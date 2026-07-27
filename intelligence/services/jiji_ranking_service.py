"""Classements annonces Jiji — demande locale, pertinence NLP."""

from __future__ import annotations

from django.db.models import F

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jiji_nlp_analysis_service import JijiNlpAnalysisService


class JijiRankingService:
    """Top annonces Jiji par vues ou pertinence NLP."""

    @classmethod
    def get_top_listings(cls, *, limit: int = 10) -> list[dict]:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        with_views = Listing.objects.filter(
            is_analyzed=True,
            is_agricultural=True,
            views_count__gt=0,
        ).order_by('-views_count', '-scraped_at')[:limit]
        rows = list(with_views)
        if len(rows) < limit:
            seen_ids = {row.pk for row in rows}
            extra = (
                JijiNlpAnalysisService.display_listings_qs()
                .exclude(pk__in=seen_ids)[: max(0, limit - len(rows))]
            )
            rows.extend(extra)

        return cls._serialize_rows(rows, metric='views')

    @classmethod
    def get_top_analyzed(cls, *, limit: int = 10) -> list[dict]:
        """Top annonces analysées — score pertinence agricole × signal vues."""
        rows = list(JijiNlpAnalysisService.display_listings_qs()[: limit * 2])
        scored = []
        for listing in rows:
            rel = float(listing.relevance_score or 0)
            views = int(listing.views_count or 0)
            score = rel * 100 + min(views, 5000) / 50.0
            scored.append((score, listing))
        scored.sort(key=lambda x: -x[0])
        return cls._serialize_rows([item[1] for item in scored[:limit]], metric='relevance')

    @classmethod
    def _serialize_rows(cls, rows, *, metric: str) -> list[dict]:
        out: list[dict] = []
        for rank, listing in enumerate(rows, start=1):
            views = int(listing.views_count or 0)
            rel = listing.relevance_score
            location = listing.location_area or listing.location_region or ''
            subtitle_parts = []
            if listing.extracted_product:
                subtitle_parts.append(listing.extracted_product)
            elif listing.search_keyword:
                subtitle_parts.append(f'Mot-clé : {listing.search_keyword}')
            if listing.nlp_category:
                subtitle_parts.append(listing.nlp_category.replace('_', ' '))
            if location:
                subtitle_parts.append(location)
            subtitle = ' · '.join(subtitle_parts) or 'Marché local Jiji'

            secondary = []
            if listing.price_xof is not None:
                secondary.append({
                    'label': 'Prix',
                    'value': f'{int(listing.price_xof):,} FCFA'.replace(',', ' '),
                })
            if rel is not None:
                secondary.append({'label': 'Pertinence', 'value': f'{rel:.0%}'})
            if listing.seller_name:
                secondary.append({'label': 'Vendeur', 'value': listing.seller_name[:40]})

            badges = []
            if listing.is_analyzed:
                badges.append({'tone': 'orange', 'label': 'Analysé'})
            if listing.is_negotiable:
                badges.append({'tone': 'bleu', 'label': 'Négociable'})
            if listing.condition == 'used':
                badges.append({'tone': 'gris', 'label': 'Occasion'})
            elif listing.condition == 'new':
                badges.append({'tone': 'jaune', 'label': 'Neuf'})
            if listing.sentiment == 'positive':
                badges.append({'tone': 'jaune', 'label': 'Positif'})
            elif listing.sentiment == 'negative':
                badges.append({'tone': 'gris', 'label': 'Négatif'})

            if metric == 'relevance' and rel is not None:
                primary_value = round(float(rel) * 100, 1)
                primary_label = 'score pertinence'
                why = (
                    f'Annonce analysée — pertinence agricole {primary_value:.0f}/100'
                    + (f', {views:,} vues Jiji'.replace(',', ' ') if views else '')
                )
            else:
                primary_value = views
                primary_label = 'vues'
                why = (
                    f'{views:,} personnes ont consulté cette annonce sur Jiji'
                ).replace(',', ' ')

            out.append({
                'rank': rank,
                'title': listing.title[:120],
                'subtitle': subtitle,
                'why_here': why,
                'primary_value': primary_value,
                'primary_label': primary_label,
                'primary_icon': 'eye' if metric == 'views' else 'star',
                'badges': badges,
                'secondary': secondary,
                'url': listing.listing_url or '',
                'anchor': '#jiji-marche',
                'source': 'jiji',
                'tone': 'orange' if metric == 'relevance' else 'bleu',
            })
        return out
