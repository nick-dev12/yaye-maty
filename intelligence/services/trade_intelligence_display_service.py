"""Formatage UI Trade Intelligence."""

from __future__ import annotations

import json

from intelligence.models import MarketResearchSession


class TradeIntelligenceDisplayService:
    """Prépare le contexte template pour la page Trade Intelligence."""

    TAB_KEYS = (
        ('top_investissement', 'TOP INVESTISSEMENT'),
        ('plus_recherche', 'PLUS RECHERCHÉ (Google SN)'),
        ('plus_aime', 'PLUS AIMÉ (TikTok)'),
        ('vitesse_vente', 'VITESSE DE VENTE (Marketplaces SN)'),
    )

    @classmethod
    def build_page_context(cls, *, session: MarketResearchSession | None) -> dict:
        from intelligence.services.deepseek_analysis_service import DeepSeekAnalysisService

        analysis = (session.analysis_result if session else {}) or {}
        if session and analysis:
            analysis = DeepSeekAnalysisService.ensure_top10(
                dict(analysis),
                payload=session.collect_payload or {},
                domain_label=session.domain_label or '',
                category_label=session.keyword or session.category_label or '',
            )
        highlights = analysis.get('highlights') or {}
        tabs = []
        for key, label in cls.TAB_KEYS:
            tabs.append({
                'key': key,
                'label': label,
                'items': analysis.get(key) or [],
            })

        return {
            'session': session,
            'session_data': cls.session_to_dict(session) if session else None,
            'analysis_json': json.dumps(analysis, ensure_ascii=False),
            'has_results': bool(session and session.status == MarketResearchSession.Status.DONE and analysis),
            'analysis': analysis,
            'tabs': tabs,
            'active_tab': 'top_investissement',
            'highlights': {
                'top_pick': highlights.get('top_pick') or {},
                'forte_croissance': highlights.get('forte_croissance') or {},
                'meilleure_marge': highlights.get('meilleure_marge') or {},
            },
            'domain_label': session.domain_label if session else '',
            'category_label': (session.keyword or session.category_label) if session else '',
            'keyword': session.keyword if session else '',
        }

    @classmethod
    def session_to_dict(cls, session: MarketResearchSession) -> dict:
        from intelligence.services.deepseek_analysis_service import DeepSeekAnalysisService

        analysis = session.analysis_result or {}
        if analysis:
            analysis = DeepSeekAnalysisService.ensure_top10(
                dict(analysis),
                payload=session.collect_payload or {},
                domain_label=session.domain_label or '',
                category_label=session.keyword or session.category_label or '',
            )
        return {
            'id': session.pk,
            'domain_slug': session.domain_slug,
            'domain_label': session.domain_label,
            'category_slug': session.category_slug,
            'category_label': session.category_label,
            'keyword': session.keyword,
            'duration_minutes': session.duration_minutes,
            'sources': session.sources or [],
            'search_query': session.search_query,
            'status': session.status,
            'progress_percent': session.progress_percent,
            'progress_message': session.progress_message,
            'error_message': session.error_message,
            'analysis': analysis,
            'completed_at': session.completed_at.isoformat() if session.completed_at else None,
        }

    @classmethod
    def recommendation_class(cls, recommandation: str) -> str:
        text = (recommandation or '').lower()
        if any(x in text for x in ('éviter', 'eviter')):
            return 'ti-badge--avoid'
        if any(x in text for x in ('moyen', 'affaire')):
            return 'ti-badge--watch'
        return 'ti-badge--buy'

    @classmethod
    def score_class(cls, note: float) -> str:
        if note >= 7.5:
            return 'ti-score--high'
        if note >= 5.0:
            return 'ti-score--mid'
        return 'ti-score--low'
