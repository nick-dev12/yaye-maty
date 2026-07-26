"""
Fenêtre temporelle des données Intelligence — flux actuel vs archives.

Le tableau de bord `/intelligence/` n'affiche que les données récentes (cycle campagne,
par défaut 3 jours). L'historique complet reste en base pour la page Archives.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from intelligence.collection_config import get_collection_config
from intelligence.models import DiscoveredQuery, SocialComment, SocialPost, TopPurchaseRecommendation
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.collection_run_context import CollectionRunContext

DEFAULT_LIVE_WINDOW_DAYS = 3


class MarketDataWindowService:
    """Centralise le filtrage temporel live / archive."""

    @classmethod
    def get_live_window_days(cls) -> int:
        """
        Durée du flux actuel affiché sur le tableau de bord.

        Priorité : CAMPAIGN_DURATION_DAYS (si > 0), sinon INTELLIGENCE_LIVE_WINDOW_DAYS,
        sinon 3 jours.
        """
        config = get_collection_config()
        campaign_days = int(config.get('CAMPAIGN_DURATION_DAYS') or 0)
        if campaign_days > 0:
            return campaign_days
        return int(getattr(settings, 'INTELLIGENCE_LIVE_WINDOW_DAYS', DEFAULT_LIVE_WINDOW_DAYS))

    @classmethod
    def get_live_since(cls, *, at: datetime | None = None) -> datetime:
        """Horodatage de début de la fenêtre live (inclus)."""
        reference = at or timezone.now()
        return reference - timedelta(days=cls.get_live_window_days())

    @classmethod
    def get_live_context(cls, *, at: datetime | None = None) -> dict:
        """Métadonnées pour l'UI (bannière, libellés)."""
        since = cls.get_live_since(at=at)
        days = cls.get_live_window_days()
        now = at or timezone.now()
        last_post = (
            SocialPost.objects.filter(scraped_at__gte=since)
            .order_by('-scraped_at')
            .values_list('scraped_at', flat=True)
            .first()
        )
        last_discovered = (
            DiscoveredQuery.objects.filter(discovered_at__gte=since)
            .order_by('-discovered_at')
            .values_list('discovered_at', flat=True)
            .first()
        )
        candidates = [dt for dt in (last_post, last_discovered) if dt]
        last_update = max(candidates) if candidates else None

        return {
            'days': days,
            'since': since,
            'until': now,
            'label': f'Données des {days} derniers jours',
            'short_label': f'Flux actuel · {days} j',
            'last_update': last_update,
            'last_update_label': cls.format_relative(last_update) if last_update else 'Aucune collecte récente',
            'is_live': True,
        }

    @classmethod
    def get_test_tables_context(cls) -> dict:
        """Métadonnées pour la page Données test (tables isolées, sans filtre horaire)."""
        router = CollectionModelRouter(CollectionRunContext.test())
        Post = router.post_model
        Discovered = router.discovered_model
        now = timezone.now()
        last_post = (
            Post.objects.order_by('-scraped_at')
            .values_list('scraped_at', flat=True)
            .first()
        )
        last_discovered = (
            Discovered.objects.order_by('-discovered_at')
            .values_list('discovered_at', flat=True)
            .first()
        )
        candidates = [dt for dt in (last_post, last_discovered) if dt]
        last_update = max(candidates) if candidates else None

        jumia_products = router.jumia_products_qs().count()
        jumia_reviews = router.jumia_reviews_qs().count()
        last_jumia = (
            router.jumia_product_model.objects.order_by('-scraped_at')
            .values_list('scraped_at', flat=True)
            .first()
        )
        if last_jumia:
            last_update = max(last_update, last_jumia) if last_update else last_jumia

        return {
            'days': None,
            'since': None,
            'until': None,
            'label': 'Session test · données isolées',
            'short_label': 'Données test',
            'last_update': last_update,
            'last_update_label': cls.format_relative(last_update) if last_update else 'Aucune donnée test',
            'is_live': False,
            'is_test': True,
            'total_posts': Post.objects.count(),
            'total_discovered': Discovered.objects.count(),
            'total_recommendations': router.recommendations_qs().count(),
            'total_jumia_products': jumia_products,
            'total_jumia_reviews': jumia_reviews,
        }

    @classmethod
    def apply_datetime_range(cls, queryset, field: str, *, since: datetime | None = None, until: datetime | None = None):
        qs = queryset
        if since is not None:
            qs = qs.filter(**{f'{field}__gte': since})
        if until is not None:
            qs = qs.filter(**{f'{field}__lte': until})
        return qs

    @classmethod
    def get_archive_context(
        cls,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        date_start: str = '',
        date_end: str = '',
    ) -> dict:
        """Métadonnées bannière pour la page Archives (même UI que Intelligence)."""
        posts_qs = cls.filter_posts(since=since, until=until)
        last_post = posts_qs.order_by('-scraped_at').values_list('scraped_at', flat=True).first()
        last_discovered = (
            cls.filter_discovered(since=since, until=until)
            .order_by('-discovered_at')
            .values_list('discovered_at', flat=True)
            .first()
        )
        candidates = [dt for dt in (last_post, last_discovered) if dt]
        last_update = max(candidates) if candidates else None

        if date_start and date_end:
            label = f'Archives du {date_start} au {date_end}'
        elif date_start:
            label = f'Archives depuis le {date_start}'
        elif date_end:
            label = f'Archives jusqu’au {date_end}'
        else:
            label = 'Archives historiques — toutes les données'

        return {
            'days': None,
            'since': since,
            'until': until or timezone.now(),
            'date_start': date_start,
            'date_end': date_end,
            'label': label,
            'short_label': 'Archives',
            'last_update': last_update,
            'last_update_label': cls.format_relative(last_update) if last_update else 'Aucune donnée archivée',
            'is_live': False,
            'total_posts': posts_qs.count(),
            'total_discovered': cls.filter_discovered(since=since, until=until).count(),
        }

    @classmethod
    def filter_posts(
        cls,
        queryset=None,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        live_only: bool = False,
    ):
        router = CollectionModelRouter()
        qs = queryset if queryset is not None else router.posts_qs()
        if router.is_test:
            return qs
        if live_only:
            since = cls.get_live_since()
        return cls.apply_datetime_range(qs, 'scraped_at', since=since, until=until)

    @classmethod
    def filter_comments(
        cls,
        queryset=None,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        live_only: bool = False,
    ):
        router = CollectionModelRouter()
        qs = queryset if queryset is not None else router.comments_qs()
        if router.is_test:
            return qs
        if live_only:
            since = cls.get_live_since()
        if since is not None or until is not None:
            qs = qs.filter(models_q_or_created_range(since=since, until=until))
        return qs

    @classmethod
    def filter_discovered(
        cls,
        queryset=None,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        live_only: bool = False,
    ):
        router = CollectionModelRouter()
        qs = queryset if queryset is not None else router.discovered_qs()
        if router.is_test:
            return qs
        if live_only:
            since = cls.get_live_since()
        return cls.apply_datetime_range(qs, 'discovered_at', since=since, until=until)

    @classmethod
    def filter_recommendations(
        cls,
        queryset=None,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        live_only: bool = False,
    ):
        router = CollectionModelRouter()
        qs = queryset if queryset is not None else router.recommendations_qs()
        if router.is_test:
            return qs
        if live_only:
            since = cls.get_live_since()
        return cls.apply_datetime_range(qs, 'computed_at', since=since, until=until)

    @staticmethod
    def format_relative(value: datetime | None) -> str:
        if not value:
            return '—'
        local = timezone.localtime(value)
        now = timezone.localtime(timezone.now())
        delta = now - local
        if delta.total_seconds() < 60:
            return "À l'instant"
        if delta.total_seconds() < 3600:
            minutes = int(delta.total_seconds() // 60)
            return f'il y a {minutes} min'
        if delta.days == 0:
            hours = int(delta.total_seconds() // 3600)
            return f'il y a {hours} h'
        if delta.days == 1:
            return 'hier'
        if delta.days < 7:
            return f'il y a {delta.days} j'
        return local.strftime('%d/%m/%Y %H:%M')


def models_q_or_created_since(since: datetime):
    """Commentaires récents : date publication ou création en base."""
    from django.db.models import Q

    return Q(published_at__gte=since) | Q(published_at__isnull=True, created_at__gte=since)


def models_q_or_created_range(*, since: datetime | None = None, until: datetime | None = None):
    """Filtre commentaires sur published_at ou created_at si absent."""
    from django.db.models import Q

    if since is not None and until is not None:
        return Q(published_at__range=[since, until]) | Q(
            published_at__isnull=True,
            created_at__range=[since, until],
        )
    if since is not None:
        return models_q_or_created_since(since)
    if until is not None:
        return Q(published_at__lte=until) | Q(published_at__isnull=True, created_at__lte=until)
    return Q()
