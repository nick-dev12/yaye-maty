"""
Service d'affichage des requêtes découvertes par domaine.
"""

from intelligence.models import MarketDomain
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.discovery_config_service import DiscoveryConfigService
from intelligence.services.market_data_window_service import MarketDataWindowService
from yayematy_project.utils.chart_utils import build_donut_segments


class DiscoveredDisplayService:
    """Prépare les données de découverte pour les templates."""

    COLORS = ['orange', 'bleu', 'jaune', 'noir', 'gris']
    CHART_COLORS = ['#F25C19', '#2E7DB5', '#F0B429', '#1A1A1A', '#8C8C8C', '#FF8A50']

    @classmethod
    def _domain_map(cls) -> dict[str, MarketDomain]:
        return DiscoveryConfigService.get_domain_map()

    @classmethod
    def _discovered_model(cls):
        return CollectionModelRouter().discovered_model

    @classmethod
    def get_by_domain(cls, limit_per_domain: int = 50, *, since=None, until=None) -> list[dict]:
        """Regroupe les requêtes par domaine actif en base."""
        Discovered = cls._discovered_model()
        result = []
        domain_map = cls._domain_map()

        for slug, market_domain in domain_map.items():
            top_qs = MarketDataWindowService.filter_discovered(
                Discovered.objects.filter(
                    domain=slug,
                    query_type=Discovered.QueryType.TOP,
                ),
                since=since,
                until=until,
            )
            rising_qs = MarketDataWindowService.filter_discovered(
                Discovered.objects.filter(
                    domain=slug,
                    query_type=Discovered.QueryType.RISING,
                ),
                since=since,
                until=until,
            )

            if not top_qs.exists() and not rising_qs.exists():
                continue

            result.append({
                'key': slug,
                'label': market_domain.label,
                'short_label': market_domain.short_label,
                'cat_id': market_domain.cat_id,
                'top': list(top_qs.order_by('-discovered_at', 'query')[:limit_per_domain]),
                'rising': list(rising_qs.order_by('-discovered_at', 'query')[:limit_per_domain]),
                'total': top_qs.count() + rising_qs.count(),
                'top_count': top_qs.count(),
            })

        return result

    @classmethod
    def get_top_queries(cls, limit: int = 8, *, since=None, until=None) -> list[dict]:
        """Meilleures requêtes pour le graphique."""
        Discovered = cls._discovered_model()
        queries = (
            MarketDataWindowService.filter_discovered(
                Discovered.objects.filter(query_type=Discovered.QueryType.TOP),
                since=since,
                until=until,
            )
            .order_by('-discovered_at', 'query')[:limit]
        )
        domain_map = cls._domain_map()
        results = []
        max_rank = len(queries) or 1

        for i, q in enumerate(queries):
            md = domain_map.get(q.domain)
            label = md.short_label if md else q.domain
            results.append({
                'query': q.query,
                'domain': q.domain,
                'domain_label': label,
                'score': max(10, 100 - (i * (80 // max_rank))),
                'color': cls.COLORS[i % len(cls.COLORS)],
                'percent': round(((max_rank - i) / max_rank) * 100),
                'discovered_at': q.discovered_at,
            })

        return results

    @classmethod
    def get_domain_chart_data(cls, discovered_by_domain: list[dict]) -> dict:
        """Données donut par domaine."""
        if not discovered_by_domain:
            return {
                'total': 0,
                'segments': build_donut_segments([]),
                'items': [],
            }

        total = sum(d['total'] for d in discovered_by_domain) or 1
        items = []

        for i, domain in enumerate(discovered_by_domain):
            pct = (domain['total'] / total) * 100
            hex_color = cls.CHART_COLORS[i % len(cls.CHART_COLORS)]
            items.append({
                'key': domain['key'],
                'label': domain['short_label'],
                'count': domain['total'],
                'percent': round(pct, 1),
                'color': f'chart-{i}',
                'hex_color': hex_color,
                'stroke': hex_color,
            })

        return {
            'total': sum(d['total'] for d in discovered_by_domain),
            'segments': build_donut_segments(items, stroke_key='stroke'),
            'items': items,
        }

    @classmethod
    def get_all_for_table(cls, *, since=None, until=None) -> list[dict]:
        """Liste complète pour le tableau."""
        Discovered = cls._discovered_model()
        domain_map = cls._domain_map()
        queries = MarketDataWindowService.filter_discovered(
            Discovered.objects.all(),
            since=since,
            until=until,
        ).order_by('-discovered_at', 'domain', 'query')
        rows = []

        for q in queries:
            md = domain_map.get(q.domain)
            rows.append({
                'query': q.query,
                'domain': q.domain,
                'domain_label': md.short_label if md else q.domain,
                'query_type': q.get_query_type_display(),
                'discovered_at': q.discovered_at,
            })

        return rows

    @classmethod
    def get_overview_stats(cls, *, since=None, until=None) -> list[dict]:
        Discovered = cls._discovered_model()
        base_qs = MarketDataWindowService.filter_discovered(since=since, until=until)
        discovered_count = base_qs.count()
        domain_count = MarketDomain.objects.filter(is_active=True).count()
        last = base_qs.order_by('-discovered_at').first()
        rising_count = base_qs.filter(
            query_type=Discovered.QueryType.RISING,
        ).count()

        return [
            {'icon': 'talks', 'value': domain_count, 'label': 'Domaines configurés'},
            {'icon': 'meetings', 'value': discovered_count, 'label': 'Requêtes découvertes'},
            {'icon': 'users', 'value': rising_count, 'label': 'Tendances en hausse'},
            {
                'icon': 'teams',
                'value': last.discovered_at.strftime('%d/%m') if last else '—',
                'label': 'Dernière découverte',
            },
        ]

    @classmethod
    def get_rising_preview(cls, limit: int = 5, *, since=None, until=None) -> list[dict]:
        """Aperçu des tendances en hausse pour le widget meetings."""
        Discovered = cls._discovered_model()
        domain_map = cls._domain_map()
        queries = (
            MarketDataWindowService.filter_discovered(
                Discovered.objects.filter(query_type=Discovered.QueryType.RISING),
                since=since,
                until=until,
            )
            .order_by('-discovered_at')[:limit]
        )
        tones = ['orange', 'bleu', 'jaune', 'noir', 'gris']
        results = []
        for i, q in enumerate(queries):
            md = domain_map.get(q.domain)
            results.append({
                'query': q.query,
                'domain_label': md.short_label if md else q.domain,
                'time': q.discovered_at.strftime('%H:%M') if q.discovered_at else '—',
                'tone': tones[i % len(tones)],
            })
        return results

    @classmethod
    def get_activity_chart(cls, *, since=None, until=None, days: int = 7) -> dict:
        """Activité basée sur les découvertes sur N jours."""
        from datetime import timedelta

        from django.db.models import Count
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        Discovered = cls._discovered_model()
        today = timezone.localdate()
        if since is not None:
            start = max(timezone.localtime(since).date(), today - timedelta(days=days - 1))
        else:
            start = today - timedelta(days=days - 1)
        counts = {
            row['day']: row['total']
            for row in (
                MarketDataWindowService.filter_discovered(
                    Discovered.objects.filter(discovered_at__date__gte=start),
                    since=since,
                    until=until,
                )
                .annotate(day=TruncDate('discovered_at'))
                .values('day')
                .annotate(total=Count('id'))
            )
        }
        labels = ['LUN', 'MAR', 'MER', 'JEU', 'VEN', 'SAM', 'DIM']
        bars = []
        max_count = 1
        span_days = (today - start).days + 1
        for offset in range(span_days):
            day = start + timedelta(days=offset)
            count = counts.get(day, 0)
            max_count = max(max_count, count)
            bars.append({'label': labels[day.weekday()], 'count': count})

        for bar in bars:
            bar['height'] = max(8, round((bar['count'] / max_count) * 100)) if max_count else 8
            bar['active'] = bar['count'] > 0

        total_week = sum(b['count'] for b in bars)
        percent = min(100, round((total_week / max(max_count * 7, 1)) * 100)) if total_week else 0
        if total_week and percent < 12:
            percent = 35 + min(40, total_week * 5)

        return {
            'percent': percent if total_week else 0,
            'bars': bars,
            'total_week': total_week,
        }
