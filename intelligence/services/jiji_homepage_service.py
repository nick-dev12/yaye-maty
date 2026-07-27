"""
Radar accueil Jiji (Trending) — filtré par mots-clés actifs Paramètres.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from django.db import transaction

from intelligence.collection_config import get_effective_collection_config
from intelligence.models import MarketSearchKeyword
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jiji_dedup_service import JijiDedupService
from intelligence.services.jiji_scraper import JijiScraper, JijiScraperError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
ShouldCancelCallback = Callable[[], bool]

SELLER_TENURE_RE = re.compile(
    r'(\d+\+?\s*(?:years?|ans?|months?|mois)\s+on\s+jiji|\d+\+?\s*(?:ans?|mois)\s+sur\s+jiji)',
    re.I,
)


class JijiHomepageService:
    """Scrape Trending Jiji, matche les mots-clés Jiji actifs, enrichit les nouveautés."""

    @classmethod
    def run(
        cls,
        scraper: JijiScraper | None = None,
        *,
        keywords: list[MarketSearchKeyword] | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
        enrich_new: bool = True,
    ) -> dict:
        config = get_effective_collection_config(test_mode=test_mode)
        if not config.get('JIJI_HOMEPAGE_RADAR_ENABLED', True):
            return {
                'success': True,
                'skipped': True,
                'message': 'Radar accueil Jiji désactivé.',
                'hits_created': 0,
                'listings_created': 0,
            }

        own_scraper = scraper is None

        if keywords is None:
            from intelligence.services.active_keyword_service import ActiveKeywordService
            from intelligence.services.django_orm_safe import run_orm_safe

            max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
            limit = max_kw if max_kw > 0 else 0

            def _load_keywords() -> list[MarketSearchKeyword]:
                return list(ActiveKeywordService.list_for_jiji(limit=limit))

            keywords = _load_keywords() if own_scraper else run_orm_safe(_load_keywords)
        else:
            keywords = list(keywords)

        if not keywords:
            return {
                'success': False,
                'message': 'Aucun mot-clé Jiji actif pour le radar accueil.',
                'hits_created': 0,
                'listings_created': 0,
            }

        scraper = scraper or JijiScraper(
            delay_min=float(config.get('JIJI_DELAY_MIN') or 1.5),
            delay_max=float(config.get('JIJI_DELAY_MAX') or 3.5),
            should_cancel=should_cancel,
            use_playwright=bool(config.get('JIJI_USE_PLAYWRIGHT', True)),
            reveal_contacts=bool(config.get('JIJI_REVEAL_CONTACTS', False)),
        )

        if own_scraper:
            known_ids, known_urls = JijiDedupService.load_known_sets(test_mode=test_mode)
        else:
            from intelligence.services.django_orm_safe import run_orm_safe

            known_ids, known_urls = run_orm_safe(
                JijiDedupService.load_known_sets,
                test_mode=test_mode,
            )
        hits_created = listings_created = listings_skipped = 0
        errors: list[str] = []

        try:
            cls._report(progress, 78, 'Jiji accueil — chargement Trending…')
            cards = scraper.fetch_homepage_cards()
            if not cards:
                return {
                    'success': False,
                    'message': 'Accueil Jiji : aucune annonce Trending détectée.',
                    'hits_created': 0,
                    'listings_created': 0,
                }

            cls._report(progress, 82, f'Jiji accueil — {len(cards)} annonce(s), filtrage mots-clés…')

            for kw in keywords:
                if should_cancel and should_cancel():
                    break

                matched = scraper.filter_cards_by_keyword(cards, kw.keyword)
                limit = cls._homepage_limit_for_keyword(kw, config=config)
                new_cards, skipped = JijiDedupService.filter_new_cards(
                    matched,
                    known_ids=known_ids,
                    known_urls=known_urls,
                    limit=limit,
                )
                listings_skipped += skipped

                for card in new_cards:
                    if cls._persist_hit_safe(card, keyword=kw, test_mode=test_mode):
                        hits_created += 1

                    if not enrich_new:
                        JijiDedupService.register_seen(
                            card, known_ids=known_ids, known_urls=known_urls,
                        )
                        continue

                    try:
                        extracted = scraper.fetch_listing(
                            card['url'],
                            keyword=kw.keyword,
                            product_category=kw.product_category,
                        )
                        if not extracted:
                            continue
                        created, _updated, _snap = JijiCollectionService._persist_safe(extracted)
                        listings_created += created
                        JijiDedupService.register_seen(
                            {'url': extracted.listing_url, 'listing_id': extracted.listing_id},
                            known_ids=known_ids,
                            known_urls=known_urls,
                        )
                        cls._mark_hit_enriched_safe(
                            card['url'],
                            kw.keyword,
                            listing_id=extracted.listing_id,
                        )
                    except JijiScraperError:
                        raise
                    except Exception as exc:
                        logger.exception('Enrichissement accueil Jiji échoué %s', card.get('url'))
                        errors.append(str(exc)[:120])

            msg = (
                f'Radar Jiji : {hits_created} hit(s), '
                f'{listings_created} nouvelle(s) annonce(s), '
                f'{listings_skipped} déjà connue(s) ignorée(s)'
            )
            cls._report(progress, 92, msg)
            return {
                'success': True,
                'message': msg,
                'hits_created': hits_created,
                'listings_created': listings_created,
                'listings_skipped': listings_skipped,
                'homepage_cards': len(cards),
                'errors': errors[:10],
            }
        finally:
            if own_scraper:
                scraper.close()

    @staticmethod
    def _homepage_limit_for_keyword(kw, *, config: dict) -> int:
        cap = int(config.get('JIJI_HOMEPAGE_MAX_LISTINGS_PER_KEYWORD') or 3)
        kw_cap = max(1, int(getattr(kw, 'max_videos', None) or 15))
        return max(1, min(cap, kw_cap))

    @classmethod
    def _persist_hit_safe(cls, card: dict, *, keyword: MarketSearchKeyword, test_mode: bool) -> bool:
        from intelligence.services.jiji_collection_service import JijiCollectionService

        return JijiCollectionService._run_orm_safe(
            cls._persist_hit,
            card,
            keyword=keyword,
            test_mode=test_mode,
        )

    @classmethod
    @transaction.atomic
    def _persist_hit(cls, card: dict, *, keyword: MarketSearchKeyword, test_mode: bool) -> bool:
        router = CollectionModelRouter()
        Hit = router.jiji_homepage_hit_model
        listing_id = card.get('listing_id') or JijiDedupService.extract_listing_id(card.get('url') or '')
        raw = card.get('raw_text') or card.get('title') or ''
        seller_badge = ''
        m = SELLER_TENURE_RE.search(raw)
        if m:
            seller_badge = m.group(1)[:120]

        defaults = {
            'listing_id': listing_id,
            'title': (card.get('title') or card.get('name') or '')[:400],
            'price_label': (card.get('price') or '')[:64],
            'condition_label': (card.get('condition_label') or '')[:40],
            'location_label': (card.get('location') or '')[:160],
            'seller_badge': seller_badge,
            'section_label': (card.get('section_label') or 'trending')[:160],
        }
        lookup = {'listing_url': card['url'], 'matched_keyword': keyword.keyword}
        if hasattr(Hit, 'keyword'):
            defaults['keyword'] = keyword
        else:
            defaults['keyword_id'] = keyword.pk

        _, created = Hit.objects.get_or_create(**lookup, defaults=defaults)
        return created

    @classmethod
    def _mark_hit_enriched_safe(cls, listing_url: str, matched_keyword: str, *, listing_id: str) -> None:
        from intelligence.services.jiji_collection_service import JijiCollectionService

        JijiCollectionService._run_orm_safe(
            cls._mark_hit_enriched,
            listing_url,
            matched_keyword,
            listing_id=listing_id,
        )

    @classmethod
    def _mark_hit_enriched(cls, listing_url: str, matched_keyword: str, *, listing_id: str) -> None:
        router = CollectionModelRouter()
        Hit = router.jiji_homepage_hit_model
        Hit.objects.filter(
            listing_url=listing_url,
            matched_keyword=matched_keyword,
        ).update(enriched=True, listing_id=listing_id or '')

    @staticmethod
    def _report(progress: ProgressCallback | None, pct: int, message: str) -> None:
        if not progress:
            return
        try:
            progress(max(0, min(100, pct)), message, 'collecte')
        except TypeError:
            progress(max(0, min(100, pct)), message)
