"""Classements annonces Jiji — demande locale par vues."""

from __future__ import annotations

from intelligence.services.collection_model_router import CollectionModelRouter


class JijiRankingService:
    """Top annonces Jiji par nombre de vues."""

    @classmethod
    def get_top_listings(cls, *, limit: int = 10) -> list[dict]:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        with_views = Listing.objects.filter(views_count__gt=0).order_by(
            '-views_count', '-scraped_at',
        )[:limit]
        rows = list(with_views)
        if len(rows) < limit:
            seen_ids = {row.pk for row in rows}
            extra = (
                Listing.objects.exclude(pk__in=seen_ids)
                .order_by('-scraped_at')[: max(0, limit - len(rows))]
            )
            rows.extend(extra)

        out: list[dict] = []
        for rank, listing in enumerate(rows, start=1):
            views = int(listing.views_count or 0)
            location = listing.location_area or listing.location_region or ''
            subtitle_parts = []
            if listing.search_keyword:
                subtitle_parts.append(f'Mot-clé : {listing.search_keyword}')
            if location:
                subtitle_parts.append(location)
            subtitle = ' · '.join(subtitle_parts) or 'Marché local Jiji'

            secondary = []
            if listing.price_xof is not None:
                secondary.append({
                    'label': 'Prix',
                    'value': f'{int(listing.price_xof):,} FCFA'.replace(',', ' '),
                })
            if listing.seller_name:
                secondary.append({'label': 'Vendeur', 'value': listing.seller_name[:40]})

            badges = []
            if listing.is_negotiable:
                badges.append({'tone': 'bleu', 'label': 'Négociable'})
            if listing.condition == 'used':
                badges.append({'tone': 'gris', 'label': 'Occasion'})
            elif listing.condition == 'new':
                badges.append({'tone': 'jaune', 'label': 'Neuf'})

            out.append({
                'rank': rank,
                'title': listing.title[:120],
                'subtitle': subtitle,
                'why_here': (
                    f'{views:,} personnes ont consulté cette annonce sur Jiji'
                ).replace(',', ' '),
                'primary_value': views,
                'primary_label': 'vues',
                'primary_icon': 'eye',
                'badges': badges,
                'secondary': secondary,
                'url': listing.listing_url or '',
                'anchor': '#jiji-marche',
                'source': 'jiji',
            })
        return out
