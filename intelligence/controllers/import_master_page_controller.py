"""
Contrôleur Import Master — rapport DeepSeek + arrêt / relance.
"""

from __future__ import annotations

import logging
import threading

from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from intelligence.services.import_master_display_service import ImportMasterDisplayService

logger = logging.getLogger(__name__)


class ImportMasterPageController:
    """Page Import Master : rapport d'analyse comparative multi-domaines."""

    def __init__(self, request):
        self.request = request

    def index(self):
        if self.request.method == 'POST':
            action = self.request.POST.get('action')
            if action == 'analyser_domaines':
                return self._handle_domain_analysis()
            if action == 'arreter_analyse':
                return self._handle_stop_analysis()

        context = ImportMasterDisplayService.build_context()
        return render(self.request, 'dashboard/intelligence/import_master.html', context)

    def _handle_stop_analysis(self):
        from intelligence.models import ImportMasterDomainAnalysis
        from intelligence.services.collection_cancel_service import CollectionCancelService

        active = list(
            ImportMasterDomainAnalysis.objects.filter(
                status__in=(
                    ImportMasterDomainAnalysis.Status.PENDING,
                    ImportMasterDomainAnalysis.Status.RUNNING,
                )
            )
        )
        if not active:
            messages.info(self.request, 'Aucune analyse en cours à arrêter.')
            return HttpResponseRedirect(reverse('intelligence:import_master'))

        for analysis in active:
            tid = (analysis.celery_task_id or '').strip()
            if tid:
                try:
                    CollectionCancelService.request_cancel(tid)
                except Exception as exc:
                    logger.warning('Cancel flag Redis : %s', exc)
                try:
                    from yayematy_project.celery import app
                    app.control.revoke(tid, terminate=True, signal='SIGTERM')
                except Exception as exc:
                    logger.warning('Revoke Celery : %s', exc)

            analysis.status = ImportMasterDomainAnalysis.Status.STOPPED
            analysis.progress_message = 'Analyse arrêtée manuellement.'
            analysis.error_message = 'Arrêt demandé par l’utilisateur.'
            analysis.completed_at = timezone.now()
            analysis.save(
                update_fields=[
                    'status', 'progress_message', 'error_message', 'completed_at',
                ]
            )

        messages.success(
            self.request,
            'Analyse arrêtée. Vous pouvez la relancer maintenant.',
        )
        return HttpResponseRedirect(reverse('intelligence:import_master'))
    def _handle_domain_analysis(self):
        from intelligence.models import ImportMasterDomainAnalysis
        from intelligence.services.import_master_deepseek_service import (
            ImportMasterDeepSeekService,
        )
        from intelligence.tasks import run_import_master_domain_analysis

        # Nettoie les pending/running coincés avant de relancer
        ImportMasterDisplayService.expire_stuck_analyses(max_age_minutes=2)

        active = ImportMasterDomainAnalysis.objects.filter(
            status__in=(
                ImportMasterDomainAnalysis.Status.PENDING,
                ImportMasterDomainAnalysis.Status.RUNNING,
            )
        ).first()
        if active:
            messages.warning(
                self.request,
                'Une analyse est encore active — cliquez sur « Arrêter » puis relancez.',
            )
            return HttpResponseRedirect(reverse('intelligence:import_master'))

        selected = [
            str(s).strip()
            for s in self.request.POST.getlist('domain_slugs')
            if str(s).strip()
        ]
        available = {
            s['domain_slug']
            for s in ImportMasterDeepSeekService.collect_domain_snapshots()
            if s.get('domain_slug')
        }
        selected = [s for s in selected if s in available]
        if not selected:
            messages.error(
                self.request,
                'Sélectionnez au moins un domaine à inclure dans l’analyse.',
            )
            return HttpResponseRedirect(reverse('intelligence:import_master'))

        analysis = ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.PENDING,
            progress_message='Démarrage…',
            domains_snapshot=[{'domain_slug': s} for s in selected],
        )
        try:
            async_result = run_import_master_domain_analysis.delay(
                analysis.pk, domain_slugs=selected,
            )
            analysis.celery_task_id = async_result.id or ''
            analysis.progress_message = 'File d’attente Celery…'
            analysis.save(update_fields=['celery_task_id', 'progress_message'])
            messages.success(
                self.request,
                f'Analyse lancée — {len(selected)} domaine(s), '
                'Top 5 des 2 dernières analyses TI + prix sourcing.',
            )
        except Exception as exc:
            logger.exception('Celery delay Import Master échoué — fallback thread')
            # Fallback : exécution dans un thread si le broker/worker refuse la tâche
            analysis.progress_message = 'Exécution locale (hors Celery)…'
            analysis.status = ImportMasterDomainAnalysis.Status.RUNNING
            analysis.save(update_fields=['progress_message', 'status'])
            thread = threading.Thread(
                target=self._run_analysis_thread,
                args=(analysis.pk, selected),
                daemon=True,
                name=f'im-domain-{analysis.pk}',
            )
            thread.start()
            messages.warning(
                self.request,
                f'Celery indisponible ({exc}). Analyse lancée en local — '
                'gardez le serveur Django actif.',
            )

        return HttpResponseRedirect(reverse('intelligence:import_master'))

    @staticmethod
    def _run_analysis_thread(analysis_id: int, domain_slugs: list | None = None) -> None:
        from django.db import close_old_connections
        from intelligence.services.import_master_deepseek_service import (
            ImportMasterDeepSeekService,
        )

        close_old_connections()
        try:
            ImportMasterDeepSeekService.run_analysis(
                analysis_id=analysis_id,
                domain_slugs=domain_slugs,
            )
        except Exception as exc:
            from intelligence.models import ImportMasterDomainAnalysis
            ImportMasterDomainAnalysis.objects.filter(pk=analysis_id).update(
                status=ImportMasterDomainAnalysis.Status.FAILED,
                error_message=str(exc)[:2000],
                progress_message=str(exc)[:300],
                completed_at=timezone.now(),
            )
            logger.exception('Fallback thread Import Master échoué')
        finally:
            close_old_connections()


@require_GET
def import_master_domain_status(request):
    """Statut JSON de la dernière analyse comparative domaines."""
    from intelligence.models import ImportMasterDomainAnalysis

    ImportMasterDisplayService.expire_stuck_analyses(max_age_minutes=15)

    latest = ImportMasterDomainAnalysis.objects.order_by('-created_at').first()
    if not latest:
        return JsonResponse({'ok': True, 'status': 'none'})
    return JsonResponse({
        'ok': True,
        'status': latest.status,
        'progress_percent': latest.progress_percent,
        'progress_message': latest.progress_message,
        'analysis_id': latest.pk,
        'done': latest.status == ImportMasterDomainAnalysis.Status.DONE,
        'failed': latest.status in (
            ImportMasterDomainAnalysis.Status.FAILED,
            ImportMasterDomainAnalysis.Status.STOPPED,
        ),
        'running': latest.status in (
            ImportMasterDomainAnalysis.Status.PENDING,
            ImportMasterDomainAnalysis.Status.RUNNING,
        ),
    })
