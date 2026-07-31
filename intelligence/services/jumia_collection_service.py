"""
Collecte Jumia — produits + avis + historique prix/stock (mots-clés Paramètres).
"""

from __future__ import annotations

import logging
from typing import Callable

from django.db import transaction
from django.utils import timezone

from intelligence.collection_config import get_effective_collection_config
from intelligence.models import JumiaProduct, JumiaReview, MarketSearchKeyword
from intelligence.services.collection_abort import CollectionAborted
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jumia_scraper import JumiaScraper, JumiaScraperError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
ShouldCancelCallback = Callable[[], bool]


class JumiaCollectionService:
    """Orchestre scraping Jumia → tables prod/test via CollectionModelRouter."""

    @classmethod
    def run(
        cls,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        """
        Collecte Jumia pour les mots-clés Top-Down actifs.

        Returns:
            dict success/message/nouvelles_donnees + détails produits/avis.
        """
        from intelligence.services.active_keyword_service import ActiveKeywordService

        config = get_effective_collection_config(test_mode=test_mode)
        max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
        keywords = list(
            ActiveKeywordService.list_for_jumia(limit=max_kw if max_kw > 0 else 0)
        )
        if not keywords:
            return {
                'success': False,
                'message': 'Aucun mot-clé marketplace actif dans Paramètres → Mots-clés marketplace.',
                'nouvelles_donnees': 0,
                'products_created': 0,
                'products_updated': 0,
                'reviews_created': 0,
                'snapshots_created': 0,
            }
        return cls.run_for_keywords(
            keywords,
            progress=progress,
            should_cancel=should_cancel,
            test_mode=test_mode,
        )

    @classmethod
    def run_for_keywords(
        cls,
        keywords: list,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
        skip_homepage: bool = False,
    ) -> dict:
        """Collecte Jumia pour une liste de mots-clés (y compris éphémères Trade Intelligence)."""
        config = get_effective_collection_config(test_mode=test_mode)
        max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
        # Test : plafond session TikTok. Prod : plafond optionnel JUMIA (0 = illimité hors max_videos)
        if test_mode:
            session_cap = int(config.get('MAX_VIDEOS_PER_KEYWORD_SESSION') or 0)
        else:
            session_cap = int(config.get('JUMIA_MAX_PRODUCTS_PER_KEYWORD') or 0)
        reviews_session_cap = int(config.get('JUMIA_MAX_REVIEWS_PER_PRODUCT') or 0)
        max_pages = int(config.get('JUMIA_MAX_LISTING_PAGES') or 3)
        delay_min = float(config.get('JUMIA_DELAY_MIN') or 1.5)
        delay_max = float(config.get('JUMIA_DELAY_MAX') or 3.5)
        use_pw = bool(config.get('JUMIA_USE_PLAYWRIGHT', True))
        skip_known = bool(config.get('JUMIA_SKIP_KNOWN_PRODUCTS', True))
        max_scan_pages = int(config.get('JUMIA_MAX_LISTING_SCAN_PAGES') or 9)
        homepage_enabled = bool(config.get('JUMIA_HOMEPAGE_RADAR_ENABLED', True))

        from intelligence.services.jumia_dedup_service import JumiaDedupService

        if not keywords:
            return {
                'success': False,
                'message': 'Aucun mot-clé à traiter pour Jumia.',
                'nouvelles_donnees': 0,
                'products_created': 0,
                'products_updated': 0,
                'reviews_created': 0,
                'snapshots_created': 0,
            }

        cls._report(progress, 2, f'Jumia — {len(keywords)} mot(s)-clé(s) à traiter')

        scraper = JumiaScraper(
            delay_min=delay_min,
            delay_max=delay_max,
            should_cancel=should_cancel,
            use_playwright_fallback=use_pw,
            max_listing_pages=max_pages,
        )
        known_skus, known_urls = JumiaDedupService.load_known_sets(test_mode=test_mode)
        products_created = 0
        products_updated = 0
        products_skipped = 0
        reviews_created = 0
        snapshots_created = 0
        errors: list[str] = []
        keyword_summaries: list[dict] = []
        homepage_result: dict = {}

        try:
            total_steps = max(len(keywords), 1)
            for idx, kw in enumerate(keywords):
                if should_cancel and should_cancel():
                    break
                # Paramètres mot-clé : max_videos → nb produits Jumia ; max_comments → avis
                max_products = cls._product_limit_for_keyword(kw, session_cap=session_cap)
                max_reviews = cls._review_limit_for_keyword(kw, session_cap=reviews_session_cap)
                pct = 5 + int(75 * idx / total_steps)
                cls._report(
                    progress,
                    pct,
                    f'Jumia — « {kw.keyword} » · cible {max_products} produit(s)',
                )
                try:
                    start_page = max(1, int(getattr(kw, 'listing_page_offset', None) or 1))
                    cards = scraper.search_listing_urls(
                        kw.keyword,
                        product_category=kw.product_category,
                        max_products=max_products,
                        max_pages=max_pages,
                        known_skus=known_skus,
                        known_urls=known_urls,
                        skip_known=skip_known,
                        start_page=start_page,
                        max_scan_pages=max_scan_pages,
                    )
                except JumiaScraperError:
                    break
                except Exception as exc:
                    logger.exception('Listing Jumia échoué pour %s', kw.keyword)
                    errors.append(f'{kw.keyword}: listing {exc}')
                    continue

                kw_created = kw_updated = kw_reviews = kw_snaps = kw_skipped = 0
                for card_i, card in enumerate(cards):
                    if should_cancel and should_cancel():
                        break
                    if skip_known and JumiaDedupService.is_known_card(
                        card, known_skus=known_skus, known_urls=known_urls,
                    ):
                        kw_skipped += 1
                        products_skipped += 1
                        continue
                    cls._report(
                        progress,
                        pct + int(10 * (card_i + 1) / max(len(cards), 1)),
                        f'Jumia — {kw.keyword} · produit {card_i + 1}/{len(cards)}',
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
                        if len(extracted.reviews) > max_reviews:
                            extracted.reviews = extracted.reviews[:max_reviews]
                        created, updated, rev_n, snap_n = cls._persist_safe(extracted)
                        kw_created += created
                        kw_updated += updated
                        kw_reviews += rev_n
                        kw_snaps += snap_n
                        products_created += created
                        products_updated += updated
                        reviews_created += rev_n
                        snapshots_created += snap_n
                        JumiaDedupService.register_seen(
                            {'url': extracted.product_url, 'sku': extracted.sku},
                            known_skus=known_skus,
                            known_urls=known_urls,
                        )
                    except JumiaScraperError:
                        raise
                    except Exception as exc:
                        logger.exception('Produit Jumia échoué %s', card.get('url'))
                        errors.append(f"{card.get('name', '?')[:40]}: {exc}")

                if not test_mode and getattr(kw, 'pk', None):
                    next_offset = start_page + max_pages
                    if next_offset > max_scan_pages:
                        next_offset = 1
                    cls._run_orm_safe(
                        cls._update_keyword_scrape_state,
                        kw.pk,
                        next_offset,
                    )

                keyword_summaries.append({
                    'keyword': kw.keyword,
                    'target_products': max_products,
                    'target_reviews': max_reviews,
                    'listings': len(cards),
                    'products_skipped': kw_skipped,
                    'start_page': start_page,
                    'products_created': kw_created,
                    'products_updated': kw_updated,
                    'reviews_created': kw_reviews,
                    'snapshots_created': kw_snaps,
                })

            homepage_result: dict = {}
            if homepage_enabled and not skip_homepage and not (should_cancel and should_cancel()):
                cls._report(progress, 76, 'Jumia — radar page d\'accueil…')
                from intelligence.services.jumia_homepage_service import JumiaHomepageService

                homepage_result = JumiaHomepageService.run(
                    scraper,
                    keywords=keywords,
                    progress=progress,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                    enrich_new=True,
                )
                products_created += int(homepage_result.get('products_created') or 0)
                products_skipped += int(homepage_result.get('products_skipped') or 0)
                reviews_created += int(homepage_result.get('reviews_created') or 0)

            # Recalcul signaux marché après collecte (léger, sans CamemBERT)
            cls._refresh_signals_safe()

            nouvelles = products_created + reviews_created
            cancelled = bool(should_cancel and should_cancel())
            msg = (
                f'Jumia : {products_created} produit(s) créé(s), '
                f'{products_updated} mis à jour, {products_skipped} ignoré(s) (déjà connus), '
                f'{reviews_created} avis, {snapshots_created} snapshot(s)'
            )
            if cancelled:
                msg = f'Interrompu — {msg}'
            cls._report(progress, 95 if not cancelled else 90, msg)
            return {
                'success': not cancelled and not (nouvelles == 0 and errors and products_skipped == 0),
                'message': msg,
                'nouvelles_donnees': nouvelles,
                'products_created': products_created,
                'products_updated': products_updated,
                'products_skipped': products_skipped,
                'reviews_created': reviews_created,
                'snapshots_created': snapshots_created,
                'homepage_radar': homepage_result,
                'keywords': keyword_summaries,
                'errors': errors[:20],
                'requests': scraper.request_count,
                'playwright_fetches': scraper.playwright_fetches,
                'cancelled': cancelled,
            }
        except (JumiaScraperError, CollectionAborted):
            # Même incomplètes, les données déjà persistées doivent alimenter
            # immédiatement les cartes et recommandations Intelligence.
            cls._refresh_signals_safe()
            nouvelles = products_created + reviews_created
            return {
                'success': False,
                'message': (
                    f'Jumia annulé — {products_created} produit(s), '
                    f'{reviews_created} avis conservés'
                ),
                'nouvelles_donnees': nouvelles,
                'products_created': products_created,
                'products_updated': products_updated,
                'reviews_created': reviews_created,
                'snapshots_created': snapshots_created,
                'keywords': keyword_summaries,
                'errors': errors[:20],
                'requests': scraper.request_count,
                'playwright_fetches': scraper.playwright_fetches,
                'cancelled': True,
            }
        finally:
            scraper.close()

    @classmethod
    def _refresh_signals_safe(cls) -> None:
        """Recalcule les indicateurs Jumia, y compris après un arrêt partiel."""
        try:
            from intelligence.services.jumia_market_signal_service import JumiaMarketSignalService
            cls._run_orm_safe(JumiaMarketSignalService.refresh_all)
        except Exception:
            logger.exception('Recalcul signaux marché Jumia échoué')

    @staticmethod
    def _update_keyword_scrape_state(keyword_pk: int, next_offset: int) -> None:
        MarketSearchKeyword.objects.filter(pk=keyword_pk).update(
            last_scraped_at=timezone.now(),
            listing_page_offset=next_offset,
        )

    @staticmethod
    def _product_limit_for_keyword(kw, *, session_cap: int = 0) -> int:
        """
        Nombre de produits Jumia = ``max_videos`` du mot-clé Paramètres.

        Même logique que TikTok : plafonné par ``MAX_VIDEOS_PER_KEYWORD_SESSION``
        si ce plafond session est > 0.
        """
        keyword_limit = max(1, int(getattr(kw, 'max_videos', None) or 15))
        if session_cap and session_cap > 0:
            return max(1, min(keyword_limit, session_cap))
        return keyword_limit

    @staticmethod
    def _review_limit_for_keyword(kw, *, session_cap: int = 0) -> int:
        """Nombre d'avis Jumia aligné sur ``max_comments`` du mot-clé Paramètres."""
        keyword_limit = max(1, int(getattr(kw, 'max_comments', None) or 20))
        if session_cap and session_cap > 0:
            return max(1, min(keyword_limit, session_cap))
        return keyword_limit

    @classmethod
    def _persist_safe(cls, extracted) -> tuple[int, int, int, int]:
        """Persistance ORM isolée du greenlet Playwright (évite SynchronousOnlyOperation)."""
        return cls._run_orm_safe(cls._persist, extracted)

    @staticmethod
    def _run_orm_safe(fn, *args, **kwargs):
        """Exécute une opération Django ORM hors du contexte async Playwright.

        Propage le ContextVar ``collection_run_ctx`` (prod/test) via copy_context,
        sinon ThreadPoolExecutor écrirait en production par défaut.
        """
        from concurrent.futures import ThreadPoolExecutor
        from contextvars import copy_context

        from django.db import close_old_connections

        ctx = copy_context()

        def _worker():
            close_old_connections()
            try:
                return fn(*args, **kwargs)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(ctx.run, _worker).result()

    @classmethod
    @transaction.atomic
    def _persist(cls, extracted) -> tuple[int, int, int, int]:
        router = CollectionModelRouter()
        Product = router.jumia_product_model
        Review = router.jumia_review_model
        Snapshot = router.jumia_snapshot_model
        now = timezone.now()

        discount = extracted.discount_percent
        if discount is None:
            discount = JumiaProduct.compute_discount_percent(
                extracted.price_xof, extracted.old_price_xof,
            )

        defaults = {
            'product_url': extracted.product_url,
            'name': extracted.name,
            'brand': extracted.brand or '',
            'category': extracted.category,
            'seller_name': extracted.seller_name,
            'price_xof': extracted.price_xof,
            'old_price_xof': extracted.old_price_xof,
            'discount_percent': discount,
            'currency': extracted.currency or 'XOF',
            'availability': extracted.availability,
            'stock_status': extracted.stock_status or JumiaProduct.StockStatus.UNKNOWN,
            'stock_quantity': extracted.stock_quantity,
            'is_in_stock': extracted.is_in_stock,
            'stock_checked_at': now,
            'rating_value': extracted.rating_value,
            'rating_count': extracted.rating_count or 0,
            'rating_distribution': extracted.rating_distribution or {},
            'comments_count': extracted.comments_count or 0,
            'search_keyword': extracted.search_keyword,
            'catalog_product_slug': extracted.catalog_product_slug or '',
            'description': extracted.description,
            'image_url': extracted.image_url,
        }
        obj, created = Product.objects.update_or_create(
            sku=extracted.sku,
            defaults=defaults,
        )

        # Snapshot historique si changement significatif ou première collecte
        snap_created = 0
        last = (
            Snapshot.objects.filter(product=obj)
            .order_by('-captured_at')
            .first()
        )
        should_snap = last is None
        if last is not None:
            should_snap = (
                last.price_xof != extracted.price_xof
                or last.stock_status != (extracted.stock_status or '')
                or last.rating_value != extracted.rating_value
                or last.rating_count != (extracted.rating_count or 0)
            )
        if should_snap:
            Snapshot.objects.create(
                product=obj,
                price_xof=extracted.price_xof,
                old_price_xof=extracted.old_price_xof,
                discount_percent=discount,
                stock_status=extracted.stock_status or '',
                stock_quantity=extracted.stock_quantity,
                is_in_stock=extracted.is_in_stock,
                rating_value=extracted.rating_value,
                rating_count=extracted.rating_count or 0,
            )
            snap_created = 1

        reviews_created = 0
        for rev in extracted.reviews:
            text_for_hash = rev.comment_text or rev.title
            if not text_for_hash and rev.rating_stars is None:
                continue
            rh = Review.build_review_hash(
                title=rev.title,
                comment_text=rev.comment_text,
                author=rev.author,
                rating_stars=rev.rating_stars,
            ) if hasattr(Review, 'build_review_hash') else JumiaReview.build_review_hash(
                title=rev.title,
                comment_text=rev.comment_text,
                author=rev.author,
                rating_stars=rev.rating_stars,
            )
            _, rev_created = Review.objects.get_or_create(
                product=obj,
                review_hash=rh,
                defaults={
                    'rating_stars': rev.rating_stars,
                    'title': rev.title,
                    'comment_text': rev.comment_text,
                    'author': rev.author,
                    'review_date': rev.review_date,
                    'verified_purchase': rev.verified_purchase,
                },
            )
            if rev_created:
                reviews_created += 1
        return (1 if created else 0), (0 if created else 1), reviews_created, snap_created

    @staticmethod
    def _report(progress: ProgressCallback | None, pct: int, message: str) -> None:
        if not progress:
            return
        try:
            progress(max(0, min(100, pct)), message, 'collecte')
        except TypeError:
            try:
                progress(max(0, min(100, pct)), message)
            except Exception:
                pass
        except Exception:
            pass
