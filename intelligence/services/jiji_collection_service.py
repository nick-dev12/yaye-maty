"""
Collecte Jiji — annonces locales via mots-clés Paramètres (max_videos = nb annonces).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import Callable

from django.db import close_old_connections, transaction
from django.utils import timezone

from intelligence.collection_config import get_effective_collection_config
from intelligence.models import MarketSearchKeyword
from intelligence.services.collection_abort import CollectionAborted
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jiji_dedup_service import JijiDedupService
from intelligence.services.jiji_scraper import JijiScraper, JijiScraperError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
ShouldCancelCallback = Callable[[], bool]


class JijiCollectionService:
    """Orchestre scraping Jiji → tables prod/test via CollectionModelRouter."""

    @classmethod
    def run(
        cls,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        config = get_effective_collection_config(test_mode=test_mode)
        max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
        if test_mode:
            session_cap = int(config.get('MAX_VIDEOS_PER_KEYWORD_SESSION') or 0)
        else:
            session_cap = int(config.get('JIJI_MAX_LISTINGS_PER_KEYWORD') or 0)
        delay_min = float(config.get('JIJI_DELAY_MIN') or 1.5)
        delay_max = float(config.get('JIJI_DELAY_MAX') or 3.5)
        use_pw = bool(config.get('JIJI_USE_PLAYWRIGHT', True))
        reveal = bool(config.get('JIJI_REVEAL_CONTACTS', False))
        skip_known = bool(config.get('JIJI_SKIP_KNOWN_LISTINGS', True))
        search_first = bool(config.get('JIJI_SEARCH_FIRST', True))
        homepage_enabled = bool(config.get('JIJI_HOMEPAGE_RADAR_ENABLED', True))

        from intelligence.services.active_keyword_service import ActiveKeywordService

        keywords = list(
            ActiveKeywordService.list_for_jiji(limit=max_kw if max_kw > 0 else 0)
        )

        if not keywords:
            return {
                'success': False,
                'message': 'Aucun mot-clé marketplace actif dans Paramètres → Mots-clés marketplace.',
                'nouvelles_donnees': 0,
                'listings_created': 0,
                'listings_updated': 0,
                'listings_skipped': 0,
                'snapshots_created': 0,
            }

        cls._report(progress, 2, f'Jiji — {len(keywords)} mot(s)-clé(s) à traiter')
        scraper = JijiScraper(
            delay_min=delay_min,
            delay_max=delay_max,
            should_cancel=should_cancel,
            use_playwright=use_pw,
            reveal_contacts=reveal,
        )
        known_ids, known_urls = JijiDedupService.load_known_sets(test_mode=test_mode)
        created = updated = snaps = skipped_total = 0
        errors: list[str] = []
        keyword_summaries: list[dict] = []
        homepage_result: dict = {}

        try:
            total = max(len(keywords), 1)
            for idx, kw in enumerate(keywords):
                if should_cancel and should_cancel():
                    break
                max_listings = cls._listing_limit_for_keyword(kw, session_cap=session_cap)
                start_page = max(1, int(getattr(kw, 'listing_page_offset', None) or 1))
                pct = 5 + int(75 * idx / total)
                cls._report(progress, pct, f'Jiji — « {kw.keyword} » · cible {max_listings} annonce(s)')
                try:
                    cards = scraper.search_listing_urls(
                        kw.keyword,
                        product_category=kw.product_category,
                        max_products=max_listings,
                        known_ids=known_ids,
                        known_urls=known_urls,
                        skip_known=skip_known,
                        search_first=search_first,
                        listing_page_offset=start_page,
                    )
                except JijiScraperError:
                    break
                except Exception as exc:
                    logger.exception('Listing Jiji échoué pour %s', kw.keyword)
                    errors.append(f'{kw.keyword}: listing {exc}')
                    continue

                kw_c = kw_u = kw_s = kw_skipped = 0
                for i, card in enumerate(cards):
                    if should_cancel and should_cancel():
                        break
                    if skip_known and JijiDedupService.is_known_card(
                        card, known_ids=known_ids, known_urls=known_urls,
                    ):
                        kw_skipped += 1
                        skipped_total += 1
                        continue
                    cls._report(
                        progress,
                        pct + int(10 * (i + 1) / max(len(cards), 1)),
                        f'Jiji — {kw.keyword} · annonce {i + 1}/{len(cards)}',
                    )
                    try:
                        extracted = scraper.fetch_listing(
                            card['url'],
                            keyword=kw.keyword,
                            product_category=kw.product_category,
                        )
                        if not extracted:
                            continue
                        c, u, s = cls._persist_safe(extracted)
                        kw_c += c
                        kw_u += u
                        kw_s += s
                        created += c
                        updated += u
                        snaps += s
                        JijiDedupService.register_seen(
                            {'url': extracted.listing_url, 'listing_id': extracted.listing_id},
                            known_ids=known_ids,
                            known_urls=known_urls,
                        )
                    except JijiScraperError:
                        raise
                    except Exception as exc:
                        logger.exception('Annonce Jiji échouée %s', card.get('url'))
                        errors.append(f"{(card.get('title') or '?')[:40]}: {exc}")

                if not test_mode:
                    next_offset = start_page + 1
                    if next_offset > 20:
                        next_offset = 1
                    cls._run_orm_safe(
                        cls._update_keyword_scrape_state,
                        kw.pk,
                        next_offset,
                    )

                keyword_summaries.append({
                    'keyword': kw.keyword,
                    'target_listings': max_listings,
                    'listings': len(cards),
                    'listings_skipped': kw_skipped,
                    'start_page': start_page,
                    'listings_created': kw_c,
                    'listings_updated': kw_u,
                    'snapshots_created': kw_s,
                })

            if homepage_enabled and not (should_cancel and should_cancel()):
                cls._report(progress, 76, 'Jiji — radar Trending accueil…')
                from intelligence.services.jiji_homepage_service import JijiHomepageService

                homepage_result = JijiHomepageService.run(
                    scraper,
                    keywords=keywords,
                    progress=progress,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                    enrich_new=True,
                )
                created += int(homepage_result.get('listings_created') or 0)
                skipped_total += int(homepage_result.get('listings_skipped') or 0)

            cls._refresh_signals_safe()

            nouvelles = created
            cancelled = bool(should_cancel and should_cancel())
            msg = (
                f'Jiji : {created} annonce(s) créée(s), {updated} mise(s) à jour, '
                f'{skipped_total} ignorée(s) (déjà connues), {snaps} snapshot(s)'
            )
            if cancelled:
                msg = f'Interrompu — {msg}'
            cls._report(progress, 95 if not cancelled else 90, msg)
            return {
                'success': not cancelled and not (nouvelles == 0 and errors and skipped_total == 0),
                'message': msg,
                'nouvelles_donnees': nouvelles,
                'listings_created': created,
                'listings_updated': updated,
                'listings_skipped': skipped_total,
                'snapshots_created': snaps,
                'homepage_radar': homepage_result,
                'keywords': keyword_summaries,
                'errors': errors[:20],
                'requests': scraper.request_count,
                'playwright_fetches': scraper.playwright_fetches,
                'cancelled': cancelled,
            }
        except (JijiScraperError, CollectionAborted) as exc:
            logger.warning('Collecte Jiji stoppée : %s', exc)
            cls._refresh_signals_safe()
            return {
                'success': False,
                'message': str(exc) or 'Collecte Jiji interrompue.',
                'nouvelles_donnees': created,
                'listings_created': created,
                'listings_updated': updated,
                'listings_skipped': skipped_total,
                'snapshots_created': snaps,
                'keywords': keyword_summaries,
                'errors': errors + [str(exc)],
                'requests': scraper.request_count,
                'playwright_fetches': scraper.playwright_fetches,
                'cancelled': True,
            }
        finally:
            scraper.close()

    @classmethod
    def _refresh_signals_safe(cls) -> None:
        """Recalcule l'arbitrage Jiji/Jumia après collecte complète ou partielle."""
        try:
            from intelligence.services.jiji_market_signal_service import JijiMarketSignalService
            cls._run_orm_safe(JijiMarketSignalService.refresh_arbitrage_hints)
        except Exception:
            logger.exception('Recalcul arbitrage Jiji échoué')

    @staticmethod
    def _update_keyword_scrape_state(keyword_pk: int, next_offset: int) -> None:
        MarketSearchKeyword.objects.filter(pk=keyword_pk).update(
            last_scraped_at=timezone.now(),
            listing_page_offset=next_offset,
        )

    @staticmethod
    def _listing_limit_for_keyword(kw, *, session_cap: int = 0) -> int:
        keyword_limit = max(1, int(getattr(kw, 'max_videos', None) or 15))
        if session_cap and session_cap > 0:
            return max(1, min(keyword_limit, session_cap))
        return keyword_limit

    @classmethod
    def _persist_safe(cls, extracted) -> tuple[int, int, int]:
        return cls._run_orm_safe(cls._persist, extracted)

    @staticmethod
    def _run_orm_safe(fn, *args, **kwargs):
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
    def _persist(cls, extracted) -> tuple[int, int, int]:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        Snapshot = router.jiji_snapshot_model

        defaults = {
            'listing_url': extracted.listing_url,
            'title': extracted.title,
            'category': extracted.category,
            'price_xof': extracted.price_xof,
            'is_negotiable': extracted.is_negotiable,
            'condition': extracted.condition,
            'location_region': extracted.location_region,
            'location_area': extracted.location_area,
            'views_count': extracted.views_count,
            'seller_name': extracted.seller_name,
            'seller_member_since': extracted.seller_member_since,
            'seller_is_verified': extracted.seller_is_verified,
            'seller_is_premium': extracted.seller_is_premium,
            'seller_response_stat': extracted.seller_response_stat,
            'seller_ads_count': extracted.seller_ads_count,
            'search_keyword': extracted.search_keyword,
            'catalog_product_slug': extracted.catalog_product_slug,
            'description': extracted.description,
            'image_url': extracted.image_url,
            'attributes': extracted.attributes or {},
            'phone_revealed': extracted.phone_revealed,
        }
        obj, was_created = Listing.objects.update_or_create(
            listing_id=extracted.listing_id,
            defaults=defaults,
        )
        snap_n = 0
        need_snap = was_created
        if not was_created:
            prev = Snapshot.objects.filter(listing=obj).order_by('-captured_at').first()
            if not prev or (
                prev.price_xof != obj.price_xof
                or prev.is_negotiable != obj.is_negotiable
                or prev.views_count != obj.views_count
                or prev.condition != obj.condition
            ):
                need_snap = True
        if need_snap:
            Snapshot.objects.create(
                listing=obj,
                price_xof=obj.price_xof,
                is_negotiable=obj.is_negotiable,
                condition=obj.condition,
                views_count=obj.views_count,
            )
            snap_n = 1
        return (1, 0, snap_n) if was_created else (0, 1, snap_n)

    @staticmethod
    def _report(progress: ProgressCallback | None, pct: int, message: str, phase: str = 'collecte') -> None:
        if progress:
            try:
                progress(pct, message, phase)
            except TypeError:
                progress(pct, message)

