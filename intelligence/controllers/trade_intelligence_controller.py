"""
Page Trade Intelligence — SENEGAL TRADE INTELLIGENCE + API recherche.
"""

from __future__ import annotations

import json

from celery.result import AsyncResult
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from intelligence.models import MarketResearchSession
from intelligence.services.trade_domain_catalog import DURATION_OPTIONS, TradeDomainCatalog
from intelligence.services.trade_intelligence_display_service import TradeIntelligenceDisplayService
from intelligence.tasks import run_market_research_session


class TradeIntelligenceController:
    """Contrôleur page /intelligence/ (Trade Intelligence)."""

    def __init__(self, request):
        self.request = request

    def index(self):
        session = self._resolve_session()
        context = TradeIntelligenceDisplayService.build_page_context(session=session)
        context['user'] = self.request.user
        domains = TradeDomainCatalog.list_domains()
        context['domains'] = domains
        context['domains_json'] = json.dumps(domains, ensure_ascii=False)
        context['duration_options'] = DURATION_OPTIONS
        context['active_task'] = self._active_task_meta(session)
        if session:
            context['selected_domain_slug'] = session.domain_slug
            context['selected_keyword'] = session.keyword
            context['selected_duration'] = session.duration_minutes
        return render(self.request, 'dashboard/intelligence/index.html', context)

    def _resolve_session(self) -> MarketResearchSession | None:
        session_id = self.request.GET.get('session')
        if session_id:
            return MarketResearchSession.objects.filter(pk=session_id).first()
        return (
            MarketResearchSession.objects.filter(
                status=MarketResearchSession.Status.DONE,
            )
            .order_by('-completed_at')
            .first()
        )

    def _active_task_meta(self, session: MarketResearchSession | None) -> dict | None:
        if not session or not session.celery_task_id:
            return None
        if session.status in (
            MarketResearchSession.Status.DONE,
            MarketResearchSession.Status.FAILED,
        ):
            return None
        remaining = None
        if session.started_at and session.duration_minutes:
            from django.utils import timezone
            elapsed = (timezone.now() - session.started_at).total_seconds()
            remaining = max(0, int(session.duration_minutes * 60 - elapsed))
        return {
            'task_id': session.celery_task_id,
            'session_id': session.pk,
            'status': session.status,
            'duration_minutes': session.duration_minutes,
            'remaining_seconds': remaining,
        }

    @staticmethod
    def _launch_sessions(
        domain_slugs: list[str],
        *,
        keyword: str = '',
        duration_minutes=20,
        sources=None,
    ) -> tuple[list[dict], str | None]:
        """Crée une session + tâche Celery par domaine. Retourne (sessions, erreur)."""
        from intelligence.services.market_research_orchestrator import MarketResearchOrchestrator

        launched: list[dict] = []
        for slug in domain_slugs:
            try:
                session = MarketResearchOrchestrator.create_session(
                    slug,
                    keyword,
                    duration_minutes=duration_minutes,
                    sources=sources,
                )
            except ValueError as exc:
                if not launched:
                    return [], str(exc)
                continue

            task = run_market_research_session.delay(session.pk)
            session.celery_task_id = task.id
            session.status = MarketResearchSession.Status.PENDING
            session.save(update_fields=['celery_task_id', 'status'])
            launched.append({
                'task_id': task.id,
                'session_id': session.pk,
                'domain_slug': session.domain_slug,
                'domain_label': session.domain_label,
                'duration_minutes': session.duration_minutes,
                'search_query': session.search_query,
            })
        if not launched:
            return [], 'Aucun domaine valide sélectionné.'
        return launched, None

    @staticmethod
    @require_POST
    def api_lancer(request):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            payload = {}

        keyword = (payload.get('keyword') or '').strip()
        duration_minutes = payload.get('duration_minutes', 20)
        sources = payload.get('sources')  # None = toutes

        raw_slugs = payload.get('domain_slugs')
        if isinstance(raw_slugs, list):
            domain_slugs = list(dict.fromkeys(
                str(s).strip() for s in raw_slugs if str(s).strip()
            ))
        else:
            single = (payload.get('domain_slug') or '').strip()
            domain_slugs = [single] if single else []

        if not domain_slugs:
            return JsonResponse(
                {'success': False, 'error': 'Sélectionnez au moins un domaine.'},
                status=400,
            )

        launched, error = TradeIntelligenceController._launch_sessions(
            domain_slugs,
            keyword=keyword,
            duration_minutes=duration_minutes,
            sources=sources,
        )
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)

        if len(launched) == 1:
            one = launched[0]
            return JsonResponse({
                'success': True,
                'batch': False,
                'task_id': one['task_id'],
                'session_id': one['session_id'],
                'domain_slug': one['domain_slug'],
                'domain_label': one['domain_label'],
                'duration_minutes': one['duration_minutes'],
                'search_query': one['search_query'],
            })

        return JsonResponse({
            'success': True,
            'batch': True,
            'count': len(launched),
            'sessions': launched,
            'duration_minutes': launched[0]['duration_minutes'],
        })

    @staticmethod
    @require_POST
    def api_arreter(request):
        """Arrêt coopératif — l'orchestrateur passe à l'analyse DeepSeek."""
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            payload = {}

        task_id = (payload.get('task_id') or '').strip()
        if not task_id:
            return JsonResponse({'success': False, 'error': 'task_id requis.'}, status=400)

        from intelligence.services.collection_cancel_service import CollectionCancelService

        CollectionCancelService.request_cancel(task_id)
        return JsonResponse({
            'success': True,
            'message': 'Arrêt demandé — analyse des données collectées en cours…',
        })

    @staticmethod
    @require_GET
    def api_statut(request, task_id: str):
        result = AsyncResult(task_id)
        state = result.state or 'PENDING'
        meta = result.info if isinstance(result.info, dict) else {}
        session_id = meta.get('session_id')

        session_data = None
        if session_id:
            session = MarketResearchSession.objects.filter(pk=session_id).first()
            if session:
                session_data = TradeIntelligenceDisplayService.session_to_dict(session)
        else:
            session = MarketResearchSession.objects.filter(celery_task_id=task_id).first()
            if session:
                session_id = session.pk
                session_data = TradeIntelligenceDisplayService.session_to_dict(session)

        if state == 'SUCCESS':
            body = result.result if isinstance(result.result, dict) else {}
            return JsonResponse({
                'state': 'SUCCESS',
                'pourcentage': body.get('pourcentage', 100),
                'message': body.get('message', 'Terminé.'),
                'phase': body.get('phase', 'done'),
                'session': session_data,
            })

        if state == 'FAILURE':
            err = str(result.result) if result.result else 'Échec de la tâche.'
            return JsonResponse({
                'state': 'FAILURE',
                'pourcentage': 0,
                'message': err,
                'phase': 'failed',
                'session': session_data,
            })

        if state == 'PROGRESS':
            return JsonResponse({
                'state': 'PROGRESS',
                'pourcentage': meta.get('pourcentage', 0),
                'message': meta.get('message', 'En cours…'),
                'phase': meta.get('phase', 'collecte'),
                'session': session_data,
            })

        return JsonResponse({
            'state': 'PENDING',
            'pourcentage': 0,
            'message': 'En file d\'attente…',
            'phase': 'pending',
            'session': session_data,
        })
