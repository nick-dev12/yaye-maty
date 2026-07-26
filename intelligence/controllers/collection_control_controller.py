"""

Page Collecte manuelle — déclenchement Celery + suivi de progression.

"""



from __future__ import annotations



import json



from celery.result import AsyncResult

from django.http import JsonResponse

from django.shortcuts import render

from django.views.decorators.http import require_GET, require_POST



from intelligence.services.collection_cancel_service import CollectionCancelService
from intelligence.services.collection_task_session_service import CollectionTaskSessionService
from intelligence.services.manual_collection_service import ManualCollectionService

from intelligence.tasks import lancer_collecte_manuelle





class CollectionControlController:

    """Interface de lancement manuel des collectes."""



    def __init__(self, request):

        self.request = request



    def index(self):

        context = ManualCollectionService.get_page_context()

        context['user'] = self.request.user

        context['active_tasks'] = CollectionTaskSessionService.get_resumable(self.request)

        from intelligence.services.celery_ui_launch_service import CeleryUiLaunchService

        context.update(CeleryUiLaunchService.get_ui_context())
        return render(self.request, 'dashboard/intelligence/collection_control.html', context)



    @staticmethod

    @require_POST

    def api_lancer(request):

        """Démarre une tâche Celery et renvoie l'identifiant de suivi."""

        try:

            payload = json.loads(request.body.decode('utf-8') or '{}')

        except json.JSONDecodeError:

            payload = {}



        job = payload.get('job') or request.POST.get('job') or ManualCollectionService.JOB_FULL

        keyword_id = payload.get('keyword_id') or request.POST.get('keyword_id')

        keyword_id = int(keyword_id) if keyword_id else None
        raw_test = payload.get('test_mode', request.POST.get('test_mode', False))
        if isinstance(raw_test, bool):
            test_mode = raw_test
        else:
            test_mode = str(raw_test).lower() in ('1', 'true', 'yes', 'on')

        if test_mode:
            from intelligence.services.test_data_purge_service import TestDataPurgeService
            TestDataPurgeService.purge_all()

        from intelligence.services.celery_health_service import celery_workers_online

        ok, health_msg = celery_workers_online(timeout=1.5)
        if not ok:
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'worker_offline',
                    'message': health_msg,
                },
                status=503,
            )

        # Libère une éventuelle session orpheline avant un nouveau lancement
        CollectionTaskSessionService.clear_task(request, test_mode=test_mode)

        task = lancer_collecte_manuelle.delay(
            job=job,
            keyword_id=keyword_id,
            test_mode=test_mode,
        )
        CollectionTaskSessionService.save_task(
            request,
            task.id,
            test_mode=test_mode,
            job=job,
        )
        return JsonResponse({
            'task_id': task.id,
            'job': job,
            'test_mode': test_mode,
            'worker': health_msg,
        })



    @staticmethod

    @require_POST

    def api_arreter(request):

        """Demande l'arrêt coopératif puis enchaînement NLP."""

        try:

            payload = json.loads(request.body.decode('utf-8') or '{}')

        except json.JSONDecodeError:

            payload = {}



        task_id = payload.get('task_id') or request.POST.get('task_id')

        if not task_id:

            return JsonResponse({'ok': False, 'message': 'Identifiant de tâche manquant.'}, status=400)



        result = AsyncResult(task_id)

        if result.state in ('SUCCESS', 'FAILURE', 'REVOKED'):

            CollectionTaskSessionService.clear_if_matches(request, task_id)

            return JsonResponse({'ok': False, 'message': 'Cette tâche est déjà terminée.'}, status=400)

        # PENDING orphelin (worker était arrêté) → libérer la session immédiatement
        if result.state == 'PENDING':

            CollectionTaskSessionService.liberate_task(request, task_id)

            return JsonResponse({

                'ok': True,

                'liberated': True,

                'message': 'Session libérée — aucun worker n’a pris la tâche. Relancez .\\scripts\\run_celery_worker.ps1 puis retestez.',

            })

        CollectionCancelService.request_cancel(str(task_id))

        return JsonResponse({

            'ok': True,

            'message': (
                'Arrêt demandé — le worker terminera l’élément en cours, puis '
                'traitera et affichera automatiquement les données partielles.'
            ),

        })



    @staticmethod

    @require_GET

    def api_statut(request, task_id: str):

        """Retourne l'état Celery pour la barre de progression."""

        result = AsyncResult(task_id)

        response = {'etat': result.state}



        if result.state == 'PROGRESS':

            info = result.info or {}

            if isinstance(info, dict):

                response['pourcentage'] = info.get('pourcentage', 0)

                response['message'] = info.get('message', 'Collecte en cours…')

                response['phase'] = info.get('phase', 'collecte')

                response['can_stop'] = info.get('can_stop', False)
                response['test_mode'] = info.get('test_mode', False)

            else:

                response['pourcentage'] = 0

                response['message'] = 'Collecte en cours…'

                response['phase'] = 'collecte'

                response['can_stop'] = False

        elif result.state == 'SUCCESS':

            CollectionTaskSessionService.clear_if_matches(request, task_id)

            info = result.result or {}

            if isinstance(info, dict):
                details = info.get('details', info)

                response['pourcentage'] = info.get('pourcentage', 100)

                response['message'] = info.get('message', 'Terminé avec succès.')

                response['resultats'] = info.get('nouvelles_donnees', 0)

                response['phase'] = info.get('phase', 'done')

                response['details'] = details
                response['cancelled'] = bool(
                    isinstance(details, dict) and details.get('cancelled')
                )
                response['partial'] = response['cancelled']

            else:

                response['pourcentage'] = 100

                response['message'] = 'Terminé.'

                response['resultats'] = 0

                response['phase'] = 'done'

        elif result.state == 'FAILURE':

            CollectionTaskSessionService.clear_if_matches(request, task_id)

            response['pourcentage'] = 0

            response['message'] = str(result.info) if result.info else 'Échec de la collecte.'

            response['phase'] = 'error'

        else:

            # PENDING / STARTED / autre — une attente longue n'est orpheline
            # que si aucun worker ne répond. Un worker solo peut légitimement
            # être occupé par une tâche Beat pendant plusieurs minutes.
            pending_stale = CollectionTaskSessionService.is_pending_stale(
                request,
                task_id,
                state=result.state,
            )
            worker_offline = False
            if pending_stale:
                from intelligence.services.celery_health_service import celery_workers_online
                worker_offline = not celery_workers_online(timeout=0.8)[0]

            if pending_stale and worker_offline:

                CollectionTaskSessionService.liberate_task(request, task_id)

                response['etat'] = 'FAILURE'

                response['pourcentage'] = 0

                response['message'] = (
                    'Aucun worker Celery n’a pris la tâche (worker arrêté ou saturé). '
                    'Session libérée. Relancez : .\\scripts\\run_celery_worker.ps1 puis retestez.'
                )

                response['phase'] = 'error'

                response['can_stop'] = False

            else:

                response['pourcentage'] = 0

                response['message'] = 'En attente du worker Celery…'

                response['phase'] = 'collecte'

                response['can_stop'] = True



        return JsonResponse(response)



    @staticmethod
    @require_POST
    def api_reset_session(request):
        """Libère la session test/prod bloquée + purge file PENDING optionnelle."""
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            payload = {}

        raw_test = payload.get('test_mode', True)
        if isinstance(raw_test, bool):
            test_mode = raw_test
        else:
            test_mode = str(raw_test).lower() in ('1', 'true', 'yes', 'on')

        session_payload = request.session.get(
            CollectionTaskSessionService._key(test_mode)
        ) or {}
        task_id = session_payload.get('task_id') or payload.get('task_id')
        cancelling = False
        if task_id:
            result = AsyncResult(str(task_id))
            if result.state in ('PROGRESS', 'STARTED'):
                # Conserver la session et le polling : le worker doit finaliser
                # les données partielles, puis l'UI ouvrira les résultats.
                CollectionCancelService.request_cancel(str(task_id))
                cancelling = True
            else:
                # PENDING ou tâche terminée : aucune donnée en cours à finaliser.
                CollectionTaskSessionService.liberate_task(request, str(task_id))
        else:
            CollectionTaskSessionService.clear_task(request, test_mode=test_mode)

        purged = 0
        if payload.get('purge_queue'):
            from intelligence.services.celery_health_service import purge_celery_queue
            purged = purge_celery_queue()

        from intelligence.services.celery_health_service import celery_workers_online
        ok, health_msg = celery_workers_online(timeout=1.2)

        return JsonResponse({
            'ok': True,
            'cancelling': cancelling,
            'session_released': not cancelling,
            'message': (
                'Arrêt demandé. Finalisation des données partielles en cours…'
                if cancelling
                else 'Session libérée. Vous pouvez lancer une nouvelle collecte.'
            ),
            'worker_online': ok,
            'worker_message': health_msg,
            'purged_tasks': purged,
        })

    @staticmethod
    @require_GET
    def api_celery_status(request):
        """État worker / beat — lancement UI (dev local)."""
        from intelligence.services.celery_ui_launch_service import CeleryUiLaunchService

        if not CeleryUiLaunchService.is_enabled():
            return JsonResponse({'enabled': False}, status=403)
        return JsonResponse(CeleryUiLaunchService.get_status())

    @staticmethod
    @require_POST
    def api_celery_start(request):
        """Démarre worker ou beat dans une fenêtre terminal."""
        from intelligence.services.celery_ui_launch_service import (
            CeleryUiLaunchError,
            CeleryUiLaunchService,
        )

        if not CeleryUiLaunchService.is_enabled():
            return JsonResponse(
                {'ok': False, 'message': 'Lancement UI désactivé sur cet environnement.'},
                status=403,
            )
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            payload = {}
        component = payload.get('component') or request.POST.get('component') or 'worker'
        try:
            result = CeleryUiLaunchService.start(component)
            return JsonResponse(result)
        except CeleryUiLaunchError as exc:
            return JsonResponse({'ok': False, 'message': str(exc)}, status=400)

    @staticmethod
    @require_POST
    def api_celery_stop(request):
        """Arrête un processus Celery lancé depuis l'interface."""
        from intelligence.services.celery_ui_launch_service import (
            CeleryUiLaunchError,
            CeleryUiLaunchService,
        )

        if not CeleryUiLaunchService.is_enabled():
            return JsonResponse(
                {'ok': False, 'message': 'Lancement UI désactivé sur cet environnement.'},
                status=403,
            )
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            payload = {}
        component = payload.get('component') or request.POST.get('component') or 'worker'
        try:
            result = CeleryUiLaunchService.stop(component)
            return JsonResponse(result)
        except CeleryUiLaunchError as exc:
            return JsonResponse({'ok': False, 'message': str(exc)}, status=400)


