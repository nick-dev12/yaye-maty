"""
Statistiques et cartes domaines Google Trends — page Intelligence / Domaines.
"""

from __future__ import annotations

from django.db.models import Count, Max, Q
from django.utils import timezone

from intelligence.models import DiscoveredQuery, MarketDomain
from intelligence.services.discovery_config_service import DiscoveryConfigService

CARD_TONES = ('orange', 'bleu', 'jaune', 'gris', 'noir')


class DomainsDisplayService:
    """Agrège KPI et mini-cartes par domaine de recherche."""

    @classmethod
    def build_context(cls) -> dict:
        cards = cls.get_domain_cards()
        overview = cls.get_overview(cards)
        return {
            'overview': overview,
            'domain_cards': cards,
            'has_domains': bool(cards),
        }

    @classmethod
    def get_overview(cls, cards: list[dict] | None = None) -> dict:
        cards = cards if cards is not None else cls.get_domain_cards()
        config = DiscoveryConfigService.get_config()

        total_domains = MarketDomain.objects.filter(is_active=True).count()
        selected_count = config.selected_domains.filter(is_active=True).count()
        total_queries = DiscoveredQuery.objects.count()
        rising_count = DiscoveredQuery.objects.filter(
            query_type=DiscoveredQuery.QueryType.RISING,
        ).count()
        last_discovery = DiscoveredQuery.objects.aggregate(
            last=Max('discovered_at'),
        )['last']

        return {
            'total_domains': total_domains,
            'selected_count': selected_count,
            'total_queries': total_queries,
            'rising_count': rising_count,
            'last_discovery_label': cls._format_datetime(last_discovery),
            'timeframe': config.get_timeframe_display(),
            'region': config.region,
            'summary': (
                f'{total_domains} domaine(s) · {selected_count} sélectionné(s) pour la découverte · '
                f'{total_queries} requête(s) collectée(s)'
            ),
            'kpis': [
                {
                    'label': 'Domaines actifs',
                    'value': total_domains,
                    'hint': f'{selected_count} en découverte',
                    'tone': 'orange',
                },
                {
                    'label': 'Requêtes découvertes',
                    'value': cls._fmt(total_queries),
                    'hint': 'Google Trends · Sénégal',
                    'tone': 'bleu',
                },
                {
                    'label': 'Tendances en hausse',
                    'value': rising_count,
                    'hint': 'Requêtes « Rising »',
                    'tone': 'jaune',
                },
                {
                    'label': 'Période configurée',
                    'value': config.get_timeframe_display(),
                    'hint': f'Région {config.region}',
                    'tone': 'gris',
                },
                {
                    'label': 'Dernière découverte',
                    'value': cls._format_date_short(last_discovery),
                    'hint': cls._format_datetime(last_discovery) if last_discovery else 'Jamais lancée',
                    'tone': 'noir',
                },
            ],
        }

    @classmethod
    def get_domain_cards(cls) -> list[dict]:
        config = DiscoveryConfigService.get_config()
        selected_slugs = set(DiscoveryConfigService.get_selected_domain_slugs())

        query_stats = {
            row['domain']: row
            for row in (
                DiscoveredQuery.objects
                .values('domain')
                .annotate(
                    total=Count('id'),
                    top=Count('id', filter=Q(query_type=DiscoveredQuery.QueryType.TOP)),
                    rising=Count('id', filter=Q(query_type=DiscoveredQuery.QueryType.RISING)),
                    last_discovery=Max('discovered_at'),
                )
            )
        }

        cards = []
        domains = MarketDomain.objects.filter(is_active=True).order_by('label')

        for index, domain in enumerate(domains):
            stats = query_stats.get(domain.slug, {})
            total = stats.get('total', 0)
            top = stats.get('top', 0)
            rising = stats.get('rising', 0)
            last = stats.get('last_discovery')
            tone = CARD_TONES[index % len(CARD_TONES)]

            cards.append({
                'id': domain.pk,
                'slug': domain.slug,
                'label': domain.label,
                'short_label': domain.short_label,
                'cat_id': domain.cat_id,
                'seed_count': len(domain.get_seed_list()),
                'top_queries': top,
                'rising_queries': rising,
                'total_queries': total,
                'is_selected': domain.slug in selected_slugs,
                'status_label': (
                    'Inclus dans la veille marché'
                    if domain.slug in selected_slugs
                    else 'Non utilisé pour l\'instant'
                ),
                'status_tone': 'active' if domain.slug in selected_slugs else 'idle',
                'last_discovery_label': cls._format_datetime(last),
                'last_discovery_short': cls._format_date_friendly(last),
                'metrics': cls._build_card_metrics(total, top, rising),
                'tone': tone,
            })

        cards.sort(key=lambda item: item['total_queries'], reverse=True)
        return cards

    @classmethod
    def _build_card_metrics(cls, total: int, top: int, rising: int) -> list[dict]:
        """Indicateurs par domaine — libellés compréhensibles pour non-initiés."""
        return [
            {
                'key': 'total',
                'value': total,
                'label': 'Recherches enregistrées',
                'help': (
                    'Nombre de mots ou expressions que les internautes cherchent sur Google '
                    'dans ce secteur (données collectées pour vous).'
                ),
                'tone': 'primary',
            },
            {
                'key': 'top',
                'value': top,
                'label': 'Très recherchées',
                'help': (
                    'Termes les plus populaires en ce moment — ce que le marché consulte '
                    'le plus sur Google Trends.'
                ),
                'tone': 'bleu',
            },
            {
                'key': 'rising',
                'value': rising,
                'label': 'En forte hausse',
                'help': (
                    'Recherches qui montent rapidement — signaux d\'intérêt émergent '
                    'à surveiller pour anticiper la demande.'
                ),
                'tone': 'jaune',
            },
        ]

    @staticmethod
    def _format_date_friendly(value) -> str:
        if not value:
            return 'Jamais collectée'
        local = timezone.localtime(value)
        months = (
            'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
            'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
        )
        return f'{local.day} {months[local.month - 1]} {local.year}'

    @staticmethod
    def _fmt(value: int) -> str:
        return f'{int(value):,}'.replace(',', '\u202f')

    @staticmethod
    def _format_datetime(value) -> str:
        if not value:
            return '—'
        return timezone.localtime(value).strftime('%d/%m/%Y %H:%M')

    @staticmethod
    def _format_date_short(value) -> str:
        if not value:
            return '—'
        local = timezone.localtime(value)
        months = ('jan', 'fév', 'mar', 'avr', 'mai', 'jun', 'jul', 'aoû', 'sep', 'oct', 'nov', 'déc')
        return f'{local.day} {months[local.month - 1]}'
