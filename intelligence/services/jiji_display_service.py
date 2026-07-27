"""Contexte d'affichage Jiji pour tableaux de bord test / live."""

from __future__ import annotations

from django.db.models import Avg, Count, Q, Sum

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jiji_market_signal_service import JijiMarketSignalService
from intelligence.services.jiji_nlp_analysis_service import JijiNlpAnalysisService


class JijiDisplayService:
    @classmethod
    def build_context(cls, *, limit_listings: int = 40, limit_sellers: int = 12) -> dict:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model

        display_qs = JijiNlpAnalysisService.display_listings_qs()
        all_qs = Listing.objects.all()

        listings = []
        for row in display_qs[:limit_listings]:
            listings.append(cls._serialize_listing(row))

        raw_listings = []
        for row in all_qs.order_by('-scraped_at')[:limit_listings]:
            raw_listings.append(cls._serialize_listing(row))

        by_keyword = {
            r['search_keyword'] or '—': r['c']
            for r in display_qs.values('search_keyword').annotate(c=Count('id'))
        }
        aggregates = display_qs.aggregate(
            avg_price=Avg('price_xof'),
            total_views=Sum('views_count'),
            negotiable=Count('id', filter=Q(is_negotiable=True)),
            used=Count('id', filter=Q(condition='used')),
            new=Count('id', filter=Q(condition='new')),
        )

        analyzed_count = all_qs.filter(is_analyzed=True).count()
        agricultural_count = display_qs.count()
        pending_count = all_qs.filter(is_analyzed=False).count()

        return {
            'jiji_listings': listings,
            'jiji_listings_all': raw_listings,
            'jiji_arbitrage': JijiMarketSignalService.get_arbitrage_opportunities(limit=8),
            'jiji_top_sellers': JijiMarketSignalService.get_top_sellers(limit=limit_sellers),
            'jiji_heatmap': JijiMarketSignalService.get_location_heatmap(limit=12),
            'jiji_keyword_demand': JijiMarketSignalService.get_keyword_demand_ranking(limit=10),
            'jiji_stats': {
                'listings_total': all_qs.count(),
                'listings_analyzed': analyzed_count,
                'listings_agricultural': agricultural_count,
                'listings_pending_nlp': pending_count,
                'by_keyword': by_keyword,
                'avg_price': aggregates.get('avg_price'),
                'total_views': int(aggregates.get('total_views') or 0),
                'negotiable': aggregates.get('negotiable') or 0,
                'used': aggregates.get('used') or 0,
                'new': aggregates.get('new') or 0,
            },
            'has_jiji': display_qs.exists(),
            'has_jiji_raw': all_qs.exists(),
        }

    @staticmethod
    def _serialize_listing(row) -> dict:
        return {
            'id': row.pk,
            'listing_id': row.listing_id,
            'url': row.listing_url,
            'title': row.title,
            'category': row.category,
            'price_xof': row.price_xof,
            'is_negotiable': row.is_negotiable,
            'condition': row.condition,
            'condition_label': row.get_condition_display(),
            'location_region': row.location_region,
            'location_area': row.location_area,
            'views_count': row.views_count,
            'seller_name': row.seller_name,
            'seller_member_since': row.seller_member_since,
            'seller_is_verified': row.seller_is_verified,
            'seller_is_premium': row.seller_is_premium,
            'search_keyword': row.search_keyword,
            'catalog_product_slug': row.catalog_product_slug,
            'extracted_product': getattr(row, 'extracted_product', '') or '',
            'nlp_category': getattr(row, 'nlp_category', '') or '',
            'keywords_detected': getattr(row, 'keywords_detected', None) or [],
            'relevance_score': getattr(row, 'relevance_score', None),
            'sentiment': getattr(row, 'sentiment', '') or '',
            'intent': getattr(row, 'intent', '') or '',
            'is_analyzed': getattr(row, 'is_analyzed', False),
            'is_agricultural': getattr(row, 'is_agricultural', True),
            'analysis_status': getattr(row, 'analysis_status', ''),
            'image_url': row.image_url,
        }
