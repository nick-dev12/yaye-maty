"""
Affichage des données Jumia pour le tableau de bord / Données test.
"""

from __future__ import annotations

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jumia_market_signal_service import JumiaMarketSignalService


class JumiaDisplayService:
    """Prépare le contexte UI Jumia (produits + avis + opportunités)."""

    @classmethod
    def build_context(cls, *, limit_products: int = 40, limit_reviews: int = 60) -> dict:
        router = CollectionModelRouter()
        Product = router.jumia_product_model
        Review = router.jumia_review_model

        products_qs = Product.objects.all().order_by('-scraped_at')
        reviews_qs = (
            Review.objects.select_related('product')
            .all()
            .order_by('-scraped_at')
        )

        products = []
        for p in products_qs[:limit_products]:
            snapshots = list(
                p.price_snapshots.order_by('-captured_at')[:4].values(
                    'price_xof', 'discount_percent', 'stock_status', 'captured_at',
                )
            ) if hasattr(p, 'price_snapshots') else []
            products.append({
                'sku': p.sku,
                'name': p.name,
                'brand': getattr(p, 'brand', '') or '',
                'url': p.product_url,
                'category': p.category,
                'seller': p.seller_name,
                'price_xof': p.price_xof,
                'old_price_xof': p.old_price_xof,
                'discount_percent': getattr(p, 'discount_percent', None),
                'rating_value': p.rating_value,
                'rating_count': p.rating_count,
                'rating_distribution': p.rating_distribution or {},
                'comments_count': p.comments_count,
                'search_keyword': p.search_keyword,
                'catalog_product_slug': getattr(p, 'catalog_product_slug', '') or '',
                'availability': p.availability,
                'stock_status': getattr(p, 'stock_status', 'unknown'),
                'stock_quantity': getattr(p, 'stock_quantity', None),
                'is_in_stock': getattr(p, 'is_in_stock', None),
                'sentiment_summary': getattr(p, 'sentiment_summary', {}) or {},
                'aspect_summary': getattr(p, 'aspect_summary', {}) or {},
                'snapshots': snapshots,
                'scraped_at': p.scraped_at,
            })

        reviews = []
        for r in reviews_qs[:limit_reviews]:
            reviews.append({
                'product_name': r.product.name[:80] if r.product_id else '',
                'product_sku': r.product.sku if r.product_id else '',
                'rating_stars': r.rating_stars,
                'title': r.title,
                'comment_text': r.comment_text,
                'author': r.author,
                'review_date': r.review_date,
                'verified_purchase': r.verified_purchase,
                'search_keyword': getattr(r.product, 'search_keyword', ''),
                'intent': r.intent,
                'sentiment': getattr(r, 'sentiment', '') or '',
                'aspects': getattr(r, 'aspects', {}) or {},
                'failure_tags': getattr(r, 'failure_tags', []) or [],
                'is_analyzed': r.is_analyzed,
            })

        avg_rating = None
        rated = [p for p in products if p['rating_value'] is not None]
        if rated:
            avg_rating = round(sum(p['rating_value'] for p in rated) / len(rated), 2)

        by_keyword: dict[str, int] = {}
        for p in products_qs:
            key = p.search_keyword or '—'
            by_keyword[key] = by_keyword.get(key, 0) + 1

        out_count = products_qs.filter(stock_status='out_of_stock').count()
        low_count = products_qs.filter(stock_status='low_stock').count()
        with_discount = products_qs.exclude(discount_percent__isnull=True).count()

        opportunities = JumiaMarketSignalService.get_opportunities(limit=8)

        return {
            'jumia_products': products,
            'jumia_reviews': reviews,
            'jumia_opportunities': opportunities,
            'jumia_stats': {
                'products_total': products_qs.count(),
                'reviews_total': reviews_qs.count(),
                'avg_rating': avg_rating,
                'by_keyword': by_keyword,
                'with_rating': products_qs.exclude(rating_value__isnull=True).count(),
                'out_of_stock': out_count,
                'low_stock': low_count,
                'with_discount': with_discount,
                'analyzed_reviews': reviews_qs.filter(is_analyzed=True).count(),
            },
            'has_jumia': products_qs.exists(),
        }
