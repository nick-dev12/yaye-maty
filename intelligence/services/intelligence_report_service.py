"""
Rapport Intelligence — Top 10 unifiés pour la page /intelligence/.
Format normalisé lisible par des non-initiés.
"""

from __future__ import annotations

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.jiji_ranking_service import JijiRankingService
from intelligence.services.jumia_ranking_service import JumiaRankingService
from intelligence.services.social_ranking_service import SocialRankingService


class IntelligenceReportService:
    """Agrège les classements marché en structure unique pour l'UI."""

    SECTIONS = (
        {
            'id': 'sourcing',
            'key': 'top_sourcing',
            'label': 'À sourcer',
            'title': 'Top 10 à sourcer en priorité',
            'hint': (
                'Produits à mettre en stock — score combinant intentions d\'achat, '
                'vues réseaux et tendances Google.'
            ),
            'empty_action': 'Lancez une collecte réseaux puis l\'analyse hybride.',
            'empty_url_name': 'intelligence:collecte',
        },
        {
            'id': 'searches',
            'key': 'top_searches',
            'label': 'Google',
            'title': 'Top 10 recherches Google',
            'hint': 'Ce que les Sénégalais tapent sur Google — vos domaines configurés.',
            'empty_action': 'Lancez une découverte Google Trends.',
            'empty_url_name': 'intelligence:domaines',
        },
        {
            'id': 'social_views',
            'key': 'top_social_views',
            'label': 'Vues réseaux',
            'title': 'Top 10 les plus regardés',
            'hint': (
                'Publications TikTok/Facebook les plus vues, liées à vos mots-clés Paramètres.'
            ),
            'empty_action': 'Lancez le scraping réseaux sociaux.',
            'empty_url_name': 'intelligence:collecte',
        },
        {
            'id': 'social_likes',
            'key': 'top_social_likes',
            'label': 'J\'aime',
            'title': 'Top 10 les plus aimés',
            'hint': 'Publications avec le plus de likes et d\'engagement.',
            'empty_action': 'Lancez le scraping réseaux sociaux.',
            'empty_url_name': 'intelligence:collecte',
        },
        {
            'id': 'jiji',
            'key': 'top_jiji_analyzed',
            'label': 'Jiji NLP',
            'title': 'Top 10 annonces Jiji analysées',
            'hint': (
                'Annonces locales filtrées et analysées (produit agricole, pertinence, '
                'sentiment) — prêtes pour le sourcing.'
            ),
            'empty_action': 'Lancez la collecte Jiji.',
            'empty_url_name': 'intelligence:collecte',
        },
        {
            'id': 'jumia',
            'key': 'top_jumia_popular',
            'label': 'Jumia',
            'title': 'Top 10 best-sellers Jumia',
            'hint': 'Produits Jumia avec le plus d\'avis clients — popularité marché.',
            'empty_action': 'Lancez la collecte Jumia.',
            'empty_url_name': 'intelligence:collecte',
        },
    )

    @classmethod
    def build_report(cls, *, since=None, until=None, limit: int = 10) -> dict:
        from intelligence.services.discovered_display_service import DiscoveredDisplayService
        from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService

        rising_queries = {
            r['query'].lower()
            for r in DiscoveredDisplayService.get_rising_preview(limit=50, since=since, until=until)
        }

        top_sourcing = cls._normalize_sourcing(
            PurchaseRecommendationService.get_top_for_display(limit=limit, since=since, until=until),
        )
        top_searches = cls._normalize_searches(
            DiscoveredDisplayService.get_top_queries(limit=limit, since=since, until=until),
            rising_queries=rising_queries,
        )
        top_social_views = SocialRankingService.get_top_posts(
            metric='views', limit=limit, since=since, until=until,
        )
        top_social_likes = SocialRankingService.get_top_posts(
            metric='likes', limit=limit, since=since, until=until,
        )
        top_jiji_analyzed = JijiRankingService.get_top_analyzed(limit=limit)
        top_jiji_views = JijiRankingService.get_top_listings(limit=limit)
        top_jumia_popular = JumiaRankingService.get_top_products(limit=limit)

        rankings = {
            'top_sourcing': top_sourcing,
            'top_searches': top_searches,
            'top_social_views': top_social_views,
            'top_social_likes': top_social_likes,
            'top_jiji_analyzed': top_jiji_analyzed,
            'top_jiji_views': top_jiji_views,
            'top_jumia_popular': top_jumia_popular,
        }

        cls._apply_progress_bars(rankings)

        sections = []
        for meta in cls.SECTIONS:
            items = rankings.get(meta['key'], [])
            sections.append({
                **meta,
                'items': items,
                'has_data': bool(items),
                'count': len(items),
            })

        preview_cards = cls._build_preview_cards(rankings)

        return {
            'sections': sections,
            'rankings': rankings,
            'preview_cards': preview_cards,
            'has_any_data': any(s['has_data'] for s in sections),
        }

    @classmethod
    def _normalize_sourcing(cls, rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            purchase = int(row.get('purchase_intent_count') or 0)
            info = int(row.get('info_intent_count') or 0)
            views = int(row.get('total_views') or 0)
            posts = int(row.get('related_posts') or 0)
            why_parts = []
            if purchase:
                why_parts.append(
                    f'{purchase} commentaire{"s" if purchase > 1 else ""} « je veux acheter »'
                )
            if views:
                why_parts.append(f'{views:,} vues sur les réseaux'.replace(',', ' '))
            if posts and not views:
                why_parts.append(f'{posts} publication(s) liée(s)')
            if row.get('trends_boost'):
                why_parts.append('boosté par Google Trends')
            why_here = row.get('why_here') or (
                ' · '.join(why_parts) if why_parts else row.get('evidence_text', '')
            )

            badges = []
            if row.get('is_hot'):
                badges.append({'tone': 'orange', 'label': 'Priorité'})
            if row.get('stock_alert') == 'critical':
                badges.append({'tone': 'orange', 'label': 'Rupture Jumia'})
            elif row.get('stock_alert') == 'watch':
                badges.append({'tone': 'jaune', 'label': 'Stock fragile'})

            secondary = []
            if purchase:
                secondary.append({'label': 'Achats', 'value': str(purchase)})
            if info:
                secondary.append({'label': 'Infos', 'value': str(info)})
            if row.get('avg_market_price_xof'):
                secondary.append({
                    'label': 'Prix moy.',
                    'value': f'{int(row["avg_market_price_xof"]):,} FCFA'.replace(',', ' '),
                })

            out.append({
                'rank': row['rank'],
                'title': row['product_name'],
                'subtitle': (row.get('category') or '').title() or 'Catalogue YAYEMATY',
                'why_here': why_here,
                'primary_value': int(row.get('score') or 0),
                'primary_label': 'score',
                'primary_icon': 'score',
                'badges': badges,
                'secondary': secondary,
                'url': '',
                'anchor': '#publications',
                'source': 'sourcing',
                'score_raw': row.get('score_raw'),
                'tone': row.get('tone', 'bleu'),
            })
        return out

    @classmethod
    def _normalize_searches(cls, rows: list[dict], *, rising_queries: set[str]) -> list[dict]:
        out = []
        for i, row in enumerate(rows, start=1):
            query = row['query']
            is_rising = query.lower() in rising_queries
            badges = []
            if is_rising:
                badges.append({'tone': 'jaune', 'label': 'En hausse'})
            badges.append({'tone': 'bleu', 'label': row.get('domain_label', '')})

            out.append({
                'rank': i,
                'title': query,
                'subtitle': f"Domaine : {row.get('domain_label', row.get('domain', ''))}",
                'why_here': (
                    f'Recherche populaire au Sénégal'
                    + (' — tendance en hausse cette semaine' if is_rising else '')
                ),
                'primary_value': int(row.get('score') or 0),
                'primary_label': 'intérêt',
                'primary_icon': 'search',
                'badges': badges,
                'secondary': [{'label': 'Rang', 'value': f'#{i}'}],
                'url': '',
                'anchor': '#intel-expert',
                'source': 'google',
            })
        return out

    @classmethod
    def _apply_progress_bars(cls, rankings: dict[str, list[dict]]) -> None:
        for items in rankings.values():
            if not items:
                continue
            max_val = max(int(it.get('primary_value') or 0) for it in items) or 1
            for it in items:
                val = int(it.get('primary_value') or 0)
                it['progress_pct'] = max(8, round(val / max_val * 100))

    @classmethod
    def _build_preview_cards(cls, rankings: dict[str, list]) -> list[dict]:
        """3 cartes aperçu pour le résumé — une par canal principal."""
        cards = []
        specs = (
            ('top_sourcing', 'orange', 'À sourcer', '#top10-hub', 'sourcing'),
            ('top_social_views', 'jaune', 'Plus vu', '#top10-hub', 'social_views'),
            ('top_jiji_analyzed', 'orange', 'Jiji analysé', '#top10-hub', 'jiji'),
        )
        for key, tone, label, anchor, tab_id in specs:
            items = rankings.get(key) or []
            if not items:
                continue
            top = items[0]
            cards.append({
                'tone': tone,
                'label': label,
                'title': top['title'][:60],
                'metric': f"{top['primary_value']:,} {top['primary_label']}".replace(',', ' '),
                'why': top.get('why_here', '')[:100],
                'anchor': anchor,
                'tab_id': tab_id,
            })
        return cards[:3]
