"""
Contrôleur de la page Intelligence de marché.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from intelligence.services.archives_display_service import ArchivesDisplayService
from intelligence.services.discovered_display_service import DiscoveredDisplayService
from intelligence.services.discovery_config_service import DiscoveryConfigService
from intelligence.services.intelligence_publications_service import IntelligencePublicationsService
from intelligence.services.market_data_window_service import MarketDataWindowService
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService
from intelligence.services.social_display_service import SocialDisplayService
from intelligence.services.social_post_service import SocialPostService


class IntelligencePageController:
    """Page centrale d'intelligence de marché agricole."""

    def __init__(self, request):
        self.request = request

    def index(self):
        if self.request.method == 'POST' and self.request.POST.get('action') == 'discover':
            return self._handle_discovery()

        return self._render_page(mode='live')

    def archives(self):
        """Même tableau de bord que Intelligence — données historiques."""
        return self._render_page(mode='archives')

    def test_results(self):
        """Tableau de bord Intelligence filtré sur la dernière session de test."""
        return self._render_page(mode='test')

    def _handle_discovery(self):
        try:
            stats = DiscoveryConfigService.run_discovery()
        except (ValueError, RuntimeError) as exc:
            messages.error(self.request, str(exc))
            return self._render_page(mode='live')

        config = DiscoveryConfigService.get_config()
        selected = list(config.selected_domains.values_list('label', flat=True))
        messages.success(
            self.request,
            f'Découverte réussie — {stats["total"]} requête(s) pour '
            f'{", ".join(selected) or "les domaines configurés"}.',
        )
        return HttpResponseRedirect(reverse('intelligence:index') + '#decouvertes')

    def _render_page(self, *, mode='live'):
        ctx_token = None
        if mode == 'test':
            from intelligence.services.collection_run_context import (
                CollectionRunContext,
                set_collection_context,
            )
            ctx_token = set_collection_context(CollectionRunContext.test())

        try:
            response = self._build_render_context(mode=mode)
            # Rendu synchrone : le contextvar test doit rester actif pendant le template.
            if hasattr(response, 'render') and callable(response.render):
                response.render()
            return response
        finally:
            if ctx_token is not None:
                from intelligence.services.collection_run_context import reset_collection_context
                reset_collection_context(ctx_token)

    def _build_render_context(self, *, mode='live'):
        from intelligence.services.collection_test_context_service import CollectionTestContextService

        archive_filters = None
        if mode == 'live':
            data_window = MarketDataWindowService.get_live_context()
            since = data_window['since']
            until = None
            chart_days = data_window['days']
        elif mode == 'test':
            data_window = MarketDataWindowService.get_test_tables_context()
            since = None
            until = None
            chart_days = 7
        else:
            archive_filters = ArchivesDisplayService.parse_date_filters(self.request)
            since = archive_filters.since
            until = archive_filters.until
            data_window = MarketDataWindowService.get_archive_context(
                since=since,
                until=until,
                date_start=archive_filters.date_start,
                date_end=archive_filters.date_end,
            )
            chart_days = 7
            if since and until:
                span = (timezone.localtime(until).date() - timezone.localtime(since).date()).days + 1
                chart_days = max(1, min(7, span))

        discovered_by_domain = DiscoveredDisplayService.get_by_domain(since=since, until=until)
        chart_data = DiscoveredDisplayService.get_domain_chart_data(discovered_by_domain)
        config = DiscoveryConfigService.get_config()
        selected_domains = list(config.selected_domains.filter(is_active=True))
        social_filters = SocialDisplayService.get_active_filters(self.request)
        social_stats = SocialPostService.get_overview_stats()
        publications_overview = IntelligencePublicationsService.get_overview(since=since, until=until)
        top_recommendations = PurchaseRecommendationService.get_top_for_display(
            limit=10, since=since, until=until,
        )
        overview_stats = DiscoveredDisplayService.get_overview_stats(since=since, until=until)
        top_queries = DiscoveredDisplayService.get_top_queries(limit=8, since=since, until=until)
        rising_preview = DiscoveredDisplayService.get_rising_preview(limit=5, since=since, until=until)
        timer_label = top_queries[0]['query'] if top_queries else 'Lancer Google Trends'

        discovered_qs = MarketDataWindowService.filter_discovered(since=since, until=until)

        context = {
            'page_mode': mode,
            'data_window': data_window,
            'live_window': data_window if mode == 'live' else MarketDataWindowService.get_live_context(),
            'archive_filters': archive_filters,
            'stats': overview_stats,
            'metric_cards': self._build_metric_cards(
                overview_stats,
                social_stats,
                publications_overview,
                since=since,
                until=until,
                live_days=chart_days,
            ),
            'discovered_by_domain': discovered_by_domain,
            'has_discovered': discovered_qs.exists(),
            'discovered_count': discovered_qs.count(),
            'chart_data': chart_data,
            'top_queries': top_queries,
            'rising_preview': rising_preview,
            'meeting_slots': self._build_meeting_slots(selected_domains, discovered_by_domain, rising_preview),
            'timer_label': timer_label,
            'activity_chart': self._get_social_activity_chart(since=since, until=until, days=chart_days),
            'social_progress': self._build_social_progress(social_stats, publications_overview),
            'schedule_items': self._build_schedule_items(discovered_by_domain),
            'reminders': self._build_reminders(social_stats, selected_domains, publications_overview),
            'table_rows': DiscoveredDisplayService.get_all_for_table(since=since, until=until),
            'selected_domains': selected_domains,
            'has_discovery_config': bool(selected_domains),
            'discovery_timeframe': config.timeframe,
            'discovery_region': config.region,
            'social_stats': social_stats,
            'publications_overview': publications_overview,
            'top_recommendations': top_recommendations,
            'has_top_recommendations': bool(top_recommendations),
            'social_posts': IntelligencePublicationsService.get_posts_for_table(
                category=social_filters['category'],
                keyword_id=social_filters['keyword_id'],
                keyword_other=social_filters['keyword_other'],
                platform=social_filters['platform'] or None,
                sentiment=social_filters['sentiment'] or None,
                since=since,
                until=until,
            ),
            'social_keyword_filters': IntelligencePublicationsService.get_keyword_filters(
                since=since,
                until=until,
            ),
            'social_filters': social_filters,
            'social_sentiment_choices': SocialDisplayService.SENTIMENT_LABELS,
            'data_sources': self._get_data_sources(),
            'api_endpoints': self._get_api_endpoints(),
            'architecture': self._get_architecture_info(),
        }
        if mode == 'test':
            from intelligence.services.jiji_display_service import JijiDisplayService
            from intelligence.services.jumia_display_service import JumiaDisplayService

            context['test_context'] = CollectionTestContextService.build()
            jumia_ctx = JumiaDisplayService.build_context()
            jiji_ctx = JijiDisplayService.build_context()
            context.update(jumia_ctx)
            context.update(jiji_ctx)
        else:
            # Jumia / Jiji aussi en live / archives (lecture tables prod)
            from intelligence.services.jiji_display_service import JijiDisplayService
            from intelligence.services.jumia_display_service import JumiaDisplayService

            jumia_ctx = JumiaDisplayService.build_context(limit_products=24, limit_reviews=30)
            jiji_ctx = JijiDisplayService.build_context(limit_listings=24, limit_sellers=10)
            context.update(jumia_ctx)
            context.update(jiji_ctx)

        # Lecture marché simplifiée (mêmes 4 blocs que le tableau de bord)
        from intelligence.services.dashboard_data_service import DashboardDataService
        from intelligence.services.intelligence_report_service import IntelligenceReportService

        market_report = IntelligenceReportService.build_report(since=since, until=until, limit=10)
        context['market_report'] = market_report

        market_overview = DashboardDataService.pack_market_overview(jumia_ctx, jiji_ctx)
        if mode == 'test':
            market_overview['jumia']['collect_url'] = reverse('intelligence:collecte_test')
            market_overview['jiji']['collect_url'] = reverse('intelligence:collecte_test')
            market_overview['jumia']['detail_url'] = '#jumia-marche'
            market_overview['jiji']['detail_url'] = '#jiji-marche'

        stats = DashboardDataService.get_kpi_stats()
        context['market_overview'] = market_overview
        context['decision_kpis'] = self._build_decision_kpis(
            publications_overview,
            overview_stats,
            market_overview,
        )
        context['social_demand'] = DashboardDataService.get_social_demand_block(
            stats,
            DashboardDataService.get_posts_chart(),
            DashboardDataService.get_overview_bars(limit=3),
            publications_overview=publications_overview,
        )
        context['priority_tasks'] = DashboardDataService.get_priority_tasks(
            market=market_overview,
            limit=5,
        )
        context['reading_summary'] = self._build_reading_summary(
            publications_overview,
            market_overview,
            overview_stats,
        )

        template = 'dashboard/intelligence/test_results.html' if mode == 'test' else 'dashboard/intelligence/index.html'
        return render(self.request, template, context)

    def _build_decision_kpis(self, publications_overview, overview_stats, market):
        """Quatre KPI lisibles — publications, intentions, Jumia, Jiji."""
        from intelligence.services.dashboard_data_service import DashboardDataService

        trends_value = overview_stats[1]['value'] if len(overview_stats) > 1 else 0
        jumia_n = int(market['jumia']['products'])
        jiji_n = int(market['jiji']['listings'])
        purchase = publications_overview['intents']['purchase']
        return [
            {
                'id': 'posts',
                'label': 'Publications suivies',
                'hint': f"{publications_overview['analyzed']} déjà analysées",
                'value': DashboardDataService._format_int(publications_overview['total']),
                'tone': 'orange',
                'trend': {
                    'up': publications_overview['total'] > 0,
                    'label': f"{trends_value} requête(s) Trends" if trends_value else 'Réseaux sociaux',
                },
            },
            {
                'id': 'intents',
                'label': 'Gens qui veulent acheter',
                'hint': 'Commentaires « je veux acheter » détectés',
                'value': DashboardDataService._format_int(purchase),
                'tone': 'jaune',
                'trend': {
                    'up': purchase > 0,
                    'label': 'Commentaires analysés' if purchase else 'En attente NLP',
                },
            },
            {
                'id': 'jumia',
                'label': 'Produits Jumia suivis',
                'hint': 'Catalogue neuf — prix et stock',
                'value': DashboardDataService._format_int(jumia_n),
                'tone': 'bleu',
                'trend': {
                    'up': jumia_n > 0,
                    'label': (
                        f"{market['jumia']['out_of_stock']} rupture(s)"
                        if market['jumia']['out_of_stock']
                        else ('Suivi actif' if jumia_n else 'À collecter')
                    ),
                },
            },
            {
                'id': 'jiji',
                'label': 'Annonces Jiji suivies',
                'hint': 'Marché local — neuf et occasion',
                'value': DashboardDataService._format_int(jiji_n),
                'tone': 'bleu',
                'trend': {
                    'up': jiji_n > 0,
                    'label': (
                        f"{market['jiji']['used']} occasion(s)"
                        if market['jiji']['used']
                        else ('Suivi actif' if jiji_n else 'À collecter')
                    ),
                },
            },
        ]

    @staticmethod
    def _build_reading_summary(publications_overview, market, overview_stats):
        parts = [
            f"{publications_overview['total']} publication(s)",
            f"{publications_overview['intents']['purchase']} intention(s) d’achat",
        ]
        jumia_n = market['jumia']['products']
        jiji_n = market['jiji']['listings']
        if jumia_n:
            parts.append(f"{jumia_n} produit(s) Jumia")
        if jiji_n:
            parts.append(f"{jiji_n} annonce(s) Jiji")
        if not jumia_n and not jiji_n and len(overview_stats) > 1:
            parts.append(f"{overview_stats[1]['value']} requête(s) Trends")
        return ' · '.join(parts)

    def _build_metric_cards(
        self,
        overview_stats,
        social_stats,
        publications_overview,
        *,
        since=None,
        until=None,
        live_days=3,
    ):
        """Cartes métriques — données réseaux sociaux + Google Trends."""
        spark_posts = IntelligencePublicationsService.get_sparkline_values(
            days=live_days, since=since, until=until,
        )
        spark_queries = [
            bar['count']
            for bar in DiscoveredDisplayService.get_activity_chart(
                since=since, until=until, days=live_days,
            )['bars']
        ]

        cards = [
            {
                'label': 'Publications réseaux',
                'value': publications_overview['total'],
                'trend': 'up' if spark_posts and spark_posts[-1] >= (spark_posts[-2] if len(spark_posts) > 1 else 0) else 'mid',
                'spark': spark_posts or [0],
                'spark_points': self._spark_points(spark_posts or [0]),
                'hint': f"{publications_overview['analyzed']} analysées",
            },
            {
                'label': "Intentions d'achat",
                'value': publications_overview['intents']['purchase'],
                'trend': 'up' if publications_overview['intents']['purchase'] else 'mid',
                'spark': [
                    publications_overview['intents']['purchase'],
                    publications_overview['intents']['info'],
                    publications_overview['intents']['off_topic'],
                ] * 3,
                'spark_points': self._spark_points([
                    publications_overview['intents']['purchase'],
                    publications_overview['intents']['info'],
                    max(1, publications_overview['intents']['off_topic'] // 3),
                    publications_overview['intents']['purchase'],
                ]),
                'hint': 'Commentaires NLP',
            },
            {
                'label': 'Requêtes Google Trends',
                'value': overview_stats[1]['value'] if len(overview_stats) > 1 else 0,
                'trend': 'up',
                'spark': spark_queries or [0],
                'spark_points': self._spark_points(spark_queries or [0]),
                'hint': 'Découvertes par domaine',
            },
        ]
        return cards

    @staticmethod
    def _spark_points(values):
        """Convertit une série en points SVG polyline (80x28)."""
        if not values:
            return ''
        max_v = max(values) or 1
        min_v = min(values)
        span = max(max_v - min_v, 1)
        width = 80
        height = 28
        step = width / max(len(values) - 1, 1)
        points = []
        for i, v in enumerate(values):
            x = round(i * step, 1)
            y = round(height - ((v - min_v) / span) * (height - 4) - 2, 1)
            points.append(f'{x},{y}')
        return ' '.join(points)

    @staticmethod
    def _get_social_activity_chart(*, since=None, until=None, days=7):
        """Activité scraping réseaux sur la fenêtre affichée."""
        from datetime import timedelta

        today = timezone.localdate()
        if since is not None:
            start_date = max(timezone.localtime(since).date(), today - timedelta(days=days - 1))
        else:
            start_date = today - timedelta(days=days - 1)
        span = (today - start_date).days + 1
        labels = []
        values = []
        label_names = ['L', 'M', 'M', 'J', 'V', 'S', 'D']

        for offset in range(span - 1, -1, -1):
            day = today - timedelta(days=offset)
            if day < start_date:
                continue
            labels.append(label_names[day.weekday()])
            qs = MarketDataWindowService.filter_posts(since=since, until=until).filter(
                scraped_at__date=day,
            )
            values.append(qs.count())

        max_val = max(values) or 1
        bars = []
        peak = max(values) if values else 0
        for label, value in zip(labels, values):
            bars.append({
                'label': label,
                'height': max(8, round(value / max_val * 100)),
                'active': value == peak and value > 0,
                'value': value,
            })

        week_total = sum(values)
        scoped_total = MarketDataWindowService.filter_posts(since=since, until=until).count()
        pct = min(100, round(week_total / max(scoped_total, 1) * 100))

        return {'bars': bars, 'percent': pct, 'values': values}

    @staticmethod
    def _build_social_progress(social_stats, publications_overview):
        """Pipeline collecte → commentaires → NLP."""
        total = max(publications_overview.get('total', 0), 1)
        with_comments = publications_overview.get('with_comments', 0)
        purchase = publications_overview.get('total_purchase_intents', 0)

        return [
            {
                'label': 'Avec commentaires (10–20)',
                'value': with_comments,
                'percent': max(6, round(with_comments / total * 100)),
                'tone': 'bleu',
            },
            {
                'label': "Signaux d'achat",
                'value': purchase,
                'percent': min(100, max(6, purchase * 5)),
                'tone': 'jaune',
            },
        ]

    @staticmethod
    def _build_meeting_slots(selected_domains, discovered_by_domain, rising_preview):
        """Créneaux style Today's meetings."""
        tones = ['orange', 'bleu', 'jaune', 'noir']
        times = ['09:00', '11:30', '14:00', '16:30']
        slots = []

        if rising_preview:
            for i, item in enumerate(rising_preview[:4]):
                slots.append({
                    'time': item.get('time', times[i % len(times)]),
                    'title': item['query'],
                    'subtitle': item['domain_label'],
                    'tone': item.get('tone', tones[i % len(tones)]),
                })
        elif discovered_by_domain:
            for i, domain in enumerate(discovered_by_domain[:4]):
                slots.append({
                    'time': times[i % len(times)],
                    'title': domain['short_label'],
                    'subtitle': f"{domain['total']} requête(s)",
                    'tone': tones[i % len(tones)],
                })
        elif selected_domains:
            for i, domain in enumerate(selected_domains[:4]):
                slots.append({
                    'time': times[i % len(times)],
                    'title': domain.short_label,
                    'subtitle': 'Domaine configuré',
                    'tone': tones[i % len(tones)],
                })

        return slots

    @staticmethod
    def _build_schedule_items(discovered_by_domain):
        """Timeline verticale des domaines découverts."""
        tones = ['orange', 'bleu', 'jaune', 'gris']
        items = []
        for i, domain in enumerate(discovered_by_domain[:5]):
            items.append({
                'title': domain['short_label'],
                'detail': f"{domain['total']} requête(s) · cat. {domain['cat_id']}",
                'tone': tones[i % len(tones)],
            })
        if not items:
            items = [
                {'title': 'Aucune découverte', 'detail': 'Configurez des domaines', 'tone': 'gris'},
            ]
        return items

    @staticmethod
    def _build_reminders(social_stats, selected_domains, publications_overview=None):
        """Actions prioritaires basées sur l'état réel des données."""
        reminders = []
        overview = publications_overview or {}

        if overview.get('pending', 0) > 0:
            reminders.append({
                'time': 'NLP',
                'text': f"{overview['pending']} publication(s) en attente d'analyse CamemBERT",
                'priority': 'high',
                'priority_label': 'HAUT',
            })

        if overview.get('with_comments', 0) < overview.get('total', 0):
            missing = overview.get('total', 0) - overview.get('with_comments', 0)
            reminders.append({
                'time': 'Scraping',
                'text': f'{missing} publication(s) sans commentaires — lancer enrich_social_comments',
                'priority': 'high',
                'priority_label': 'HAUT',
            })

        if not selected_domains:
            reminders.append({
                'time': 'Config',
                'text': 'Configurer les domaines Google Trends dans Intelligence → Domaines',
                'priority': 'low',
                'priority_label': 'MOYEN',
            })
        elif not reminders:
            reminders.append({
                'time': 'Routine',
                'text': f"Score demande moyen : {overview.get('avg_demand', 0)} — surveiller les catégories forte demande",
                'priority': 'low',
                'priority_label': 'INFO',
            })

        return reminders[:3]

    def _get_data_sources(self):
        return [
            {
                'name': 'Google Trends',
                'tool': 'pytrends',
                'status': 'active',
                'status_label': 'Actif',
                'description': 'Scores de recherche 0-100 pour le Sénégal (SN).',
            },
            {
                'name': 'Découverte par domaine',
                'tool': 'pytrends related_queries',
                'status': 'active',
                'status_label': 'Actif',
                'description': 'Domaines configurés dans Intelligence → Domaines.',
            },
            {
                'name': 'Réseaux sociaux',
                'tool': 'Playwright Stealth',
                'status': 'active',
                'status_label': 'Actif',
                'description': 'Extraction publications réseaux sociaux + API NLP.',
            },
        ]

    def _get_api_endpoints(self):
        return [
            {
                'method': 'GET',
                'path': '/intelligence/api/raw-data/',
                'description': 'Publications sociales en attente d\'analyse NLP.',
            },
            {
                'method': 'POST',
                'path': '/intelligence/api/analyzed-data/',
                'description': 'Réception des analyses NLP depuis le Ryzen 7.',
            },
            {
                'method': 'GET',
                'path': '/intelligence/api/raw-jumia-reviews/',
                'description': 'Avis Jumia bruts pour CamemBERT local (sentiment/aspects).',
            },
            {
                'method': 'POST',
                'path': '/intelligence/api/analyzed-jumia-reviews/',
                'description': 'Résultats NLP Jumia (local → VPS) + refresh Top 10.',
            },
            {
                'method': 'GET',
                'path': '/intelligence/api/social-posts/',
                'description': 'Liste des publications sociales collectées.',
            },
            {
                'method': 'GET',
                'path': '/intelligence/api/keywords/',
                'description': 'Requêtes Google Trends découvertes par domaine.',
            },
        ]

    def _get_architecture_info(self):
        return [
            {
                'role': 'VPS (Logistique)',
                'items': [
                    'Django + PostgreSQL',
                    'Collecte pytrends / Playwright / Jumia',
                    'Tâches Cron ou Celery (sans CamemBERT)',
                ],
            },
            {
                'role': 'Machine locale (Cerveau)',
                'items': [
                    'Modèles NLP CamemBERT (AMD Ryzen 7)',
                    'Avis Jumia : sentiment, aspects, failles',
                    'Communication via API REST',
                ],
            },
        ]
