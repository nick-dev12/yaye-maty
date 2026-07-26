"""
Dédoublonnage Jiji — évite de re-scraper les annonces déjà en base.

Priorité : découvrir de **nouvelles** annonces à chaque session (pilotée par mots-clés).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from intelligence.services.collection_model_router import CollectionModelRouter

LISTING_ID_FROM_URL_RE = re.compile(r'-([A-Za-z0-9]{10,})\.html(?:\?|#|$)')


class JijiDedupService:
    """Utilitaires anti-doublon pour listings Jiji."""

    @staticmethod
    def extract_listing_id(url: str) -> str:
        """Extrait l'ID annonce Jiji depuis l'URL (suffixe -ID.html)."""
        if not url:
            return ''
        path = urlparse(url).path or url
        match = LISTING_ID_FROM_URL_RE.search(path)
        if match:
            return match.group(1)
        fallback = re.search(r'/([A-Za-z0-9_-]{12,})\.html', path)
        if fallback:
            return fallback.group(1)[-40:]
        return ''

    @staticmethod
    def normalize_listing_url(url: str) -> str:
        """Normalise une URL annonce (sans query/fragment)."""
        if not url:
            return ''
        parsed = urlparse(url.strip())
        path = parsed.path.rstrip('/') or parsed.path
        host = (parsed.netloc or 'jiji.sn').lower()
        if host.startswith('www.'):
            host = host[4:]
        return f'{host}{path}'.lower()

    @classmethod
    def load_known_sets(cls, *, test_mode: bool = False) -> tuple[set[str], set[str]]:
        _ = test_mode
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        ids = {i for i in Listing.objects.values_list('listing_id', flat=True) if i}
        urls = {
            cls.normalize_listing_url(u)
            for u in Listing.objects.values_list('listing_url', flat=True)
            if u
        }
        return ids, urls

    @classmethod
    def enrich_cards_with_id(cls, cards: list[dict]) -> list[dict]:
        for card in cards:
            if not card.get('listing_id'):
                card['listing_id'] = cls.extract_listing_id(card.get('url') or '')
        return cards

    @classmethod
    def is_known_card(
        cls,
        card: dict,
        *,
        known_ids: set[str],
        known_urls: set[str],
    ) -> bool:
        listing_id = card.get('listing_id') or cls.extract_listing_id(card.get('url') or '')
        url = cls.normalize_listing_url(card.get('url') or '')
        if listing_id and listing_id in known_ids:
            return True
        return bool(url and url in known_urls)

    @classmethod
    def filter_new_cards(
        cls,
        cards: list[dict],
        *,
        known_ids: set[str],
        known_urls: set[str],
        limit: int | None = None,
    ) -> tuple[list[dict], int]:
        cls.enrich_cards_with_id(cards)
        new_cards: list[dict] = []
        skipped = 0
        for card in cards:
            if cls.is_known_card(card, known_ids=known_ids, known_urls=known_urls):
                skipped += 1
                continue
            new_cards.append(card)
            if limit and len(new_cards) >= limit:
                break
        return new_cards, skipped

    @classmethod
    def register_seen(cls, card: dict, *, known_ids: set[str], known_urls: set[str]) -> None:
        listing_id = card.get('listing_id') or cls.extract_listing_id(card.get('url') or '')
        url = cls.normalize_listing_url(card.get('url') or '')
        if listing_id:
            known_ids.add(listing_id)
        if url:
            known_urls.add(url)
