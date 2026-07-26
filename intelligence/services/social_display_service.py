"""
Service d'affichage des publications sociales — page Intelligence.
"""

from __future__ import annotations

from django.db.models import Count

from intelligence.models import MarketSearchKeyword, SocialPost


class SocialDisplayService:
    """Prépare filtres et tableau des publications NLP."""

    CATEGORY_LABELS = {
        'irrigation': 'Irrigation',
        'solaire_pompage': 'Solaire & pompage',
        'tracteurs_machinisme': 'Tracteurs & machinisme',
        'semences_engrais': 'Semences & engrais',
        'elevage_alimentation': 'Élevage & alimentation',
        'marche_prix': 'Marché & prix',
        'formation_conseil': 'Formation & conseil',
        'autre': 'Autre',
    }

    SENTIMENT_LABELS = {
        'positive': 'Positif',
        'negative': 'Négatif',
        'neutral': 'Neutre',
    }

    @classmethod
    def get_category_filters(cls) -> list[dict]:
        """Compteurs par catégorie pour les filtres."""
        counts = (
            SocialPost.objects
            .filter(analysis_status=SocialPost.AnalysisStatus.DONE)
            .exclude(category='')
            .values('category')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        filters = [
            {
                'slug': row['category'],
                'label': cls.CATEGORY_LABELS.get(row['category'], row['category']),
                'count': row['count'],
            }
            for row in counts
        ]

        uncategorized = SocialPost.objects.filter(
            analysis_status=SocialPost.AnalysisStatus.DONE,
            category='',
        ).count()
        if uncategorized:
            filters.append({
                'slug': '',
                'label': 'Non classé',
                'count': uncategorized,
            })

        return filters

    @classmethod
    def get_posts_for_table(
        cls,
        *,
        category: str | None = None,
        platform: str | None = None,
        sentiment: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Lignes du tableau publications sociales."""
        queryset = SocialPost.objects.all().order_by('-demand_score', '-analyzed_at', '-scraped_at')

        if category is not None and category != '':
            queryset = queryset.filter(category=category)
        elif category == '':
            queryset = queryset.filter(category='')

        if platform in SocialPost.Platform.values:
            queryset = queryset.filter(platform=platform)

        if sentiment in cls.SENTIMENT_LABELS:
            queryset = queryset.filter(sentiment=sentiment)

        rows = []
        for post in queryset[:limit]:
            rows.append({
                'id': post.pk,
                'content': post.content,
                'content_short': post.content[:80] + ('…' if len(post.content) > 80 else ''),
                'platform': post.platform,
                'platform_label': post.get_platform_display(),
                'author': post.author,
                'platform_post_id': post.platform_post_id,
                'hashtags': post.hashtags or [],
                'hashtags_display': ', '.join(f'#{tag}' for tag in (post.hashtags or [])[:4]),
                'category': post.category,
                'category_label': cls.CATEGORY_LABELS.get(post.category, post.category or '—'),
                'sentiment': post.sentiment,
                'sentiment_label': cls.SENTIMENT_LABELS.get(post.sentiment, post.sentiment or '—'),
                'keywords': post.keywords or [],
                'keywords_display': ', '.join((post.keywords or [])[:4]),
                'view_count': post.view_count,
                'like_count': post.like_count,
                'save_count': post.save_count,
                'demand_score': post.demand_score,
                'purchase_intent_count': post.purchase_intent_count,
                'engagement_display': cls._format_engagement(post),
                'analysis_status': post.analysis_status,
                'status_label': post.get_analysis_status_display(),
                'scraped_at': post.scraped_at,
                'analyzed_at': post.analyzed_at,
            })

        return rows

    @staticmethod
    def _format_engagement(post) -> str:
        parts = []
        if post.view_count:
            parts.append(f'{post.view_count:,}'.replace(',', ' ') + ' vues')
        if post.like_count:
            parts.append(f'{post.like_count:,}'.replace(',', ' ') + ' likes')
        if post.save_count:
            parts.append(f'{post.save_count:,}'.replace(',', ' ') + ' favoris')
        return ' · '.join(parts) if parts else '—'

    @classmethod
    def get_keyword_source_map(cls) -> dict[str, dict]:
        """Associe l'URL de recherche Top-Down au mot-clé Paramètres."""
        mapping: dict[str, dict] = {}
        for keyword in MarketSearchKeyword.objects.all().order_by('keyword'):
            mapping[keyword.build_search_url()] = {
                'id': keyword.pk,
                'keyword': keyword.keyword,
                'label': keyword.display_label,
                'is_active': keyword.is_active,
            }
        return mapping

    @classmethod
    def resolve_keyword_for_source(cls, source_url: str, source_map: dict | None = None) -> dict:
        """Retourne le mot-clé lié à une publication (via source_url)."""
        if not source_url:
            return {}
        source_map = source_map or cls.get_keyword_source_map()
        return source_map.get(source_url, {})

    @classmethod
    def get_active_filters(cls, request) -> dict:
        """Lit les filtres depuis les paramètres GET."""
        raw_category = request.GET.get('social_category')
        if raw_category is None:
            category = None
        elif raw_category == 'none':
            category = ''
        else:
            category = raw_category

        raw_keyword = request.GET.get('social_keyword', '').strip()
        keyword_id = None
        keyword_other = False
        if raw_keyword == 'other':
            keyword_other = True
        elif raw_keyword.isdigit():
            keyword_id = int(raw_keyword)

        platform = request.GET.get('social_platform', '')
        sentiment = request.GET.get('social_sentiment', '')

        return {
            'category': category,
            'keyword_id': keyword_id,
            'keyword_other': keyword_other,
            'platform': platform if platform in SocialPost.Platform.values else '',
            'sentiment': sentiment if sentiment in cls.SENTIMENT_LABELS else '',
        }
