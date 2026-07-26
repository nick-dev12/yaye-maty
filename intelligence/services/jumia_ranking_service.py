"""Classements produits Jumia — popularité par avis."""

from __future__ import annotations

from intelligence.services.collection_model_router import CollectionModelRouter


class JumiaRankingService:
    """Top produits Jumia par nombre d'avis et note."""

    @classmethod
    def get_top_products(cls, *, limit: int = 10) -> list[dict]:
        router = CollectionModelRouter()
        Product = router.jumia_product_model
        rows = (
            Product.objects.filter(rating_count__gt=0)
            .order_by('-rating_count', '-rating_value', '-scraped_at')[:limit]
        )

        out: list[dict] = []
        for rank, product in enumerate(rows, start=1):
            ratings = int(product.rating_count or 0)
            rating_val = product.rating_value
            subtitle_parts = []
            if product.search_keyword:
                subtitle_parts.append(f'Mot-clé : {product.search_keyword}')
            if product.brand:
                subtitle_parts.append(product.brand)
            subtitle = ' · '.join(subtitle_parts) or product.category or 'Jumia.sn'

            why_parts = [f'{ratings:,} avis clients sur Jumia'.replace(',', ' ')]
            if rating_val:
                why_parts.append(f'note moyenne {rating_val:.1f}/5')

            secondary = []
            if product.price_xof is not None:
                secondary.append({
                    'label': 'Prix',
                    'value': f'{int(product.price_xof):,} FCFA'.replace(',', ' '),
                })
            if product.discount_percent:
                secondary.append({'label': 'Remise', 'value': f'-{int(product.discount_percent)}%'})

            badges = []
            if product.stock_status == 'out_of_stock':
                badges.append({'tone': 'orange', 'label': 'Rupture'})
            elif product.stock_status == 'low_stock':
                badges.append({'tone': 'jaune', 'label': 'Stock faible'})

            out.append({
                'rank': rank,
                'title': product.name[:120],
                'subtitle': subtitle,
                'why_here': ' · '.join(why_parts),
                'primary_value': ratings,
                'primary_label': 'avis',
                'primary_icon': 'star',
                'badges': badges,
                'secondary': secondary,
                'url': product.product_url or '',
                'anchor': '#jumia-marche',
                'source': 'jumia',
            })
        return out
