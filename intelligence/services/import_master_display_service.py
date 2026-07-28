"""
Contexte UI de la page Import Master — opportunités du jour + veille concurrentielle.
"""

from __future__ import annotations

from django.utils import timezone

from intelligence.models import ImportOpportunity
from intelligence.services.competitor_watch_service import CompetitorWatchService

DECISION_META = {
    ImportOpportunity.Decision.BUY: {
        'label': 'Acheter',
        'tone': 'orange',
        'hint': 'Demande forte, marché accessible — importer en priorité.',
    },
    ImportOpportunity.Decision.WATCH: {
        'label': 'Surveiller',
        'tone': 'jaune',
        'hint': 'Signaux encourageants — attendre confirmation avant d\'importer.',
    },
    ImportOpportunity.Decision.AVOID: {
        'label': 'Éviter',
        'tone': 'gris',
        'hint': 'Demande faible ou marché saturé — ne pas importer pour l\'instant.',
    },
}

SUBSCORE_META = (
    ('demand_score', 'Demande', 'Intentions d\'achat + vues réseaux'),
    ('trend_score', 'Tendance', 'Google Trends + requêtes en hausse'),
    ('competition_score', 'Concurrence', 'Plus haut = marché plus accessible'),
    ('price_score', 'Prix', 'Marge de positionnement possible'),
)


class ImportMasterDisplayService:
    """Prépare le contexte complet de la page Import Master."""

    @classmethod
    def build_context(cls) -> dict:
        latest_date = (
            ImportOpportunity.objects.values_list('snapshot_date', flat=True)
            .order_by('-snapshot_date')
            .first()
        )
        rows = list(
            ImportOpportunity.objects.filter(snapshot_date=latest_date)
            .select_related('keyword')
            .order_by('rank')
        ) if latest_date else []

        opportunities = [cls._opportunity_card(row) for row in rows]
        counts = cls._decision_counts(rows)
        trending = [o for o in opportunities if o['trend_score'] >= 50][:6]
        competitor_watch = CompetitorWatchService.get_watch_for_keywords(limit=8)
        price_comparison = cls._price_comparison()

        return {
            'im_snapshot_date': latest_date,
            'im_is_today': latest_date == timezone.localdate() if latest_date else False,
            'im_summary_line': cls._summary_line(counts, latest_date),
            'im_counts': counts,
            'im_opportunities': opportunities,
            'im_has_data': bool(opportunities),
            'im_trending': trending,
            'im_competitor_watch': competitor_watch,
            'im_price_comparison': price_comparison,
        }

    @classmethod
    def get_home_preview(cls, *, limit: int = 3) -> list[dict]:
        """Top opportunités « Acheter » (ou meilleures dispo) pour l'accueil."""
        latest_date = (
            ImportOpportunity.objects.values_list('snapshot_date', flat=True)
            .order_by('-snapshot_date')
            .first()
        )
        if not latest_date:
            return []
        qs = ImportOpportunity.objects.filter(snapshot_date=latest_date)
        buys = list(qs.filter(decision=ImportOpportunity.Decision.BUY).order_by('rank')[:limit])
        if len(buys) < limit:
            extra = list(
                qs.exclude(decision=ImportOpportunity.Decision.BUY)
                .order_by('rank')[: limit - len(buys)]
            )
            buys.extend(extra)
        return [cls._opportunity_card(row) for row in buys]

    # ------------------------------------------------------------------
    # Blocs internes
    # ------------------------------------------------------------------

    @classmethod
    def _opportunity_card(cls, row: ImportOpportunity) -> dict:
        meta = DECISION_META.get(row.decision, DECISION_META[ImportOpportunity.Decision.WATCH])
        return {
            'rank': row.rank,
            'keyword': row.keyword_text,
            'product_name': row.product_name,
            'score': row.score,
            'decision': row.decision,
            'decision_label': meta['label'],
            'decision_tone': meta['tone'],
            'decision_hint': meta['hint'],
            'reasons': row.decision_reasons or [],
            'demand_score': row.demand_score,
            'trend_score': row.trend_score,
            'competition_score': row.competition_score,
            'price_score': row.price_score,
            'subscores': [
                {
                    'label': label,
                    'hint': hint,
                    'value': getattr(row, field_name),
                }
                for field_name, label, hint in SUBSCORE_META
            ],
            'price_min': row.market_price_min_xof,
            'price_avg': row.market_price_avg_xof,
            'price_max': row.market_price_max_xof,
            'suggested_price': row.suggested_price_xof,
            'jumia_sellers': row.jumia_sellers,
            'jiji_listings': row.jiji_listings_count,
            'purchase_intents': row.purchase_intent_count,
            'total_views': row.total_views,
            'stock_alert': row.stock_alert,
        }

    @staticmethod
    def _decision_counts(rows: list[ImportOpportunity]) -> dict:
        buy = sum(1 for r in rows if r.decision == ImportOpportunity.Decision.BUY)
        avoid = sum(1 for r in rows if r.decision == ImportOpportunity.Decision.AVOID)
        return {
            'buy': buy,
            'watch': len(rows) - buy - avoid,
            'avoid': avoid,
            'total': len(rows),
        }

    @staticmethod
    def _summary_line(counts: dict, latest_date) -> str:
        if not counts['total']:
            return (
                'Aucune opportunité calculée — activez des mots-clés dans Paramètres, '
                'collectez des données puis lancez un recalcul.'
            )
        parts = []
        if counts['buy']:
            parts.append(f'{counts["buy"]} opportunité(s) « Acheter »')
        if counts['watch']:
            parts.append(f'{counts["watch"]} à surveiller')
        if counts['avoid']:
            parts.append(f'{counts["avoid"]} à éviter')
        return ' · '.join(parts) + f' sur {counts["total"]} mot(s)-clé(s) analysé(s).'

    @staticmethod
    def _price_comparison() -> list[dict]:
        from intelligence.services.jiji_market_signal_service import JijiMarketSignalService

        try:
            return JijiMarketSignalService.get_arbitrage_opportunities(limit=8)
        except Exception:
            return []
