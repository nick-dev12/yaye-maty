"""Historique Archives — sessions Trade Intelligence (max 40)."""

from __future__ import annotations

from intelligence.models import MarketResearchSession

MAX_RESEARCH_SESSIONS = 40


class TradeResearchArchiveService:
    """Liste et purge l'historique des recherches marché."""

    MAX = MAX_RESEARCH_SESSIONS

    @classmethod
    def prune_to_limit(cls, limit: int | None = None, *, queryset=None) -> int:
        """
        Conserve les `limit` sessions les plus récentes ; supprime les plus anciennes.
        Retourne le nombre de sessions supprimées.
        """
        max_keep = int(limit if limit is not None else cls.MAX)
        if max_keep < 1:
            max_keep = cls.MAX

        base = queryset if queryset is not None else MarketResearchSession.objects.all()
        total = base.count()
        if total <= max_keep:
            return 0

        to_delete = total - max_keep
        oldest_ids = list(
            base.order_by('created_at', 'pk').values_list('pk', flat=True)[:to_delete]
        )
        deleted, _ = MarketResearchSession.objects.filter(pk__in=oldest_ids).delete()
        return deleted

    @classmethod
    def list_sessions(cls, *, limit: int | None = None) -> list[MarketResearchSession]:
        """Sessions récentes pour la page Archives (plus récente d'abord)."""
        max_n = int(limit if limit is not None else cls.MAX)
        return list(
            MarketResearchSession.objects
            .order_by('-created_at', '-pk')[:max_n]
        )

    @classmethod
    def delete_session(cls, session_id: int) -> bool:
        """Supprime une session d'archive. Retourne True si une ligne a été supprimée."""
        deleted, _details = MarketResearchSession.objects.filter(pk=session_id).delete()
        return deleted > 0

    @classmethod
    def session_card(cls, session: MarketResearchSession) -> dict:
        """Résumé UI d'une session d'archive."""
        analysis = session.analysis_result or {}
        top = (analysis.get('top_investissement') or analysis.get('highlights', {}).get('top_pick') or {})
        if isinstance(top, list):
            top_pick = top[0] if top else {}
        else:
            top_pick = top if isinstance(top, dict) else {}
        highlights = analysis.get('highlights') or {}
        if not top_pick and isinstance(highlights.get('top_pick'), dict):
            top_pick = highlights['top_pick']

        note = top_pick.get('note')
        try:
            note_f = float(note) if note is not None else None
        except (TypeError, ValueError):
            note_f = None

        return {
            'id': session.pk,
            'domain_label': session.domain_label,
            'keyword': session.keyword or session.category_label or '—',
            'search_query': session.search_query,
            'duration_minutes': session.duration_minutes,
            'sources': session.sources or [],
            'status': session.status,
            'status_label': session.get_status_display(),
            'is_done': session.status == MarketResearchSession.Status.DONE,
            'top_product': top_pick.get('produit') or '—',
            'top_note': note_f,
            'top_reco': top_pick.get('recommandation') or '',
            'created_at': session.created_at,
            'completed_at': session.completed_at,
            'error_message': (session.error_message or '')[:200],
            'view_url_name': 'intelligence:index',
        }
