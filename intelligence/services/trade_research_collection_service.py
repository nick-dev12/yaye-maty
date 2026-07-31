"""
Collecte ad-hoc pour Trade Intelligence — une requête domaine + mot-clé.
Volumes illimités : seule la durée / should_cancel borne la session.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Callable

from django.conf import settings

from intelligence.controllers.google_trends_controller import GoogleTrendsController
from intelligence.models import JijiListing, JumiaProduct, SocialPost, TrendRecord
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
        }

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
    def collect_jumia(
        cls,
        query: str,
        *,
        product_category: str = '',
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        limits = cls._limits()
        kw = build_ephemeral_keyword(
            query,
            platform='jumia',
            product_category=product_category,
            max_videos=limits['MAX_PRODUCTS'],
            max_comments=limits['MAX_REVIEWS'],
        )
        return JumiaCollectionService.run_for_keywords(
            [kw],
            progress=progress,
            should_cancel=should_cancel,
            test_mode=False,
            skip_homepage=True,
        )

    @classmethod
    def collect_jiji(
        cls,
        query: str,
        *,
        product_category: str = '',
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        limits = cls._limits()
        kw = build_ephemeral_keyword(
            query,
            platform='jiji',
            product_category=product_category,
            max_videos=limits['MAX_LISTINGS'],
        )
        return JijiCollectionService.run_for_keywords(
            [kw],
            progress=progress,
            should_cancel=should_cancel,
            test_mode=False,
            skip_homepage=True,
            skip_nlp=True,
        )

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
        jumia_base = JumiaProduct.objects.filter(search_keyword__iexact=q)
        jiji_base = JijiListing.objects.filter(search_keyword__iexact=q)
        jumia_qs = jumia_base.order_by('-rating_value')[:40]
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
                'stats': price_stats(jumia_prices),
                'products': [
                    {
                        'name': p.name[:120],
                        'price_xof': float(p.price_xof) if p.price_xof else None,
                        'rating': float(p.rating_value) if p.rating_value else None,
                        'reviews': p.rating_count or 0,
                        'brand': p.brand or '',
                    }
                    for p in jumia_qs[:25]
                ],
                'collect': collect_results.get('jumia', {}),
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
