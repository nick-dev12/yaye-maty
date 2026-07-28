"""
Données agrégées pour le tableau de bord administrateur.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from intelligence.models import MarketSearchKeyword, SocialComment, SocialPost
from intelligence.services.active_keyword_service import ActiveKeywordService
from intelligence.services.social_display_service import SocialDisplayService

CATEGORY_COLORS = ('orange', 'bleu', 'jaune', 'gris', 'orange', 'bleu', 'jaune')


class DashboardDataService:
    """Prépare KPI, graphiques et tableaux depuis la base intelligence."""

    @staticmethod
    def _collection_router():
        from intelligence.services.collection_model_router import CollectionModelRouter

        return CollectionModelRouter()

    @classmethod
    def _posts_qs(cls):
        return cls._collection_router().posts_qs()

    @classmethod
    def _comments_qs(cls):
        return cls._collection_router().comments_qs()

    @classmethod
    def _post_model(cls):
        return cls._collection_router().post_model

    @classmethod
    def _comment_model(cls):
        return cls._collection_router().comment_model

    @classmethod
    def build_context(cls) -> dict:
        """Contexte du home — lecture marché en 4 blocs (KPI, demande, Jumia/Jiji, actions)."""
        from intelligence.services.market_data_window_service import MarketDataWindowService

        stats = cls.get_kpi_stats()
        market = cls.get_market_overview()
        posts_chart = cls.get_posts_chart()
        demand_themes = cls.get_overview_bars(limit=3)
        social_demand = cls.get_social_demand_block(stats, posts_chart, demand_themes)
        data_window = MarketDataWindowService.get_live_context()
        category_breakdown = cls.get_category_breakdown()
        total_categorized = sum(item['count'] for item in category_breakdown) or 0
        posts_chart_widget = cls.get_posts_chart_widget()
        demand_themes_widget = cls.get_demand_themes_widget()
        recent_posts = cls.get_recent_posts(limit=6)
        from intelligence.services.import_master_display_service import ImportMasterDisplayService
        from intelligence.services.intelligence_report_service import IntelligenceReportService

        market_report = IntelligenceReportService.build_report()
        import_master_preview = ImportMasterDisplayService.get_home_preview(limit=3)

        return {
            'market_report': market_report,
            'import_master_preview': import_master_preview,
            'notification_count': stats['pending_analysis'],
            'posts_total': stats['posts_total'],
            'summary_line': cls._build_home_summary(stats, market, data_window),
            'data_window': data_window,
            'decision_kpis': cls.get_decision_kpis(stats, market),
            'social_demand': social_demand,
            'market_overview': market,
            'priority_tasks': cls.get_priority_tasks(market=market, limit=5),
            # Compatibilité / données secondaires
            'stats': stats['cards'],
            'focus_widget': social_demand['focus'],
            'activity_widget': social_demand['activity'],
            'overview_bars': demand_themes,
            'sparkline_kpis': cls.get_decision_kpis(stats, market),
            'category_breakdown': category_breakdown,
            'donut_total': total_categorized,
            'posts_chart': posts_chart_widget['chart'],
            'posts_chart_widget': posts_chart_widget,
            'engagement_bars': demand_themes_widget['bars'],
            'demand_themes_widget': demand_themes_widget,
            'recent_posts': recent_posts,
            'market_signals': social_demand['strong_demand'],
            'timeline': cls.get_timeline(limit=3),
            'reminders': cls.get_reminders(stats),
        }

    @classmethod
    def get_dashboard_layout(cls, stats: dict | None = None) -> dict:
        """Alias conservé — délègue au nouveau layout décisionnel."""
        stats = stats or cls.get_kpi_stats()
        market = cls.get_market_overview()
        posts_chart = cls.get_posts_chart()
        demand_themes = cls.get_overview_bars(limit=3)
        return {
            'decision_kpis': cls.get_decision_kpis(stats, market),
            'social_demand': cls.get_social_demand_block(stats, posts_chart, demand_themes),
            'market_overview': market,
            'priority_tasks': cls.get_priority_tasks(market=market),
            'focus_widget': cls.get_focus_widget(stats),
            'activity_widget': cls.get_activity_widget(posts_chart, stats),
            'overview_bars': demand_themes,
        }

    @classmethod
    def get_market_overview(cls) -> dict:
        """Vue compacte Jumia + Jiji pour le home (pas les tableaux complets Intelligence)."""
        from intelligence.services.jiji_display_service import JijiDisplayService
        from intelligence.services.jumia_display_service import JumiaDisplayService

        return cls.pack_market_overview(
            JumiaDisplayService.build_context(limit_products=6, limit_reviews=0),
            JijiDisplayService.build_context(limit_listings=6, limit_sellers=5),
        )

    @classmethod
    def pack_market_overview(cls, jumia_ctx: dict, jiji_ctx: dict) -> dict:
        """
        Compacte des contextes JumiaDisplay/JijiDisplay déjà chargés.

        Utilisé par le home et la page Intelligence pour éviter un double scrape
        de contexte affichage.
        """
        jumia_stats = jumia_ctx.get('jumia_stats') or {}
        jiji_stats = jiji_ctx.get('jiji_stats') or {}
        opportunities = (jumia_ctx.get('jumia_opportunities') or [])[:3]
        arbitrage = (jiji_ctx.get('jiji_arbitrage') or [])[:3]
        heatmap = (jiji_ctx.get('jiji_heatmap') or [])[:3]
        keyword_demand = (jiji_ctx.get('jiji_keyword_demand') or [])[:3]

        avg_price = jiji_stats.get('avg_price')
        return {
            'has_jumia': bool(jumia_ctx.get('has_jumia')),
            'has_jiji': bool(jiji_ctx.get('has_jiji')),
            'jumia': {
                'products': int(jumia_stats.get('products_total') or 0),
                'avg_rating': jumia_stats.get('avg_rating'),
                'out_of_stock': int(jumia_stats.get('out_of_stock') or 0),
                'low_stock': int(jumia_stats.get('low_stock') or 0),
                'discounts': int(jumia_stats.get('with_discount') or 0),
                'opportunities': opportunities,
                'products_preview': jumia_ctx.get('jumia_products') or [],
                'collect_url': reverse('intelligence:collecte'),
                'detail_url': f"{reverse('intelligence:index')}#jumia-marche",
            },
            'jiji': {
                'listings': int(jiji_stats.get('listings_total') or 0),
                'total_views': int(jiji_stats.get('total_views') or 0),
                'avg_price': round(float(avg_price), 0) if avg_price is not None else None,
                'used': int(jiji_stats.get('used') or 0),
                'new': int(jiji_stats.get('new') or 0),
                'negotiable': int(jiji_stats.get('negotiable') or 0),
                'heatmap': heatmap,
                'keyword_demand': keyword_demand,
                'listings_preview': jiji_ctx.get('jiji_listings') or [],
                'collect_url': reverse('intelligence:collecte'),
                'detail_url': f"{reverse('intelligence:index')}#jiji-marche",
            },
            'arbitrage': arbitrage,
            'arbitrage_title': 'Neuf Jiji moins cher que Jumia',
            'arbitrage_subtitle': 'Comparaison neuf ↔ neuf (même produit catalogue)',
            'arbitrage_empty': 'Pas encore d’écart prix neuf significatif Jumia ↔ Jiji.',
        }

    @classmethod
    def _build_home_summary(cls, stats: dict, market: dict, data_window: dict) -> str:
        """Phrase d’accroche lisible pour le hero du tableau de bord."""
        parts = [data_window.get('label', 'Flux actuel')]
        if stats.get('posts_total'):
            parts.append(f"{cls._format_int(stats['posts_total'])} publications réseaux")
        jumia_n = int(market['jumia']['products'])
        jiji_n = int(market['jiji']['listings'])
        if jumia_n or jiji_n:
            parts.append(f"{jumia_n} produit(s) Jumia · {jiji_n} annonce(s) Jiji")
        elif stats.get('pending_analysis'):
            parts.append(f"{stats['pending_analysis']} analyse(s) en attente")
        else:
            parts.append('Lancez une collecte pour alimenter la veille')
        return ' · '.join(parts)

    @classmethod
    def get_decision_kpis(cls, stats: dict, market: dict | None = None) -> list[dict]:
        """Quatre KPI décisionnels — sans sparklines techniques."""
        market = market or cls.get_market_overview()
        week_ago = timezone.now() - timedelta(days=7)
        posts_week = SocialPost.objects.filter(scraped_at__gte=week_ago).count()
        posts_prev = SocialPost.objects.filter(
            scraped_at__gte=week_ago - timedelta(days=7),
            scraped_at__lt=week_ago,
        ).count()
        purchase_intents = SocialComment.objects.filter(
            intent=SocialComment.Intent.PURCHASE,
        ).count()
        intents_week = SocialComment.objects.filter(
            created_at__gte=week_ago,
            intent=SocialComment.Intent.PURCHASE,
        ).count()
        intents_prev = SocialComment.objects.filter(
            created_at__gte=week_ago - timedelta(days=7),
            created_at__lt=week_ago,
            intent=SocialComment.Intent.PURCHASE,
        ).count()

        jumia_n = int(market['jumia']['products'])
        jiji_n = int(market['jiji']['listings'])

        return [
            {
                'id': 'posts',
                'label': 'Publications (7 j)',
                'hint': 'Réseaux sociaux collectés cette semaine',
                'value': cls._format_int(posts_week),
                'tone': 'orange',
                'trend': cls._format_trend(posts_week, posts_prev),
            },
            {
                'id': 'intents',
                'label': 'Intentions d’achat',
                'hint': 'Signaux NLP « je veux acheter »',
                'value': cls._format_int(purchase_intents),
                'tone': 'jaune',
                'trend': cls._format_trend(intents_week, intents_prev),
            },
            {
                'id': 'jumia',
                'label': 'Produits Jumia',
                'hint': 'Catalogue neuf suivi (prix & stock)',
                'value': cls._format_int(jumia_n),
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
                'label': 'Annonces Jiji',
                'hint': 'Occasions & neuf sur le marché local',
                'value': cls._format_int(jiji_n),
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

    @classmethod
    def get_social_demand_block(
        cls,
        stats: dict,
        posts_chart: dict,
        demand_themes: dict,
        *,
        publications_overview: dict | None = None,
    ) -> dict:
        """Bloc « Demande sur les réseaux » — veille par mots-clés Paramètres."""
        focus = cls.get_focus_widget(stats)
        activity = cls.get_activity_widget(posts_chart, stats)
        keyword_panel = cls.build_keyword_veille_panel()
        nlp = cls._build_social_nlp_summary(stats, publications_overview)

        return {
            'title': 'Demande sur les réseaux sociaux',
            'subtitle': (
                f'{keyword_panel["social_active"]} mot-clé{"s" if keyword_panel["social_active"] != 1 else ""} '
                f'actif{"s" if keyword_panel["social_active"] != 1 else ""} · '
                f'TikTok {keyword_panel["tiktok"]} · Facebook {keyword_panel["facebook"]}'
            ),
            'intro': (
                'Toutes les publications proviennent de recherches lancées avec vos mots-clés '
                'dans Paramètres → Recherche. Chaque ligne ci-dessous montre ce qu’un mot-clé '
                'a réellement collecté.'
            ),
            'focus': focus,
            'keywords': keyword_panel,
            'nlp': nlp,
            'stats_row': cls._build_social_stats_row(stats, focus, nlp, activity),
            'themes': {
                **demand_themes,
                'title': 'Thématiques détectées (NLP)',
                'subtitle': 'Catégories agricoles les plus discutées dans les contenus analysés',
            },
            'activity': activity,
            'strong_demand': cls.get_market_signals(limit=4),
            'strong_demand_title': 'Publications à fort potentiel',
            'strong_demand_hint': (
                'Contenus liés à vos mots-clé avec le meilleur score de demande '
                '(engagement + intentions d’achat dans les commentaires)'
            ),
            'detail_url': f"{reverse('intelligence:index')}#publications",
            'settings_url': f"{reverse('settings')}?section=recherche",
            'collect_url': reverse('intelligence:collecte'),
        }

    @classmethod
    def build_keyword_veille_panel(cls, *, limit: int = 10) -> dict:
        """Tableau de bord des mots-clés réseaux — source unique de collecte."""
        from intelligence.models import MarketSearchKeyword

        posts_qs = cls._posts_qs()
        week_ago = timezone.now() - timedelta(days=7)

        url_counts: dict[str, int] = {}
        week_counts: dict[str, int] = {}
        for row in posts_qs.values('source_url').annotate(total=Count('id')):
            url = row.get('source_url') or ''
            if url:
                url_counts[url] = row['total']
        for row in posts_qs.filter(scraped_at__gte=week_ago).values('source_url').annotate(
            total=Count('id'),
        ):
            url = row.get('source_url') or ''
            if url:
                week_counts[url] = row['total']

        social_keywords = ActiveKeywordService.list_for_social()
        tiktok_n = sum(1 for kw in social_keywords if kw.platform == MarketSearchKeyword.Platform.TIKTOK)
        facebook_n = sum(1 for kw in social_keywords if kw.platform == MarketSearchKeyword.Platform.FACEBOOK)
        marketplace_n = ActiveKeywordService.count_marketplace()

        rows = []
        for kw in social_keywords:
            url = kw.build_search_url()
            total = url_counts.get(url, 0)
            week = week_counts.get(url, 0)
            rows.append({
                'id': kw.pk,
                'keyword': kw.keyword,
                'label': kw.display_label,
                'platform': kw.platform,
                'platform_label': kw.get_platform_display(),
                'platform_icon': 'tiktok' if kw.platform == MarketSearchKeyword.Platform.TIKTOK else 'facebook',
                'posts_total': total,
                'posts_week': week,
                'last_scraped_label': cls._relative_time(kw.last_scraped_at),
                'max_videos': kw.max_videos,
                'max_comments': kw.max_comments,
                'has_data': total > 0,
                'filter_url': f"{reverse('intelligence:index')}?section=social&social_keyword={kw.pk}#publications",
            })
        rows.sort(key=lambda item: (-item['posts_week'], -item['posts_total'], item['keyword']))

        return {
            'social_active': len(social_keywords),
            'tiktok': tiktok_n,
            'facebook': facebook_n,
            'marketplace_total': marketplace_n,
            'rows': rows[:limit],
            'has_keywords': bool(social_keywords),
            'empty_message': (
                'Aucun mot-clé TikTok ou Facebook actif. '
                'Ajoutez-en dans Paramètres pour lancer la collecte.'
            ),
        }

    @classmethod
    def _build_social_nlp_summary(
        cls,
        stats: dict,
        publications_overview: dict | None,
    ) -> dict:
        """Synthèse NLP pour le panneau réseaux."""
        pub = publications_overview or {}
        total = int(pub.get('total') or stats.get('posts_total') or 0)
        analyzed = int(pub.get('analyzed') or 0)
        pending = int(pub.get('pending') or stats.get('pending_analysis') or 0)
        purchase = int((pub.get('intents') or {}).get('purchase') or 0)
        comments = int(pub.get('comment_total') or 0)
        percent = round(analyzed / total * 100) if total else 0

        return {
            'analyzed': analyzed,
            'pending': pending,
            'purchase_intents': purchase,
            'comments_total': comments,
            'percent': percent,
            'percent_label': f'{percent} % des publications analysées',
            'status': 'done' if percent >= 80 else ('progress' if percent >= 30 else 'idle'),
        }

    @classmethod
    def _build_social_stats_row(
        cls,
        stats: dict,
        focus: dict,
        nlp: dict,
        activity: dict,
    ) -> list[dict]:
        """Quatre indicateurs lisibles pour le panneau réseaux."""
        return [
            {
                'label': 'Publications (7 j)',
                'value': focus['today_value'],
                'hint': 'Contenus collectés via mots-clés Paramètres',
                'tone': 'orange',
                'icon': 'collect',
            },
            {
                'label': 'Total en base',
                'value': focus['limit_value'],
                'hint': 'Toutes publications réseaux enregistrées',
                'tone': 'bleu',
                'icon': 'database',
            },
            {
                'label': 'Intentions d’achat',
                'value': cls._format_int(nlp['purchase_intents']),
                'hint': 'Commentaires « je veux acheter » détectés par NLP',
                'tone': 'jaune',
                'icon': 'intent',
            },
            {
                'label': 'Analyse IA',
                'value': f"{nlp['percent']} %",
                'hint': f'{cls._format_int(nlp["pending"])} publication(s) en attente',
                'tone': 'gris' if nlp['percent'] < 50 else 'bleu',
                'icon': 'nlp',
            },
        ]

    @staticmethod
    def _relative_time(dt) -> str:
        if not dt:
            return 'Jamais collecté'
        delta = timezone.now() - dt
        if delta.days >= 1:
            return f'il y a {delta.days} jour{"s" if delta.days > 1 else ""}'
        hours = delta.seconds // 3600
        if hours >= 1:
            return f'il y a {hours} h'
        minutes = max(1, delta.seconds // 60)
        return f'il y a {minutes} min'

    @classmethod
    def get_focus_widget(cls, stats: dict) -> dict:
        week_ago = timezone.now() - timedelta(days=7)
        posts_this_week = cls._posts_qs().filter(scraped_at__gte=week_ago).count()
        social_count = ActiveKeywordService.count_social()

        return {
            'title': 'Veille par mots-clés',
            'subtitle': (
                f'{social_count} mot-clé{"s" if social_count != 1 else ""} réseau '
                f'actif{"s" if social_count != 1 else ""} dans Paramètres'
            ),
            'today_label': 'Nouvelles publications (7 j)',
            'today_value': cls._format_int(posts_this_week),
            'limit_label': 'Total publications',
            'limit_value': cls._format_int(stats.get('posts_total', 0)),
            'status': 'active' if posts_this_week > 0 else 'idle',
            'status_label': (
                'Collecte active cette semaine'
                if posts_this_week > 0
                else 'En attente — lancez une collecte'
            ),
            'help': (
                'TikTok : recherche Top-Down par mot-clé. Facebook : page recherche '
                'construite automatiquement depuis le même mot-clé Paramètres.'
            ),
        }

    @classmethod
    def get_priority_tasks(
        cls,
        *,
        limit: int = 5,
        market: dict | None = None,
    ) -> list[dict]:
        """Actions prioritaires — NLP pending + alertes Jumia/Jiji."""
        tasks: list[dict] = []
        market = market or {}

        jumia = market.get('jumia') or {}
        out_stock = int(jumia.get('out_of_stock') or 0)
        if out_stock:
            tasks.append({
                'title': f'{out_stock} rupture(s) de stock Jumia',
                'meta': 'Prix & stock Jumia · opportunité de proposer une alternative',
                'tone': 'orange',
                'icon': 'pending',
                'url': jumia.get('detail_url') or reverse('intelligence:index'),
            })

        for opp in (jumia.get('opportunities') or [])[:1]:
            label = (opp.get('product_label') or opp.get('product_slug') or 'Produit')[:42]
            tasks.append({
                'title': f'Alerte stock : {label}',
                'meta': opp.get('evidence_text') or 'Signal marché Jumia',
                'tone': opp.get('tone') or 'jaune',
                'icon': 'star',
                'url': jumia.get('detail_url') or reverse('intelligence:index'),
            })

        for arb in (market.get('arbitrage') or [])[:1]:
            gap = arb.get('gap_percent')
            title = arb.get('product_label') or arb.get('product_slug') or 'Produit'
            tasks.append({
                'title': f'Moins cher en local : {str(title)[:40]}',
                'meta': (
                    f'Écart {gap}% vs neuf Jumia'
                    if gap is not None
                    else (arb.get('evidence_text') or 'Arbitrage Jiji ↔ Jumia')
                ),
                'tone': 'jaune',
                'icon': 'star',
                'url': (market.get('jiji') or {}).get('detail_url') or reverse('intelligence:index'),
            })

        remaining = max(1, limit - len(tasks))
        Post = cls._post_model()
        pending = (
            cls._posts_qs()
            .filter(analysis_status=Post.AnalysisStatus.PENDING)
            .order_by('-scraped_at')[:remaining]
        )
        for post in pending:
            tasks.append({
                'title': post.content[:48] + ('…' if len(post.content) > 48 else ''),
                'meta': f'{post.get_platform_display()} · en attente d\'analyse IA',
                'tone': 'orange',
                'icon': 'pending',
                'url': f"{reverse('intelligence:index')}#publications",
            })

        if len(tasks) < limit:
            high_demand = (
                cls._posts_qs()
                .filter(analysis_status=Post.AnalysisStatus.DONE, demand_score__gte=3)
                .order_by('-demand_score', '-scraped_at')[: limit - len(tasks)]
            )
            for post in high_demand:
                tasks.append({
                    'title': post.content[:48] + ('…' if len(post.content) > 48 else ''),
                    'meta': (
                        f'Demande {cls._demand_label(post.demand_score).lower()} · '
                        f'{post.get_platform_display()}'
                    ),
                    'tone': 'bleu',
                    'icon': 'star',
                    'url': f"{reverse('intelligence:index')}#publications",
                })

        if not tasks:
            tasks.append({
                'title': 'Aucune action urgente',
                'meta': 'Lancez une collecte Jumia, Jiji ou réseaux sociaux',
                'tone': 'gris',
                'icon': 'idle',
                'url': reverse('intelligence:collecte'),
            })

        return tasks[:limit]

    @classmethod
    def get_market_signals(cls, *, limit: int = 3) -> list[dict]:
        """Signaux forts — publications à fort potentiel commercial."""
        posts = (
            cls._posts_qs()
            .filter(demand_score__gte=3)
            .order_by('-demand_score', '-scraped_at')[:limit]
        )
        tones = ('orange', 'bleu', 'purple')
        signals = []

        for index, post in enumerate(posts):
            local = timezone.localtime(post.scraped_at or post.published_at or timezone.now())
            keyword_meta = SocialDisplayService.resolve_keyword_for_source(post.source_url)
            keyword_hint = keyword_meta.get('keyword') or 'veille générale'
            category = SocialDisplayService.CATEGORY_LABELS.get(post.category, 'Non classé')
            signals.append({
                'time': local.strftime('%d/%m'),
                'title': post.content[:48] + ('…' if len(post.content) > 48 else ''),
                'subtitle': (
                    f'Mot-clé « {keyword_hint} » · {category} · '
                    f'{cls._demand_label(post.demand_score).lower()}'
                ),
                'tone': tones[index % len(tones)],
            })

        if not signals:
            signals.append({
                'time': '—',
                'title': 'Aucune publication à forte demande pour l’instant',
                'subtitle': 'Lancez une collecte réseaux puis analysez les commentaires (NLP)',
                'tone': 'gris',
            })

        return signals

    @classmethod
    def get_activity_widget(cls, posts_chart: dict, stats: dict) -> dict:
        """Graphique barres — activité de collecte sur 7 jours."""
        values = posts_chart['values']
        labels = posts_chart['labels']
        max_val = max(values) or 1
        total_week = sum(values)

        week_ago = timezone.now() - timedelta(days=7)
        prev_start = week_ago - timedelta(days=7)
        current = cls._posts_qs().filter(scraped_at__gte=week_ago).count()
        previous = cls._posts_qs().filter(
            scraped_at__gte=prev_start, scraped_at__lt=week_ago,
        ).count()
        trend = cls._format_trend(current, previous)

        posts_total = stats['posts_total'] or 1
        pending = stats['pending_analysis']
        analyzed_pct = round((posts_total - pending) / posts_total * 100)

        bars = []
        for label, value in zip(labels, values):
            bars.append({
                'label': label,
                'value': value,
                'percent': max(8, round(value / max_val * 100)),
                'active': value == max(values) and value > 0,
            })

        return {
            'title': 'Activité collecte (7 jours)',
            'subtitle': 'Publications enregistrées par jour — toutes sources mots-clés Paramètres',
            'percent': analyzed_pct,
            'percent_label': 'publications analysées par NLP',
            'trend': trend['label'],
            'trend_up': trend['up'],
            'bars': bars,
            'footer': f'{cls._format_int(total_week)} collectée{"s" if total_week != 1 else ""} cette semaine',
        }

    @classmethod
    def get_sparkline_kpis(cls, posts_chart: dict, stats: dict) -> list[dict]:
        """Trois KPI compacts avec mini sparkline (style TaskHive)."""
        post_values = posts_chart['values']
        today = timezone.localdate()

        comment_values = []
        intent_values = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            comment_values.append(SocialComment.objects.filter(created_at__date=day).count())
            intent_values.append(
                SocialComment.objects.filter(
                    created_at__date=day,
                    intent=SocialComment.Intent.PURCHASE,
                ).count()
            )

        posts_total = stats['posts_total']
        comments_total = SocialComment.objects.count()
        purchase_intents = SocialComment.objects.filter(
            intent=SocialComment.Intent.PURCHASE,
        ).count()

        week_ago = timezone.now() - timedelta(days=7)
        posts_week = SocialPost.objects.filter(scraped_at__gte=week_ago).count()
        posts_prev = SocialPost.objects.filter(
            scraped_at__gte=week_ago - timedelta(days=7),
            scraped_at__lt=week_ago,
        ).count()
        comments_week = SocialComment.objects.filter(created_at__gte=week_ago).count()
        comments_prev = SocialComment.objects.filter(
            created_at__gte=week_ago - timedelta(days=7),
            created_at__lt=week_ago,
        ).count()
        intents_week = SocialComment.objects.filter(
            created_at__gte=week_ago,
            intent=SocialComment.Intent.PURCHASE,
        ).count()
        intents_prev = SocialComment.objects.filter(
            created_at__gte=week_ago - timedelta(days=7),
            created_at__lt=week_ago,
            intent=SocialComment.Intent.PURCHASE,
        ).count()

        return [
            {
                'label': 'Publications réseaux',
                'sublabel': 'Toutes plateformes',
                'value': cls._format_int(posts_total),
                'trend': cls._format_trend(posts_week, posts_prev),
                'sparkline': cls._build_sparkline(post_values, color='green'),
            },
            {
                'label': 'Commentaires collectés',
                'sublabel': 'Textes analysés localement',
                'value': cls._format_int(comments_total),
                'trend': cls._format_trend(comments_week, comments_prev),
                'sparkline': cls._build_sparkline(comment_values, color='bleu'),
            },
            {
                'label': 'Intentions d\'achat',
                'sublabel': 'Signaux commerciaux NLP',
                'value': cls._format_int(purchase_intents),
                'trend': cls._format_trend(intents_week, intents_prev),
                'sparkline': cls._build_sparkline(intent_values, color='orange'),
            },
        ]

    @classmethod
    def get_overview_bars(cls, *, limit: int = 5) -> dict:
        """Barres horizontales — score demande par thématique (style Invoice Overview)."""
        bars = cls._build_demand_theme_bars(limit=limit)
        bar_colors = ('purple', 'rose', 'bleu', 'green', 'jaune')

        items = []
        for index, bar in enumerate(bars):
            items.append({
                'label': bar['name'],
                'value': f"{bar['score']} / 5",
                'hint': bar['demand_label'],
                'percent': bar['percent'],
                'color': bar_colors[index % len(bar_colors)],
                'detail': bar['publications_label'],
            })

        return {
            'title': 'Thématiques les plus demandées',
            'subtitle': 'Score moyen sur les publications analysées (0 à 5)',
            'items': items,
        }

    @classmethod
    def get_timeline(cls, *, limit: int = 4) -> dict:
        """Chronologie — dernières publications collectées."""
        posts = SocialPost.objects.all().order_by('-scraped_at')[:limit]
        tones = ('lime', 'yellow', 'lavender', 'bleu')
        events = []

        for index, post in enumerate(posts):
            local = timezone.localtime(post.scraped_at or timezone.now())
            months = ('jan', 'fév', 'mar', 'avr', 'mai', 'jun', 'jul', 'aoû', 'sep', 'oct', 'nov', 'déc')
            events.append({
                'time': f'{local.day} {months[local.month - 1]} · {local.strftime("%H:%M")}',
                'title': post.content[:40] + ('…' if len(post.content) > 40 else ''),
                'category': SocialDisplayService.CATEGORY_LABELS.get(
                    post.category, post.get_platform_display(),
                ),
                'tone': tones[index % len(tones)],
            })

        if not events:
            events.append({
                'time': '—',
                'title': 'Aucune publication récente',
                'category': 'Lancez une collecte',
                'tone': 'gris',
            })

        return {
            'title': 'Dernières collectes',
            'subtitle': 'Publications enregistrées récemment',
            'events': events,
        }

    @classmethod
    def get_reminders(cls, stats: dict) -> dict:
        """Rappels — actions à ne pas oublier."""
        pending = stats['pending_analysis']
        purchase = SocialComment.objects.filter(
            intent=SocialComment.Intent.PURCHASE,
        ).count()
        failed = SocialPost.objects.filter(
            analysis_status=SocialPost.AnalysisStatus.FAILED,
        ).count()

        items = []
        if pending:
            items.append({
                'time': 'Priorité',
                'title': f'{cls._format_int(pending)} publication{"s" if pending != 1 else ""} à analyser',
                'priority': 'high',
                'priority_label': 'Urgent',
            })
        if purchase:
            items.append({
                'time': 'NLP',
                'title': f'{cls._format_int(purchase)} intention{"s" if purchase != 1 else ""} d\'achat détectée{"s" if purchase != 1 else ""}',
                'priority': 'high',
                'priority_label': 'Urgent',
            })
        if failed:
            items.append({
                'time': 'Erreur',
                'title': f'{failed} analyse{"s" if failed != 1 else ""} en échec',
                'priority': 'low',
                'priority_label': 'À revoir',
            })
        items.append({
            'time': 'Veille',
            'title': 'Consulter le Top 10 achats recommandés',
            'priority': 'low',
            'priority_label': 'Info',
        })

        return {
            'title': 'Rappels',
            'items': items[:4],
        }

    @staticmethod
    def _build_sparkline(values: list[int], *, width: int = 88, height: int = 36, color: str = 'green') -> dict:
        """Points SVG pour mini courbe tendance."""
        if not values:
            values = [0] * 7
        max_v = max(values) or 1
        step = width / max(len(values) - 1, 1)
        coords = []
        for index, value in enumerate(values):
            x = round(index * step, 1)
            y = round(height - 4 - (value / max_v) * (height - 8), 1)
            coords.append(f'{x},{y}')
        return {
            'points': ' '.join(coords),
            'color': color,
            'width': width,
            'height': height,
        }

    @classmethod
    def get_kpi_stats(cls) -> dict:
        Post = cls._post_model()
        Comment = cls._comment_model()
        posts_qs = cls._posts_qs()
        posts_total = posts_qs.count()
        analyzed = posts_qs.filter(analysis_status=Post.AnalysisStatus.DONE).count()
        pending = posts_qs.filter(analysis_status=Post.AnalysisStatus.PENDING).count()
        with_comments = posts_qs.exclude(Q(comments=[]) | Q(comments__isnull=True)).count()

        comments_total = cls._comments_qs().count()
        purchase_intents = cls._comments_qs().filter(
            intent=Comment.Intent.PURCHASE,
        ).count()
        info_requests = cls._comments_qs().filter(
            intent=Comment.Intent.INFO,
        ).count()

        avg_demand = posts_qs.aggregate(avg=Avg('demand_score'))['avg'] or 0
        total_views = posts_qs.aggregate(total=Sum('view_count'))['total'] or 0
        total_saves = posts_qs.aggregate(total=Sum('save_count'))['total'] or 0

        keywords_active = ActiveKeywordService.count_active()
        social_keywords_active = ActiveKeywordService.count_social()

        week_ago = timezone.now() - timedelta(days=7)
        posts_this_week = posts_qs.filter(scraped_at__gte=week_ago).count()
        posts_prev_week = posts_qs.filter(
            scraped_at__gte=week_ago - timedelta(days=7),
            scraped_at__lt=week_ago,
        ).count()

        comments_week = cls._comments_qs().filter(created_at__gte=week_ago).count()
        comments_prev = cls._comments_qs().filter(
            created_at__gte=week_ago - timedelta(days=7),
            created_at__lt=week_ago,
        ).count()

        cards = [
            {
                'icon': 'posts',
                'tone': 'orange',
                'title': 'Publications réseaux sociaux',
                'subtitle': 'TikTok · Facebook · veille marché agricole',
                'badge_label': cls._weekly_badge(posts_this_week, posts_prev_week, 'nouvelle'),
                'badge_tone': 'up' if posts_this_week >= posts_prev_week else 'neutral',
                'highlight_value': cls._format_int(posts_total),
                'highlight_label': f'publication{"s" if posts_total != 1 else ""} collectée{"s" if posts_total != 1 else ""}',
                'highlight_help': (
                    'Contenus repérés sur les réseaux sociaux liés à l\'équipement agricole au Sénégal.'
                ),
                'metrics': [
                    {
                        'label': 'Analysées par l\'IA',
                        'value': cls._format_int(analyzed),
                        'help': 'Publications déjà classées (catégorie, sentiment, score de demande).',
                        'tone': 'bleu',
                    },
                    {
                        'label': 'Avec commentaires',
                        'value': cls._format_int(with_comments),
                        'help': 'Publications pour lesquelles des commentaires ont été récupérés.',
                        'tone': 'jaune',
                    },
                ],
                'footer': [
                    {'label': 'Cette semaine', 'value': f'{cls._format_int(posts_this_week)} nouvelle(s)'},
                    {'label': 'En attente d\'analyse', 'value': cls._format_int(pending)},
                ],
            },
            {
                'icon': 'comments',
                'tone': 'bleu',
                'title': 'Commentaires collectés',
                'subtitle': 'Textes des internautes · analyse locale',
                'badge_label': cls._weekly_badge(comments_week, comments_prev, 'nouveau'),
                'badge_tone': 'up' if comments_week >= comments_prev else 'neutral',
                'highlight_value': cls._format_int(comments_total),
                'highlight_label': f'commentaire{"s" if comments_total != 1 else ""} enregistré{"s" if comments_total != 1 else ""}',
                'highlight_help': (
                    'Réactions et questions laissées sous les publications — matière pour détecter la demande.'
                ),
                'metrics': [
                    {
                        'label': 'Intentions d\'achat',
                        'value': cls._format_int(purchase_intents),
                        'help': 'Commentaires où quelqu\'un manifeste vouloir acheter ou se renseigner pour acheter.',
                        'tone': 'orange',
                    },
                    {
                        'label': 'Demandes d\'information',
                        'value': cls._format_int(info_requests),
                        'help': 'Questions sur le prix, la disponibilité ou le fonctionnement d\'un produit.',
                        'tone': 'jaune',
                    },
                ],
                'footer': [
                    {'label': 'Cette semaine', 'value': f'{cls._format_int(comments_week)} nouveau(x)'},
                    {'label': 'Total analysé', 'value': cls._format_int(comments_total)},
                ],
            },
            {
                'icon': 'engagement',
                'tone': 'jaune',
                'title': 'Visibilité & engagement',
                'subtitle': 'Vues · favoris · score de demande',
                'badge_label': cls._demand_label(int(round(avg_demand))),
                'badge_tone': cls._demand_tone(int(round(avg_demand))),
                'highlight_value': cls._format_int(total_views),
                'highlight_label': 'vues cumulées sur les publications',
                'highlight_help': (
                    'Nombre total de consultations — indicateur de portée des contenus suivis.'
                ),
                'metrics': [
                    {
                        'label': 'Favoris enregistrés',
                        'value': cls._format_int(total_saves),
                        'help': 'Sauvegardes des publications — signe d\'intérêt durable des utilisateurs.',
                        'tone': 'bleu',
                    },
                    {
                        'label': 'Score demande moyen',
                        'value': f'{avg_demand:.1f} / 5',
                        'help': (
                            'Estimation de l\'intérêt commercial (0 = faible, 5 = forte demande). '
                            'Calculé par l\'IA locale.'
                        ),
                        'tone': 'orange',
                    },
                ],
                'footer': [
                    {'label': 'Niveau global', 'value': cls._demand_label(int(round(avg_demand)))},
                    {'label': 'Publications analysées', 'value': cls._format_int(analyzed)},
                ],
            },
            {
                'icon': 'collect',
                'tone': 'orange',
                'title': 'Sources de collecte',
                'subtitle': 'Mots-clés Paramètres · réseaux · Jumia · Jiji',
                'badge_label': f'{cls._format_int(keywords_active)} actif(s)',
                'badge_tone': 'up',
                'highlight_value': cls._format_int(keywords_active),
                'highlight_label': 'mot(s)-clé(s) de veille configuré(s)',
                'highlight_help': (
                    'Seuls les mots-clés actifs dans Paramètres alimentent les collectes automatiques.'
                ),
                'metrics': [
                    {
                        'label': 'Réseaux (TikTok / Facebook)',
                        'value': cls._format_int(social_keywords_active),
                        'help': 'Recherches TikTok Top-Down et Facebook par mot-clé Paramètres.',
                        'tone': 'jaune',
                    },
                    {
                        'label': 'Marché (Jumia & Jiji)',
                        'value': cls._format_int(keywords_active),
                        'help': 'Mêmes mots-clés actifs pour prix, avis et annonces locales.',
                        'tone': 'bleu',
                    },
                ],
                'footer': [
                    {'label': 'Publications cette semaine', 'value': cls._format_int(posts_this_week)},
                    {'label': 'Semaine précédente', 'value': cls._format_int(posts_prev_week)},
                ],
            },
        ]

        return {
            'cards': cards,
            'posts_total': posts_total,
            'pending_analysis': pending,
            'summary_line': cls._build_summary_line(
                posts_total=posts_total,
                comments_total=comments_total,
                purchase_intents=purchase_intents,
            ),
        }

    @classmethod
    def _build_summary_line(
        cls,
        *,
        posts_total: int,
        comments_total: int,
        purchase_intents: int,
    ) -> str:
        """Sous-titre d'accueil — mentionne Jumia/Jiji si des données existent."""
        from intelligence.services.collection_model_router import CollectionModelRouter

        router = CollectionModelRouter()
        jumia_n = router.jumia_product_model.objects.count()
        jiji_n = router.jiji_listing_model.objects.count()
        parts = [
            f'{cls._format_int(posts_total)} publication{"s" if posts_total != 1 else ""}',
            f'{cls._format_int(purchase_intents)} intention{"s" if purchase_intents != 1 else ""} d’achat',
        ]
        if jumia_n:
            parts.append(f'{cls._format_int(jumia_n)} produit{"s" if jumia_n != 1 else ""} Jumia')
        if jiji_n:
            parts.append(f'{cls._format_int(jiji_n)} annonce{"s" if jiji_n != 1 else ""} Jiji')
        if not jumia_n and not jiji_n:
            parts.append(f'{cls._format_int(comments_total)} commentaire{"s" if comments_total != 1 else ""}')
        return ' · '.join(parts)

    @classmethod
    def get_category_breakdown(cls, *, limit: int = 6) -> list[dict]:
        rows = (
            SocialPost.objects
            .filter(analysis_status=SocialPost.AnalysisStatus.DONE)
            .exclude(category='')
            .values('category')
            .annotate(count=Count('id'))
            .order_by('-count')[:limit]
        )

        items = []
        for index, row in enumerate(rows):
            slug = row['category']
            items.append({
                'name': SocialDisplayService.CATEGORY_LABELS.get(slug, slug.replace('_', ' ').title()),
                'count': row['count'],
                'color': CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
            })

        if not items:
            items.append({
                'name': 'En attente de données',
                'count': 1,
                'color': 'gris',
            })

        total = sum(item['count'] for item in items) or 1
        for item in items:
            share = round(item['count'] / total * 100, 1)
            item['share'] = f'{share:g}'
            item['percent'] = share

        return items

    @classmethod
    def get_posts_chart(cls) -> dict:
        """Publications collectées sur les 7 derniers jours."""
        today = timezone.localdate()
        labels = []
        values = []

        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            labels.append(cls._weekday_label(day))
            values.append(
                cls._posts_qs().filter(scraped_at__date=day).count()
            )

        return cls._build_line_chart(labels, values)

    @classmethod
    def get_posts_chart_widget(cls) -> dict:
        """Widget courbe — collecte quotidienne avec libellés compréhensibles."""
        chart = cls.get_posts_chart()
        values = chart['values']
        labels = chart['labels']
        total_week = sum(values)
        peak_value = max(values) if values else 0
        peak_idx = values.index(peak_value) if values and peak_value else 0
        peak_label = labels[peak_idx] if labels else '—'
        avg_day = round(total_week / len(values), 1) if values else 0

        return {
            'title': 'Collecte des publications (7 jours)',
            'subtitle': 'Réseaux sociaux · TikTok & Facebook · veille automatique',
            'help': (
                'Chaque point indique combien de nouvelles publications ont été enregistrées '
                'ce jour-là par le système (hashtags, groupes, mots-clés).'
            ),
            'badge_label': f'{cls._format_int(total_week)} cette semaine',
            'badge_tone': 'up' if total_week > 0 else 'neutral',
            'chart': chart,
            'footer': [
                {'label': 'Total 7 jours', 'value': cls._format_int(total_week)},
                {'label': 'Jour le plus actif', 'value': f'{peak_label} · {cls._format_int(peak_value)}'},
                {'label': 'Moyenne par jour', 'value': f'{avg_day:.1f} publication{"s" if avg_day != 1 else ""}'},
            ],
        }

    @classmethod
    def get_demand_themes_widget(cls, *, limit: int = 5) -> dict:
        """Widget barres — intérêt commercial par thématique NLP (échelle 0–5)."""
        bars = cls._build_demand_theme_bars(limit=limit)
        top_name = bars[0]['name'] if bars and bars[0].get('name') != 'Aucune thématique' else '—'

        return {
            'title': 'Intérêt par thématique agricole',
            'subtitle': 'Score de demande moyen · publications déjà analysées',
            'help': (
                'Classement des secteurs où les contenus suscitent le plus d\'intérêt d\'achat. '
                'Le score va de 0 (faible) à 5 (forte demande) — calculé par l\'IA locale.'
            ),
            'badge_label': f'Top : {top_name[:22]}{"…" if len(top_name) > 22 else ""}',
            'badge_tone': 'up' if bars and top_name != '—' else 'neutral',
            'legend': [
                {
                    'term': 'Score / 5',
                    'desc': 'Niveau d\'intérêt commercial estimé pour cette thématique.',
                },
                {
                    'term': 'Barre',
                    'desc': 'Repère visuel sur l\'échelle 0–5 (pas une part de marché).',
                },
            ],
            'bars': bars,
            'empty': not bars or bars[0].get('name') == 'Aucune thématique',
        }

    @classmethod
    def get_engagement_by_category(cls, *, limit: int = 5) -> list[dict]:
        """Barres — score demande moyen par catégorie (compatibilité)."""
        return cls._build_demand_theme_bars(limit=limit)

    @classmethod
    def _build_demand_theme_bars(cls, *, limit: int = 5) -> list[dict]:
        """Barres thématiques avec échelle fixe 0–5 et textes d'aide."""
        Post = cls._post_model()
        rows = (
            cls._posts_qs()
            .filter(analysis_status=Post.AnalysisStatus.DONE)
            .exclude(category='')
            .values('category')
            .annotate(
                avg_score=Avg('demand_score'),
                total_views=Sum('view_count'),
                count=Count('id'),
            )
            .order_by('-avg_score')[:limit]
        )

        if not rows:
            return [{
                'name': 'Aucune thématique',
                'score': '—',
                'demand_label': 'En attente',
                'demand_tone': 'gris',
                'percent': 0,
                'color': 'gris',
                'publications_label': '0 publication',
                'views_label': '0 vue',
                'help': 'Lancez l\'analyse NLP sur vos publications pour voir ce classement.',
            }]

        bars = []
        for index, row in enumerate(rows):
            slug = row['category']
            raw_avg = row['avg_score'] or 0
            display_avg = min(float(raw_avg), 5.0)
            count = row['count']
            views = row['total_views'] or 0
            name = SocialDisplayService.CATEGORY_LABELS.get(
                slug, slug.replace('_', ' ').title(),
            )
            rounded = int(round(display_avg))

            bars.append({
                'name': name,
                'score': f'{display_avg:.1f}',
                'demand_label': cls._demand_label(rounded),
                'demand_tone': cls._demand_tone(rounded),
                'percent': max(4, round(display_avg / 5 * 100)),
                'color': CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
                'publications_label': (
                    f'{count} publication{"s" if count != 1 else ""} analysée{"s" if count != 1 else ""}'
                ),
                'views_label': f'{cls._format_int(views)} vues cumulées',
                'help': (
                    f'Intérêt moyen constaté sur « {name} » '
                    f'({cls._demand_label(rounded).lower()} demande).'
                ),
            })

        return bars

    @classmethod
    def get_recent_posts(cls, *, limit: int = 8) -> list[dict]:
        posts = (
            SocialPost.objects
            .all()
            .order_by('-demand_score', '-scraped_at')[:limit]
        )

        rows = []
        for post in posts:
            comments_goal = 20
            scraped = post.comments_scraped_count or len(post.comments or [])
            progress = min(100, round(scraped / comments_goal * 100))

            rows.append({
                'id': post.pk,
                'name': post.content[:55] + ('…' if len(post.content) > 55 else ''),
                'icon_color': cls._category_color(post.category),
                'author': post.author or '—',
                'author_initials': cls._initials(post.author or '?'),
                'date_label': cls._format_date(post.published_at or post.scraped_at),
                'views': cls._format_int(post.view_count) if post.view_count else '—',
                'comments_label': f'{scraped}/{comments_goal}',
                'progress': progress,
                'category': SocialDisplayService.CATEGORY_LABELS.get(
                    post.category, post.category or 'Non classé',
                ),
                'demand_score': post.demand_score,
                'demand_label': cls._demand_label(post.demand_score),
                'demand_tone': cls._demand_tone(post.demand_score),
                'status': post.get_analysis_status_display(),
                'status_tone': cls._status_tone(post.analysis_status),
                'sentiment': SocialDisplayService.SENTIMENT_LABELS.get(
                    post.sentiment, post.sentiment or '—',
                ),
                'sentiment_tone': cls._sentiment_tone(post.sentiment),
            })

        return rows

    @staticmethod
    def _build_line_chart(labels: list[str], values: list[int]) -> dict:
        width, height, padding = 400, 140, 24
        max_val = max(values) or 1
        step = (width - padding * 2) / max(len(values) - 1, 1)

        points = []
        for index, value in enumerate(values):
            x = round(padding + index * step, 1)
            y = round(height - padding - (value / max_val) * (height - padding * 2), 1)
            points.append({'x': x, 'y': y, 'label': labels[index], 'value': value})

        line_points = ' '.join(f"{p['x']},{p['y']}" for p in points)
        area_points = (
            f"{points[0]['x']},{height - padding} "
            + line_points
            + f" {points[-1]['x']},{height - padding}"
        )
        highlight = max(points, key=lambda item: item['value'])
        highlight = dict(highlight)
        highlight['tooltip_y'] = highlight['y'] - 42

        return {
            'labels': labels,
            'values': values,
            'line_points': line_points,
            'area_points': area_points,
            'points': points,
            'highlight': highlight,
        }

    @staticmethod
    def _format_int(value: int | None) -> str:
        if value is None:
            return '0'
        return f'{int(value):,}'.replace(',', '\u202f')

    @staticmethod
    def _format_trend(current: int, previous: int) -> dict:
        if previous <= 0:
            if current > 0:
                return {'label': f'+{current}', 'up': True}
            return {'label': '—', 'up': False}
        delta = ((current - previous) / previous) * 100
        sign = '+' if delta >= 0 else ''
        return {
            'label': f'{sign}{delta:.0f}%',
            'up': delta >= 0,
        }

    @staticmethod
    def _weekly_badge(current: int, previous: int, noun: str) -> str:
        """Libellé lisible pour l'évolution sur 7 jours (évite les « +176 » ambigus)."""
        if current <= 0 and previous <= 0:
            return 'Aucune activité récente'
        if previous <= 0:
            return f'{current} {noun}{"x" if current > 1 else ""} cette semaine'
        trend = DashboardDataService._format_trend(current, previous)
        return f'{trend["label"]} vs sem. dernière'

    @staticmethod
    def _weekday_label(day) -> str:
        names = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
        return names[day.weekday()]

    @staticmethod
    def _format_date(value) -> str:
        if not value:
            return '—'
        local = timezone.localtime(value)
        months = ('jan', 'fév', 'mar', 'avr', 'mai', 'jun', 'jul', 'aoû', 'sep', 'oct', 'nov', 'déc')
        return f'{local.day} {months[local.month - 1]} {local.year}'

    @staticmethod
    def _initials(name: str) -> str:
        parts = name.replace('@', '').split()
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[-1][:1]).upper()

    @staticmethod
    def _category_color(category: str) -> str:
        mapping = {
            'tracteurs_machinisme': 'orange',
            'irrigation': 'bleu',
            'semences_engrais': 'jaune',
            'marche_prix': 'orange',
            'solaire_pompage': 'bleu',
            'formation_conseil': 'gris',
        }
        return mapping.get(category, 'gris')

    @staticmethod
    def _status_tone(status: str) -> str:
        return {
            SocialPost.AnalysisStatus.DONE: 'success',
            SocialPost.AnalysisStatus.PENDING: 'warning',
            SocialPost.AnalysisStatus.PROCESSING: 'bleu',
            SocialPost.AnalysisStatus.FAILED: 'error',
        }.get(status, 'gris')

    @staticmethod
    def _demand_label(score: int) -> str:
        if score >= 4:
            return 'Forte'
        if score >= 2:
            return 'Modérée'
        return 'Faible'

    @staticmethod
    def _demand_tone(score: int) -> str:
        if score >= 4:
            return 'error'
        if score >= 2:
            return 'warning'
        return 'success'

    @staticmethod
    def _sentiment_tone(sentiment: str) -> str:
        return {
            'positive': 'success',
            'negative': 'error',
            'neutral': 'warning',
        }.get(sentiment, 'gris')
