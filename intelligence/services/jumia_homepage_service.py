"""
Radar accueil Jumia — détecte les produits mis en avant, filtrés par mots-clés actifs.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from django.db import transaction
from django.utils import timezone

from intelligence.collection_config import get_effective_collection_config
from intelligence.models import MarketSearchKeyword
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jumia_dedup_service import JumiaDedupService
from intelligence.services.jumia_scraper import JumiaScraper, JumiaScraperError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
ShouldCancelCallback = Callable[[], bool]

STOCK_REMAINING_RE = re.compile(
    r'(\d+)\s*articles?\s*restants?',
    re.I,
)


class JumiaHomepageService:
    """Scrape l'accueil Jumia, matche les mots-clés Jumia actifs, enrichit les nouveautés."""

    @classmethod
    def run(
        cls,
        scraper: JumiaScraper | None = None,
        *,
        keywords: list[MarketSearchKeyword] | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
        enrich_new: bool = True,
    ) -> dict:
        config = get_effective_collection_config(test_mode=test_mode)
        if not config.get('JUMIA_HOMEPAGE_RADAR_ENABLED', True):
            return {
                'success': True,
                'skipped': True,
                'message': 'Radar accueil Jumia désactivé.',
                'hits_created': 0,
                'products_created': 0,
            }

        own_scraper = scraper is None

        if keywords is None:
            from intelligence.services.active_keyword_service import ActiveKeywordService
            from intelligence.services.django_orm_safe import run_orm_safe

            max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
            limit = max_kw if max_kw > 0 else 0

            def _load_keywords() -> list[MarketSearchKeyword]:
                return list(ActiveKeywordService.list_for_jumia(limit=limit))

            keywords = _load_keywords() if own_scraper else run_orm_safe(_load_keywords)
        else:
            keywords = list(keywords)

        if not keywords:
            return {
                'success': False,
                'message': 'Aucun mot-clé Jumia actif pour le radar accueil.',
                'hits_created': 0,
                'products_created': 0,
            }

        scraper = scraper or JumiaScraper(
            delay_min=float(config.get('JUMIA_DELAY_MIN') or 1.5),
            delay_max=float(config.get('JUMIA_DELAY_MAX') or 3.5),
            should_cancel=should_cancel,
            use_playwright_fallback=bool(config.get('JUMIA_USE_PLAYWRIGHT', True)),
        )

        if own_scraper:
            known_skus, known_urls = JumiaDedupService.load_known_sets(test_mode=test_mode)
        else:
            from intelligence.services.django_orm_safe import run_orm_safe

            known_skus, known_urls = run_orm_safe(
                JumiaDedupService.load_known_sets,
                test_mode=test_mode,
            )
        hits_created = 0
        products_created = 0
        products_skipped = 0
        reviews_created = 0
        errors: list[str] = []

        try:
            cls._report(progress, 78, 'Jumia accueil — chargement page d\'accueil…')
            cards = scraper.fetch_homepage_cards()
            if not cards:
                return {
                    'success': False,
                    'message': 'Accueil Jumia : aucune carte produit détectée.',
                    'hits_created': 0,
                    'products_created': 0,
                }

            cls._report(progress, 82, f'Jumia accueil — {len(cards)} carte(s), filtrage mots-clés…')

            for kw in keywords:
                if should_cancel and should_cancel():
                    break

                matched = scraper.filter_cards_by_keyword(cards, kw.keyword)
                new_cards, skipped = JumiaDedupService.filter_new_cards(
                    matched,
                    known_skus=known_skus,
                    known_urls=known_urls,
                    limit=cls._homepage_limit_for_keyword(kw, config=config),
                )
                products_skipped += skipped

                for card in new_cards:
                    hit_created = cls._persist_hit_safe(
                        card,
                        keyword=kw,
                        test_mode=test_mode,
                    )
                    if hit_created:
                        hits_created += 1

                    if not enrich_new:
                        JumiaDedupService.register_seen(
                            card, known_skus=known_skus, known_urls=known_urls,
                        )
                        continue

                    max_reviews = JumiaCollectionService._review_limit_for_keyword(
                        kw,
                        session_cap=int(config.get('JUMIA_MAX_REVIEWS_PER_PRODUCT') or 0),
                    )
                    try:
                        extracted = scraper.fetch_product(
                            card['url'],
                            keyword=kw.keyword,
                            product_category=kw.product_category,
                            max_reviews=max_reviews,
                        )
                        if not extracted:
                            continue
                        created, _updated, rev_n, _snap = JumiaCollectionService._persist_safe(
                            extracted,
                        )
                        products_created += created
                        reviews_created += rev_n
                        JumiaDedupService.register_seen(
                            card,
                            known_skus=known_skus,
                            known_urls=known_urls,
                        )
                        if created:
                            known_skus.add(extracted.sku.upper())
                            known_urls.add(
                                JumiaDedupService.normalize_product_url(extracted.product_url),
                            )
                        cls._mark_hit_enriched_safe(
                            card['url'],
                            kw.keyword,
                            sku=extracted.sku,
                            test_mode=test_mode,
                        )
                    except JumiaScraperError:
                        raise
                    except Exception as exc:
                        logger.exception('Enrichissement accueil Jumia échoué %s', card.get('url'))
                        errors.append(str(exc)[:120])

            msg = (
                f'Radar accueil : {hits_created} hit(s), '
                f'{products_created} nouveau(x) produit(s), '
                f'{products_skipped} déjà connu(s) ignoré(s)'
            )
            cls._report(progress, 92, msg)
            return {
                'success': True,
                'message': msg,
                'hits_created': hits_created,
                'products_created': products_created,
                'products_skipped': products_skipped,
                'reviews_created': reviews_created,
                'homepage_cards': len(cards),
                'errors': errors[:10],
            }
        finally:
            if own_scraper:
                scraper.close()

    @staticmethod
    def _homepage_limit_for_keyword(kw, *, config: dict) -> int:
        cap = int(config.get('JUMIA_HOMEPAGE_MAX_PRODUCTS_PER_KEYWORD') or 3)
        kw_cap = max(1, int(getattr(kw, 'max_videos', None) or 15))
        return max(1, min(cap, kw_cap))

    @classmethod
    def _persist_hit_safe(cls, card: dict, *, keyword: MarketSearchKeyword, test_mode: bool) -> bool:
        from intelligence.services.jumia_collection_service import JumiaCollectionService

        return JumiaCollectionService._run_orm_safe(
            cls._persist_hit,
            card,
            keyword=keyword,
            test_mode=test_mode,
        )

    @classmethod
    @transaction.atomic
    def _persist_hit(cls, card: dict, *, keyword: MarketSearchKeyword, test_mode: bool) -> bool:
        router = CollectionModelRouter()
        Hit = router.jumia_homepage_hit_model
        stock = card.get('stock_remaining')
        if stock is None:
            m = STOCK_REMAINING_RE.search(card.get('raw_text') or card.get('name') or '')
            if m:
                stock = int(m.group(1))

        sku = card.get('sku') or JumiaDedupService.extract_sku_from_url(card.get('url') or '')
        defaults = {
            'sku': sku,
            'name': (card.get('name') or '')[:400],
            'price_label': (card.get('price') or '')[:64],
            'discount_percent': card.get('discount_percent'),
            'stock_remaining': stock,
            'section_label': (card.get('section_label') or 'accueil')[:160],
        }
        if hasattr(Hit, 'keyword'):
            lookup = {'product_url': card['url'], 'matched_keyword': keyword.keyword}
            defaults['keyword'] = keyword
        else:
            lookup = {'product_url': card['url'], 'matched_keyword': keyword.keyword}
            defaults['keyword_id'] = keyword.pk

        _, created = Hit.objects.get_or_create(**lookup, defaults=defaults)
        return created

    @classmethod
    def _mark_hit_enriched_safe(
        cls,
        product_url: str,
        matched_keyword: str,
        *,
        sku: str,
        test_mode: bool,
    ) -> None:
        from intelligence.services.jumia_collection_service import JumiaCollectionService

        JumiaCollectionService._run_orm_safe(
            cls._mark_hit_enriched,
            product_url,
            matched_keyword,
            sku=sku,
        )

    @classmethod
    def _mark_hit_enriched(cls, product_url: str, matched_keyword: str, *, sku: str) -> None:
        router = CollectionModelRouter()
        Hit = router.jumia_homepage_hit_model
        Hit.objects.filter(
            product_url=product_url,
            matched_keyword=matched_keyword,
        ).update(enriched=True, sku=sku or '')

    @staticmethod
    def _report(progress: ProgressCallback | None, pct: int, message: str) -> None:
        if not progress:
            return
        try:
            progress(max(0, min(100, pct)), message, 'collecte')
        except TypeError:
            progress(max(0, min(100, pct)), message)
