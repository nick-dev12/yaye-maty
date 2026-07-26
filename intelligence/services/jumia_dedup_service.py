"""
Dédoublonnage Jumia — évite de re-scraper les produits déjà en base.

Priorité : découvrir de **nouveaux** SKU à chaque session (pilotée par mots-clés).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from intelligence.services.collection_model_router import CollectionModelRouter

SKU_FROM_URL_RE = re.compile(r'-([A-Z0-9]{6,64})\.html(?:\?|#|$)', re.I)


class JumiaDedupService:
    """Utilitaires anti-doublon pour listings, accueil et fiches produit."""

    @staticmethod
    def extract_sku_from_url(url: str) -> str:
        """Extrait le SKU Jumia depuis l'URL produit (suffixe -SKU.html)."""
        if not url:
            return ''
        path = urlparse(url).path or url
        match = SKU_FROM_URL_RE.search(path)
        return match.group(1).upper() if match else ''

    @staticmethod
    def normalize_product_url(url: str) -> str:
        """Normalise une URL produit pour comparaison (sans query/fragment)."""
        if not url:
            return ''
        parsed = urlparse(url.strip())
        path = parsed.path.rstrip('/') or parsed.path
        host = (parsed.netloc or 'www.jumia.sn').lower()
        if host.startswith('www.'):
            host = host[4:]
        return f'{host}{path}'.lower()

    @classmethod
    def load_known_sets(cls, *, test_mode: bool = False) -> tuple[set[str], set[str]]:
        """Charge les SKU et URLs déjà persistés (prod ou tables test selon contexte)."""
        _ = test_mode
        router = CollectionModelRouter()
        Product = router.jumia_product_model
        skus = {s.upper() for s in Product.objects.values_list('sku', flat=True) if s}
        urls = {
            cls.normalize_product_url(u)
            for u in Product.objects.values_list('product_url', flat=True)
            if u
        }
        return skus, urls

    @classmethod
    def enrich_cards_with_sku(cls, cards: list[dict]) -> list[dict]:
        """Ajoute le champ ``sku`` extrait de l'URL sur chaque carte."""
        for card in cards:
            if not card.get('sku'):
                card['sku'] = cls.extract_sku_from_url(card.get('url') or '')
        return cards

    @classmethod
    def is_known_card(
        cls,
        card: dict,
        *,
        known_skus: set[str],
        known_urls: set[str],
    ) -> bool:
        sku = (card.get('sku') or cls.extract_sku_from_url(card.get('url') or '')).upper()
        url = cls.normalize_product_url(card.get('url') or '')
        if sku and sku in known_skus:
            return True
        return bool(url and url in known_urls)

    @classmethod
    def filter_new_cards(
        cls,
        cards: list[dict],
        *,
        known_skus: set[str],
        known_urls: set[str],
        limit: int | None = None,
    ) -> tuple[list[dict], int]:
        """
        Retourne les cartes inconnues en priorité.

        Returns:
            (cartes_nouvelles, nombre_ignorées)
        """
        cls.enrich_cards_with_sku(cards)
        new_cards: list[dict] = []
        skipped = 0
        for card in cards:
            if cls.is_known_card(card, known_skus=known_skus, known_urls=known_urls):
                skipped += 1
                continue
            new_cards.append(card)
            if limit and len(new_cards) >= limit:
                break
        return new_cards, skipped

    @classmethod
    def register_seen(cls, card: dict, *, known_skus: set[str], known_urls: set[str]) -> None:
        """Marque un produit comme vu en session (évite double fetch)."""
        sku = (card.get('sku') or cls.extract_sku_from_url(card.get('url') or '')).upper()
        url = cls.normalize_product_url(card.get('url') or '')
        if sku:
            known_skus.add(sku)
        if url:
            known_urls.add(url)
