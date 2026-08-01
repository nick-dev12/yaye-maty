"""
Collecte ad-hoc pour Trade Intelligence — une requête domaine + mot-clé.
Volumes illimités : seule la durée / should_cancel borne la session.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Callable

from django.conf import settings
from django.db.models import Q

from intelligence.controllers.google_trends_controller import GoogleTrendsController
from intelligence.models import JijiListing, JumiaProduct, JumiaReview, SocialPost, TrendRecord
from intelligence.services.ephemeral_keyword import build_ephemeral_keyword
from intelligence.services.jiji_collection_service import JijiCollectionService
from intelligence.services.jumia_collection_service import JumiaCollectionService
from intelligence.services.search_top_down_service import SearchTopDownService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
ShouldCancelCallback = Callable[[], bool]

# Volumes très élevés — la durée / cancel arrête la collecte
UNLIMITED_PRODUCTS = 500
UNLIMITED_LISTINGS = 500
UNLIMITED_SOCIAL = 200
UNLIMITED_REVIEWS = 20


class TradeResearchCollectionService:
    """Lance Trends, Jumia, Jiji et TikTok pour une requête unique."""

    @classmethod
    def _limits(cls) -> dict:
        cfg = getattr(settings, 'TRADE_RESEARCH', {}) or {}
        return {
            'MAX_PRODUCTS': int(cfg.get('MAX_PRODUCTS') or 0) or UNLIMITED_PRODUCTS,
            'MAX_LISTINGS': int(cfg.get('MAX_LISTINGS') or 0) or UNLIMITED_LISTINGS,
            'MAX_SOCIAL_POSTS': int(cfg.get('MAX_SOCIAL_POSTS') or 0) or UNLIMITED_SOCIAL,
            'MAX_REVIEWS': int(cfg.get('MAX_REVIEWS') or 0) or UNLIMITED_REVIEWS,
            'JUMIA_CATALOG_PRODUCTS_PER_TOUR': int(
                cfg.get('JUMIA_CATALOG_PRODUCTS_PER_TOUR') or 100
            ),
            'JUMIA_CATALOG_MAX_TOURS': int(cfg.get('JUMIA_CATALOG_MAX_TOURS') or 3),
            'JUMIA_SOURCE': str(cfg.get('JUMIA_SOURCE') or 'catalog').lower(),
            'JUMIA_CATALOG_FALLBACK_LIVE': bool(cfg.get('JUMIA_CATALOG_FALLBACK_LIVE', False)),
            'JUMIA_USE_CATALOG_FIRST': str(cfg.get('JUMIA_SOURCE') or 'catalog').lower() == 'catalog',
            'JIJI_SOURCE': str(cfg.get('JIJI_SOURCE') or 'live').lower(),
            'JIJI_DATABASE_LISTINGS_PER_TOUR': int(
                cfg.get('JIJI_DATABASE_LISTINGS_PER_TOUR') or 100
            ),
            'JIJI_DATABASE_MAX_TOURS': int(cfg.get('JIJI_DATABASE_MAX_TOURS') or 3),
            'JIJI_DATABASE_FALLBACK_LIVE': bool(cfg.get('JIJI_DATABASE_FALLBACK_LIVE', False)),
        }

    @classmethod
    def _query_tokens(cls, query: str) -> list[str]:
        stop = {'et', 'de', 'du', 'la', 'le', 'les', 'des', 'un', 'une', 'pour', 'avec', 'au', 'en'}
        return [
            t for t in query.lower().split()
            if len(t) >= 2 and t not in stop
        ]

    @classmethod
    def catalog_products_queryset(cls, query: str):
        """Produits catalogue Jumia matchant la requête (catégorie liée prioritaire)."""
        q = (query or '').strip()
        tokens = cls._query_tokens(q)
        base = JumiaProduct.objects.filter(jumia_category__isnull=False)
        if not tokens:
            if q:
                return base.filter(
                    Q(name__icontains=q)
                    | Q(brand__icontains=q)
                    | Q(category__icontains=q)
                    | Q(search_keyword__icontains=q)
                ).distinct()
            return base.none()

        q_filter = Q()
        for t in tokens:
            q_filter |= (
                Q(name__icontains=t)
                | Q(brand__icontains=t)
                | Q(category__icontains=t)
                | Q(search_keyword__icontains=t)
            )
        return base.filter(q_filter).distinct().order_by('-rating_count', '-rating_value', 'id')

    @classmethod
    def collect_trends(
        cls,
        query: str,
        *,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        if should_cancel and should_cancel():
            return {'success': False, 'message': 'Annulé', 'series': []}
        try:
            controller = GoogleTrendsController()
            terms = [t.strip() for t in query.split() if len(t.strip()) > 2][:3]
            if not terms:
                terms = [query[:80]]
            # Premier terme principal + éventuellement le mot-clé brut
            df = controller.fetch_interest_over_time(terms[:1], region='SN')
            controller.save_dataframe(df, region='SN')
            series = []
            for col in df.columns:
                values = [int(v) for v in df[col].tolist()]
                recent = values[-4:] if len(values) >= 4 else values
                avg_recent = sum(recent) / len(recent) if recent else 0
                series.append({
                    'keyword': col,
                    'avg_score': round(sum(values) / len(values), 1) if values else 0,
                    'recent_avg': round(avg_recent, 1),
                    'latest': values[-1] if values else 0,
                    'trend_direction': 'up' if len(values) >= 2 and values[-1] > values[0] else 'flat',
                })
            return {'success': True, 'terms': terms, 'series': series}
        except Exception as exc:
            msg = str(exc)
            logger.exception('Trends Trade Intelligence : %s', exc)
            return {
                'success': False,
                'message': msg,
                'series': [],
                'rate_limited': '429' in msg,
            }

    @classmethod
    def jiji_listings_queryset(cls, query: str):
        """Annonces Jiji en BDD matchant la requête."""
        q = (query or '').strip()
        tokens = cls._query_tokens(q)
        base = JijiListing.objects.all()
        if not tokens:
            if q:
                return base.filter(
                    Q(title__icontains=q)
                    | Q(category__icontains=q)
                    | Q(search_keyword__icontains=q)
                ).distinct()
            return base.none()

        q_filter = Q()
        for t in tokens:
            q_filter |= (
                Q(title__icontains=t)
                | Q(category__icontains=t)
                | Q(search_keyword__icontains=t)
            )
        return base.filter(q_filter).distinct().order_by('-views_count', '-id')

    @classmethod
    def collect_jiji_from_database(
        cls,
        query: str,
        *,
        tour_index: int = 0,
        limit: int | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        """Parcourt les annonces Jiji en BDD (pas de scrape live)."""
        if should_cancel and should_cancel():
            return {
                'success': False,
                'message': 'Annulé',
                'source': 'database',
                'listings_count': 0,
                'total_matching': 0,
                'tour_index': tour_index,
            }
        limits = cls._limits()
        per_tour = limit if limit is not None else limits['JIJI_DATABASE_LISTINGS_PER_TOUR']
        per_tour = max(1, int(per_tour))
        tour_index = max(0, int(tour_index))
        offset = tour_index * per_tour

        qs = cls.jiji_listings_queryset(query)
        total_matching = qs.count()
        page = list(qs[offset:offset + per_tour])

        if progress:
            try:
                progress(
                    10,
                    f'Jiji BDD tour {tour_index + 1} — '
                    f'{len(page)}/{total_matching} annonce(s)',
                )
            except TypeError:
                pass

        listings_payload = [
            {
                'listing_id': row.listing_id,
                'title': row.title[:120],
                'category': row.category or '',
                'price_xof': float(row.price_xof) if row.price_xof else None,
                'condition': row.condition or '',
                'location': row.location_region or row.location_area or '',
                'views': row.views_count or 0,
                'seller': row.seller_name or '',
                'url': row.listing_url,
            }
            for row in page
        ]
        has_more = (offset + len(page)) < total_matching
        return {
            'success': bool(page) or total_matching == 0,
            'message': (
                f'{len(page)} annonce(s) BDD (tour {tour_index + 1})'
                if page
                else 'Aucune annonce Jiji en BDD pour cette requête'
            ),
            'source': 'database',
            'tour_index': tour_index,
            'limit': per_tour,
            'listings_count': len(page),
            'listings_scanned': len(page),
            'total_matching': total_matching,
            'has_more': has_more,
            'listings': listings_payload,
            'nouvelles_donnees': 0,
        }

    @classmethod
    def collect_jumia_from_catalog(
        cls,
        query: str,
        *,
        tour_index: int = 0,
        limit: int | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        """
        Parcourt le catalogue Jumia en BDD (pas de scrape live).

        Chaque tour lit ``limit`` produits (défaut 100) à l'offset ``tour_index * limit``.
        """
        if should_cancel and should_cancel():
            return {
                'success': False,
                'message': 'Annulé',
                'source': 'catalog',
                'products_count': 0,
                'total_matching': 0,
                'tour_index': tour_index,
            }
        limits = cls._limits()
        per_tour = limit if limit is not None else limits['JUMIA_CATALOG_PRODUCTS_PER_TOUR']
        per_tour = max(1, int(per_tour))
        tour_index = max(0, int(tour_index))
        offset = tour_index * per_tour

        qs = cls.catalog_products_queryset(query)
        total_matching = qs.count()
        page = list(qs[offset:offset + per_tour])

        if progress:
            try:
                progress(
                    10,
                    f'Jumia catalogue tour {tour_index + 1} — '
                    f'{len(page)}/{total_matching} produit(s)',
                )
            except TypeError:
                pass

        product_ids = [p.pk for p in page]
        products_payload = [
            {
                'sku': p.sku,
                'name': p.name[:120],
                'brand': p.brand or '',
                'category': p.category or '',
                'price_xof': float(p.price_xof) if p.price_xof else None,
                'old_price_xof': float(p.old_price_xof) if p.old_price_xof else None,
                'discount_percent': p.discount_percent,
                'rating': float(p.rating_value) if p.rating_value else None,
                'reviews': p.rating_count or 0,
                'seller': p.seller_name or '',
                'url': p.product_url,
            }
            for p in page
        ]

        reviews_qs = (
            JumiaReview.objects.filter(product_id__in=product_ids)
            .exclude(comment_text='')
            .select_related('product')
            .order_by('-review_date', '-id')[:40]
        )
        reviews_sample = [
            {
                'sku': r.product.sku,
                'product': (r.product.name or '')[:80],
                'stars': r.rating_stars,
                'title': (r.title or '')[:100],
                'text': (r.comment_text or '')[:280],
                'verified': r.verified_purchase,
            }
            for r in reviews_qs
        ]

        prices = [
            Decimal(str(p.price_xof))
            for p in page
            if p.price_xof is not None
        ]
        stats = {}
        if prices:
            stats = {
                'min_xof': float(min(prices)),
                'avg_xof': float(sum(prices) / len(prices)),
                'max_xof': float(max(prices)),
                'count': len(prices),
            }

        has_more = (offset + len(page)) < total_matching
        return {
            'success': True,
            'message': (
                f'Catalogue Jumia tour {tour_index + 1}: '
                f'{len(page)} produit(s) (total match {total_matching})'
            ),
            'source': 'catalog',
            'tour_index': tour_index,
            'offset': offset,
            'limit': per_tour,
            'products_count': len(page),
            'products_scanned': len(page),
            'total_matching': total_matching,
            'has_more': has_more,
            'product_ids': product_ids,
            'products': products_payload,
            'reviews_sample': reviews_sample,
            'stats': stats,
            'nouvelles_donnees': 0,
        }

    @classmethod
    def collect_jumia(
        cls,
        query: str,
        *,
        product_category: str = '',
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        tour_index: int = 0,
        force_live: bool = False,
    ) -> dict:
        """
        Collecte Jumia pour Trade Intelligence.

        ``JUMIA_SOURCE=catalog`` → BDD catalogue ; ``live`` → scrape HTTP.
        """
        limits = cls._limits()
        source = limits.get('JUMIA_SOURCE', 'catalog')
        use_catalog = source == 'catalog' and not force_live

        if use_catalog:
            catalog = cls.collect_jumia_from_catalog(
                query,
                tour_index=tour_index,
                limit=limits['JUMIA_CATALOG_PRODUCTS_PER_TOUR'],
                progress=progress,
                should_cancel=should_cancel,
            )
            if catalog.get('total_matching', 0) > 0:
                return catalog
            if not limits.get('JUMIA_CATALOG_FALLBACK_LIVE'):
                catalog.setdefault('source', 'catalog')
                return catalog
            logger.info(
                'Catalogue Jumia vide pour %r — fallback scrape live (env)',
                query[:60],
            )

        kw = build_ephemeral_keyword(
            query,
            platform='jumia',
            product_category=product_category,
            max_videos=limits['MAX_PRODUCTS'],
            max_comments=limits['MAX_REVIEWS'],
        )
        result = JumiaCollectionService.run_for_keywords(
            [kw],
            progress=progress,
            should_cancel=should_cancel,
            test_mode=False,
            skip_homepage=True,
        )
        if isinstance(result, dict):
            result.setdefault('source', 'live')
            result.setdefault('tour_index', tour_index)
        return result

    @classmethod
    def collect_jiji(
        cls,
        query: str,
        *,
        product_category: str = '',
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        tour_index: int = 0,
        force_live: bool = False,
    ) -> dict:
        """
        Collecte Jiji pour Trade Intelligence.

        ``JIJI_SOURCE=database`` → BDD JijiListing ; ``live`` → scrape HTTP.
        """
        limits = cls._limits()
        source = limits.get('JIJI_SOURCE', 'live')
        use_database = source == 'catalog' and not force_live

        if use_database:
            db_result = cls.collect_jiji_from_database(
                query,
                tour_index=tour_index,
                limit=limits['JIJI_DATABASE_LISTINGS_PER_TOUR'],
                progress=progress,
                should_cancel=should_cancel,
            )
            if db_result.get('total_matching', 0) > 0:
                return db_result
            if not limits.get('JIJI_DATABASE_FALLBACK_LIVE'):
                return db_result
            logger.info(
                'Jiji BDD vide pour %r — fallback scrape live (env)',
                query[:60],
            )

        kw = build_ephemeral_keyword(
            query,
            platform='jiji',
            product_category=product_category,
            max_videos=limits['MAX_LISTINGS'],
        )
        result = JijiCollectionService.run_for_keywords(
            [kw],
            progress=progress,
            should_cancel=should_cancel,
            test_mode=False,
            skip_homepage=True,
            skip_nlp=True,
        )
        if isinstance(result, dict):
            result.setdefault('source', 'live')
            result.setdefault('tour_index', tour_index)
        return result

    @classmethod
    def collect_tiktok(
        cls,
        query: str,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        """Collecte TikTok uniquement (Facebook retiré du flux Trade)."""
        if should_cancel and should_cancel():
            return {'success': False, 'message': 'Annulé', 'platforms': []}
        limits = cls._limits()
        max_posts = limits['MAX_SOCIAL_POSTS']
        tiktok_kw = build_ephemeral_keyword(
            query,
            platform='tiktok',
            max_videos=max_posts,
            max_comments=15,
        )
        try:
            if progress:
                try:
                    progress(5, f'TikTok — « {query[:40]} »')
                except TypeError:
                    progress(5, f'TikTok — « {query[:40]} »')
            top_down = SearchTopDownService()
            tiktok_result = top_down.run_keyword(
                tiktok_kw,
                max_videos_session=max_posts,
            )
            return {
                'success': tiktok_result.success,
                'platforms': [{
                    'platform': 'tiktok',
                    'success': tiktok_result.success,
                    'message': tiktok_result.message,
                    'created': tiktok_result.created,
                    'updated': tiktok_result.updated,
                    'urls_harvested': tiktok_result.urls_harvested,
                }],
                'query': query,
            }
        except Exception as exc:
            logger.exception('TikTok Trade Intelligence : %s', exc)
            return {
                'success': False,
                'platforms': [{'platform': 'tiktok', 'success': False, 'message': str(exc)}],
                'query': query,
            }

    # Alias pour compatibilité
    collect_social = collect_tiktok

    @classmethod
    def aggregate_payload(cls, query: str, *, collect_results: dict) -> dict:
        """Construit le JSON compact envoyé à DeepSeek."""
        q = query.strip()
        jumia_collect = collect_results.get('jumia') or {}
        # Fusion si plusieurs tours stockés sous jumia_tours
        jumia_tours = collect_results.get('jumia_tours') or []
        if not jumia_tours and jumia_collect:
            jumia_tours = [jumia_collect]

        catalog_ids: list[int] = []
        reviews_sample: list[dict] = []
        products_scanned = 0
        tours_used = 0
        jumia_source = 'live'
        for tour in jumia_tours:
            if not isinstance(tour, dict):
                continue
            tours_used += 1
            if tour.get('source') == 'catalog':
                jumia_source = 'catalog'
            products_scanned += int(tour.get('products_scanned') or tour.get('products_count') or 0)
            for pid in tour.get('product_ids') or []:
                if pid not in catalog_ids:
                    catalog_ids.append(pid)
            for rev in tour.get('reviews_sample') or []:
                if len(reviews_sample) < 30:
                    reviews_sample.append(rev)

        if catalog_ids:
            jumia_base = JumiaProduct.objects.filter(pk__in=catalog_ids)
        else:
            catalog_qs = cls.catalog_products_queryset(q)
            if catalog_qs.exists():
                jumia_base = catalog_qs
                jumia_source = 'catalog'
            else:
                jumia_base = JumiaProduct.objects.filter(search_keyword__iexact=q)

        jumia_qs = list(jumia_base.order_by('-rating_value')[:40])
        jiji_base = JijiListing.objects.filter(search_keyword__iexact=q)
        jiji_qs = jiji_base.order_by('-views_count')[:40]
        social_qs = SocialPost.objects.filter(
            content__icontains=q[:50],
            platform='tiktok',
        ).order_by('-view_count')[:30]

        jumia_prices = list(
            jumia_base.exclude(price_xof__isnull=True).values_list('price_xof', flat=True)[:50]
        )
        jiji_prices = list(
            jiji_base.exclude(price_xof__isnull=True).values_list('price_xof', flat=True)[:50]
        )

        def price_stats(prices: list) -> dict:
            if not prices:
                return {}
            dec = [Decimal(str(p)) for p in prices]
            return {
                'min_xof': float(min(dec)),
                'avg_xof': float(sum(dec) / len(dec)),
                'max_xof': float(max(dec)),
                'count': len(dec),
            }

        if not reviews_sample and catalog_ids:
            for r in (
                JumiaReview.objects.filter(product_id__in=catalog_ids)
                .exclude(comment_text='')
                .select_related('product')
                .order_by('-review_date', '-id')[:30]
            ):
                reviews_sample.append({
                    'sku': r.product.sku,
                    'product': (r.product.name or '')[:80],
                    'stars': r.rating_stars,
                    'title': (r.title or '')[:100],
                    'text': (r.comment_text or '')[:280],
                    'verified': r.verified_purchase,
                })

        first_term = q.split()[0] if q.split() else q
        trends = TrendRecord.objects.filter(
            keyword__icontains=first_term,
            region='SN',
        ).order_by('-date')[:30]

        trend_summary = []
        seen_kw: set[str] = set()
        for tr in trends:
            if tr.keyword in seen_kw:
                continue
            seen_kw.add(tr.keyword)
            trend_summary.append({'keyword': tr.keyword, 'score': tr.score, 'date': str(tr.date)})

        return {
            'search_query': q,
            'google_trends': collect_results.get('trends', {}),
            'jumia': {
                'source': jumia_source,
                'tours_used': tours_used,
                'products_scanned': products_scanned or len(jumia_qs),
                'stats': price_stats(jumia_prices),
                'products': [
                    {
                        'name': p.name[:120],
                        'price_xof': float(p.price_xof) if p.price_xof else None,
                        'old_price_xof': float(p.old_price_xof) if p.old_price_xof else None,
                        'discount_percent': p.discount_percent,
                        'rating': float(p.rating_value) if p.rating_value else None,
                        'reviews': p.rating_count or 0,
                        'brand': p.brand or '',
                        'seller': p.seller_name or '',
                        'category': p.category or '',
                    }
                    for p in jumia_qs[:25]
                ],
                'reviews_sample': reviews_sample[:30],
                'collect': jumia_collect,
            },
            'jiji': {
                'stats': price_stats(jiji_prices),
                'listings': [
                    {
                        'title': li.title[:120],
                        'price_xof': float(li.price_xof) if li.price_xof else None,
                        'views': li.views_count,
                        'condition': li.condition or '',
                        'location': ' '.join(
                            x for x in (li.location_region, li.location_area) if x
                        ).strip(),
                    }
                    for li in jiji_qs[:25]
                ],
                'collect': collect_results.get('jiji', {}),
            },
            'social': {
                'posts': [
                    {
                        'platform': p.platform,
                        'content': (p.content or '')[:200],
                        'views': p.view_count,
                        'likes': p.like_count,
                        'comments': p.comment_count,
                    }
                    for p in social_qs[:20]
                ],
                'collect': collect_results.get('social', {}),
            },
            'trend_records': trend_summary[:12],
        }
