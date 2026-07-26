"""Contexte d'affichage Jiji pour tableaux de bord test / live."""

from __future__ import annotations

from django.db.models import Avg, Count, Q, Sum

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jiji_market_signal_service import JijiMarketSignalService


class JijiDisplayService:
    @classmethod
    def build_context(cls, *, limit_listings: int = 40, limit_sellers: int = 12) -> dict:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model

        qs = Listing.objects.all().order_by('-views_count', '-scraped_at')
        listings = []
        for row in qs[:limit_listings]:
            listings.append({
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
                'image_url': row.image_url,
            })

        by_keyword = {
            r['search_keyword'] or '—': r['c']
            for r in Listing.objects.values('search_keyword').annotate(c=Count('id'))
        }
        aggregates = Listing.objects.aggregate(
            avg_price=Avg('price_xof'),
            total_views=Sum('views_count'),
            negotiable=Count('id', filter=Q(is_negotiable=True)),
            used=Count('id', filter=Q(condition='used')),
            new=Count('id', filter=Q(condition='new')),
        )

        return {
            'jiji_listings': listings,
            'jiji_arbitrage': JijiMarketSignalService.get_arbitrage_opportunities(limit=8),
            'jiji_top_sellers': JijiMarketSignalService.get_top_sellers(limit=limit_sellers),
            'jiji_heatmap': JijiMarketSignalService.get_location_heatmap(limit=12),
            'jiji_keyword_demand': JijiMarketSignalService.get_keyword_demand_ranking(limit=10),
            'jiji_stats': {
                'listings_total': Listing.objects.count(),
                'by_keyword': by_keyword,
                'avg_price': aggregates.get('avg_price'),
                'total_views': int(aggregates.get('total_views') or 0),
                'negotiable': aggregates.get('negotiable') or 0,
                'used': aggregates.get('used') or 0,
                'new': aggregates.get('new') or 0,
            },
            'has_jiji': Listing.objects.exists(),
        }
