"""Classements publications réseaux — vues, likes, demande."""

from __future__ import annotations

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.market_data_window_service import MarketDataWindowService


class SocialRankingService:
    """Top N publications par métrique d'engagement."""

    METRIC_ORDER = {
        'views': ('-view_count', '-demand_score', '-scraped_at'),
        'likes': ('-like_count', '-view_count', '-scraped_at'),
        'demand': ('-demand_score', '-view_count', '-scraped_at'),
    }

    @classmethod
    def get_top_posts(
        cls,
        *,
        metric: str = 'views',
        limit: int = 10,
        since=None,
        until=None,
    ) -> list[dict]:
        router = CollectionModelRouter()
        Post = router.post_model
        order = cls.METRIC_ORDER.get(metric, cls.METRIC_ORDER['views'])
        qs = MarketDataWindowService.filter_posts(Post.objects.all(), since=since, until=until)
        rows = qs.order_by(*order)[:limit]

        out: list[dict] = []
        for rank, post in enumerate(rows, start=1):
            title = (post.content or post.author or 'Publication')[:120].strip()
            if len((post.content or '')) > 120:
                title = title.rstrip() + '…'
            platform_label = post.get_platform_display()
            keyword = ''
            if post.keywords:
                keyword = post.keywords[0] if isinstance(post.keywords[0], str) else str(post.keywords[0])

            if metric == 'likes':
                primary_value = int(post.like_count or 0)
                primary_label = 'j\'aime'
                why = (
                    f'{primary_value:,} personnes ont aimé cette publication {platform_label}'
                ).replace(',', ' ')
            elif metric == 'demand':
                primary_value = int(post.demand_score or 0)
                primary_label = 'score demande'
                why = (
                    f'Score de demande {primary_value}/5 — '
                    f'{post.purchase_intent_count or 0} intention(s) d\'achat détectée(s)'
                )
            else:
                primary_value = int(post.view_count or 0)
                primary_label = 'vues'
                why = (
                    f'{primary_value:,} vues sur {platform_label}'
                ).replace(',', ' ')

            secondary = []
            if post.like_count:
                secondary.append({'label': 'J\'aime', 'value': str(post.like_count)})
            if post.view_count and metric != 'views':
                secondary.append({'label': 'Vues', 'value': str(post.view_count)})
            if post.save_count:
                secondary.append({'label': 'Sauvegardes', 'value': str(post.save_count)})

            out.append({
                'rank': rank,
                'title': title or f'Publication {platform_label}',
                'subtitle': f'{platform_label}' + (f' · {keyword}' if keyword else ''),
                'why_here': why,
                'primary_value': primary_value,
                'primary_label': primary_label,
                'primary_icon': 'eye' if metric == 'views' else ('heart' if metric == 'likes' else 'star'),
                'badges': cls._badges(post),
                'secondary': secondary,
                'url': post.post_url or post.source_url or '',
                'anchor': '#publications',
                'source': 'social',
            })
        return out

    @staticmethod
    def _badges(post) -> list[dict]:
        badges: list[dict] = []
        if (post.purchase_intent_count or 0) > 0:
            badges.append({'tone': 'orange', 'label': 'Veut acheter'})
        if (post.demand_score or 0) >= 4:
            badges.append({'tone': 'jaune', 'label': 'Forte demande'})
        return badges
