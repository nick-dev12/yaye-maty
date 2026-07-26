"""
Affichage publications sociales — page Intelligence (#publications).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from intelligence.models import MarketSearchKeyword
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.market_data_window_service import MarketDataWindowService
from intelligence.services.social_display_service import SocialDisplayService


class IntelligencePublicationsService:
    """KPI, filtres et lignes tableau pour la section publications."""

    COMMENTS_GOAL = 20

    @classmethod
    def get_overview(cls, *, since: datetime | None = None, until: datetime | None = None) -> dict:
        router = CollectionModelRouter()
        Post = router.post_model
        Comment = router.comment_model
        posts = MarketDataWindowService.filter_posts(since=since, until=until)
        total = posts.count()
        analyzed = posts.filter(analysis_status=Post.AnalysisStatus.DONE).count()
        pending = posts.filter(analysis_status=Post.AnalysisStatus.PENDING).count()
        with_comments = posts.exclude(Q(comments=[]) | Q(comments__isnull=True)).count()
        full_comments = posts.filter(comments_scraped_count__gte=10).count()

        purchase_posts = posts.filter(purchase_intent_count__gt=0).count()
        total_purchase = posts.aggregate(s=Sum('purchase_intent_count'))['s'] or 0
        avg_demand = posts.aggregate(a=Avg('demand_score'))['a'] or 0
        total_views = posts.aggregate(s=Sum('view_count'))['s'] or 0

        comments_qs = MarketDataWindowService.filter_comments(since=since, until=until)
        if since is not None:
            post_ids = posts.values_list('pk', flat=True)
            comments_qs = comments_qs.filter(post_id__in=post_ids)
        comment_total = comments_qs.count()
        intents = {
            'purchase': comments_qs.filter(intent=Comment.Intent.PURCHASE).count(),
            'info': comments_qs.filter(intent=Comment.Intent.INFO).count(),
            'off_topic': comments_qs.filter(intent=Comment.Intent.OFF_TOPIC).count(),
        }

        return {
            'total': total,
            'analyzed': analyzed,
            'pending': pending,
            'with_comments': with_comments,
            'full_comments': full_comments,
            'purchase_posts': purchase_posts,
            'total_purchase_intents': total_purchase,
            'avg_demand': round(avg_demand, 1),
            'total_views': total_views,
            'comment_total': comment_total,
            'intents': intents,
            'kpis': [
                {
                    'label': 'Publications',
                    'value': cls._fmt(total),
                    'hint': f'{analyzed} analysées · {pending} en attente',
                    'tone': 'orange',
                },
                {
                    'label': 'Commentaires collectés',
                    'value': cls._fmt(comment_total),
                    'hint': f'{with_comments} publications avec commentaires · objectif 10–20',
                    'tone': 'bleu',
                },
                {
                    'label': "Intentions d'achat",
                    'value': cls._fmt(intents['purchase']),
                    'hint': f'{purchase_posts} publications concernées',
                    'tone': 'jaune',
                },
                {
                    'label': 'Score demande moy.',
                    'value': f'{avg_demand:.1f}',
                    'hint': f'Vues totales : {cls._fmt(total_views)}',
                    'tone': 'noir',
                },
                {
                    'label': 'Couverture commentaires',
                    'value': f'{round(with_comments / total * 100) if total else 0}%',
                    'hint': f'{full_comments} posts avec ≥10 commentaires',
                    'tone': 'gris',
                },
            ],
            'summary': (
                f'{total} publications réseaux · {comment_total} commentaires analysés · '
                f'{intents["purchase"]} signaux d\'achat détectés'
            ),
        }

    @classmethod
    def get_sparkline_values(
        cls,
        *,
        days: int = 7,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[int]:
        """Publications collectées par jour — sparkline métriques."""
        today = timezone.localdate()
        if since is not None:
            days = max(1, min(days, (today - timezone.localtime(since).date()).days + 1))
        values = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            qs = MarketDataWindowService.filter_posts(since=since, until=until).filter(
                scraped_at__date=day,
            )
            values.append(qs.count())
        return values

    @classmethod
    def get_keyword_filters(
        cls,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict]:
        """Compteurs par mot-clé Paramètres (MarketSearchKeyword)."""
        posts = MarketDataWindowService.filter_posts(since=since, until=until)
        source_map = SocialDisplayService.get_keyword_source_map()
        known_urls = set(source_map.keys())

        filters: list[dict] = []
        for source_url, meta in source_map.items():
            count = posts.filter(source_url=source_url).count()
            if count > 0 or meta['is_active']:
                filters.append({
                    'id': meta['id'],
                    'keyword': meta['keyword'],
                    'label': meta['label'],
                    'count': count,
                    'is_active': meta['is_active'],
                })

        filters.sort(key=lambda row: (-row['count'], row['keyword'].lower()))

        other_count = posts.exclude(source_url__in=known_urls).count() if known_urls else posts.count()
        if other_count:
            filters.append({
                'id': None,
                'keyword': '',
                'label': 'Autres sources',
                'count': other_count,
                'is_active': True,
            })

        return filters

    @classmethod
    def get_posts_for_table(
        cls,
        *,
        category: str | None = None,
        keyword_id: int | None = None,
        keyword_other: bool = False,
        platform: str | None = None,
        sentiment: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Lignes enrichies pour le tableau publications."""
        queryset = MarketDataWindowService.filter_posts(since=since, until=until).order_by(
            '-demand_score', '-analyzed_at', '-scraped_at',
        )
        if platform:
            queryset = queryset.filter(platform=platform)

        if keyword_other:
            source_map = SocialDisplayService.get_keyword_source_map()
            queryset = queryset.exclude(source_url__in=source_map.keys())
        elif keyword_id is not None:
            keyword = MarketSearchKeyword.objects.filter(pk=keyword_id).first()
            if keyword:
                queryset = queryset.filter(source_url=keyword.build_search_url())

        if category is not None and category != '':
            queryset = queryset.filter(category=category)
        elif category == '':
            queryset = queryset.filter(category='')

        if sentiment in SocialDisplayService.SENTIMENT_LABELS:
            queryset = queryset.filter(sentiment=sentiment)

        source_map = SocialDisplayService.get_keyword_source_map()
        rows = []
        for post in queryset[:limit]:
            scraped = post.comments_scraped_count or len(post.comments or [])
            goal = cls.COMMENTS_GOAL
            comment_pct = min(100, round(scraped / goal * 100)) if goal else 0
            content_short = post.content[:80] + ('…' if len(post.content) > 80 else '')
            keyword_meta = SocialDisplayService.resolve_keyword_for_source(post.source_url, source_map)
            subject_line = cls._build_subject_line(post)
            category_label = SocialDisplayService.CATEGORY_LABELS.get(
                post.category, post.category or 'Non classé',
            )

            rows.append({
                'id': post.pk,
                'content': post.content,
                'content_short': content_short,
                'subject_line': subject_line,
                'topic_summary': cls._build_topic_summary(post, category_label, keyword_meta),
                'author_display': f'@{post.author}' if post.author else 'Auteur inconnu',
                'platform': post.platform,
                'platform_label': post.get_platform_display(),
                'search_keyword': keyword_meta.get('keyword', ''),
                'search_keyword_label': keyword_meta.get('label') or 'Source non liée',
                'view_count_fmt': cls._fmt(post.view_count),
                'like_count_fmt': cls._fmt(post.like_count),
                'share_count_fmt': cls._fmt(post.share_count),
                'save_count_fmt': cls._fmt(post.save_count),
                'engagement_summary': cls._engagement_summary(post),
                'comments_scraped': scraped,
                'comments_label': f'{scraped}/{goal}',
                'comments_pct': comment_pct,
                'comments_tone': cls._comments_tone(scraped),
                'purchase_intents': post.purchase_intent_count or 0,
                'purchase_label': cls._purchase_label(post.purchase_intent_count or 0),
                'purchase_tone': 'orange' if (post.purchase_intent_count or 0) > 0 else 'gris',
                'category_label': category_label,
                'sentiment': post.sentiment,
                'sentiment_label': SocialDisplayService.SENTIMENT_LABELS.get(
                    post.sentiment, post.sentiment or 'En attente',
                ),
                'demand_score': post.demand_score,
                'demand_label': cls._demand_label(post.demand_score),
                'demand_tone': cls._demand_tone(post.demand_score),
                'status_label': post.get_analysis_status_display(),
                'status_tone': cls._status_tone(post.analysis_status),
                'published_label': cls._format_date(post.published_at or post.scraped_at),
                'post_url': post.post_url,
                'has_url': bool(post.post_url),
            })

        return rows

    @classmethod
    def _build_subject_line(cls, post) -> str:
        """Libellé court : de quoi parle la publication."""
        if getattr(post, 'extracted_product', ''):
            return post.extracted_product[:80]
        keywords = post.keywords or []
        if keywords:
            return ', '.join(str(k) for k in keywords[:2])[:80]
        preview = post.content.strip()[:72]
        return preview + ('…' if len(post.content.strip()) > 72 else '')

    @classmethod
    def _build_topic_summary(cls, post, category_label: str, keyword_meta: dict) -> str:
        """Phrase de contexte pour interpréter la ligne."""
        keyword = keyword_meta.get('keyword') or 'veille générale'
        platform = post.get_platform_display()
        parts = [f'Contenu {platform} collecté via « {keyword} »']
        if category_label and category_label != 'Non classé':
            parts.append(f'thème {category_label.lower()}')
        if post.purchase_intent_count:
            parts.append(f'{post.purchase_intent_count} commentaire(s) avec intention d\'achat')
        return ' · '.join(parts)

    @staticmethod
    def _engagement_summary(post) -> str:
        parts = []
        if post.view_count:
            parts.append(f'{IntelligencePublicationsService._fmt(post.view_count)} vues')
        if post.like_count:
            parts.append(f'{IntelligencePublicationsService._fmt(post.like_count)} likes')
        if post.save_count:
            parts.append(f'{IntelligencePublicationsService._fmt(post.save_count)} favoris')
        return ' · '.join(parts) if parts else 'Peu d\'engagement mesuré'

    @staticmethod
    def _fmt(value: int | None) -> str:
        if value is None:
            return '—'
        return f'{int(value):,}'.replace(',', '\u202f')

    @staticmethod
    def _format_date(value) -> str:
        if not value:
            return '—'
        local = timezone.localtime(value)
        return local.strftime('%d/%m/%Y')

    @staticmethod
    def _comments_tone(scraped: int) -> str:
        if scraped >= 10:
            return 'success'
        if scraped >= 1:
            return 'warning'
        return 'muted'

    @staticmethod
    def _purchase_label(count: int) -> str:
        if count >= 3:
            return 'Forte'
        if count >= 1:
            return 'Oui'
        return '—'

    @staticmethod
    def _demand_label(score: int) -> str:
        if score >= 4:
            return 'Forte demande'
        if score >= 2:
            return 'Demande modérée'
        return 'Faible'

    @staticmethod
    def _demand_tone(score: int) -> str:
        if score >= 4:
            return 'high'
        if score >= 2:
            return 'mid'
        return 'low'

    @staticmethod
    def _status_tone(status: str) -> str:
        from intelligence.models import SocialPost
        return {
            SocialPost.AnalysisStatus.DONE: 'done',
            SocialPost.AnalysisStatus.PENDING: 'pending',
            SocialPost.AnalysisStatus.PROCESSING: 'processing',
            SocialPost.AnalysisStatus.FAILED: 'failed',
        }.get(status, 'pending')
