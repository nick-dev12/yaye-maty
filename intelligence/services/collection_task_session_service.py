"""Persistance session Django — reprise de la barre de progression après actualisation."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from celery.result import AsyncResult

from intelligence.services.test_data_window_service import TestDataWindowService

SESSION_KEY_TEST = 'collecte_tache_test'
SESSION_KEY_PROD = 'collecte_tache_prod'
_RUNNING_STATES = frozenset({'PENDING', 'PROGRESS', 'STARTED'})
# PENDING sans démarrage worker = souvent une tâche orpheline (worker arrêté)
_PENDING_STALE_SECONDS = 45


class CollectionTaskSessionService:
    """Mémorise les tâches Celery actives par utilisateur (test / production)."""

    SESSION_KEY_TEST = SESSION_KEY_TEST
    SESSION_KEY_PROD = SESSION_KEY_PROD
    PENDING_STALE_SECONDS = _PENDING_STALE_SECONDS

    @classmethod
    def _key(cls, test_mode: bool) -> str:
        return cls.SESSION_KEY_TEST if test_mode else cls.SESSION_KEY_PROD

    @classmethod
    def save_task(cls, request, task_id: str, *, test_mode: bool, job: str) -> None:
        request.session[cls._key(test_mode)] = {
            'task_id': str(task_id),
            'test_mode': test_mode,
            'job': job,
            'queued_at': datetime.now(dt_timezone.utc).isoformat(),
        }
        if test_mode:
            TestDataWindowService.mark_started(request)
            TestDataWindowService.touch_job(request, job)
        request.session.modified = True

    @classmethod
    def clear_task(cls, request, *, test_mode: bool) -> None:
        key = cls._key(test_mode)
        if key in request.session:
            del request.session[key]
            request.session.modified = True

    @classmethod
    def clear_if_matches(cls, request, task_id: str) -> None:
        for test_mode in (True, False):
            payload = request.session.get(cls._key(test_mode))
            if payload and payload.get('task_id') == str(task_id):
                cls.clear_task(request, test_mode=test_mode)
                if test_mode:
                    TestDataWindowService.mark_completed(request)

    @classmethod
    def get_resumable(cls, request) -> dict:
        """Retourne les tâches encore actives pour reprise UI."""
        from intelligence.services.celery_health_service import celery_workers_online

        workers_ok, _ = celery_workers_online(timeout=1.0)
        return {
            'test': cls._resolve_session_task(request, test_mode=True, workers_ok=workers_ok),
            'prod': cls._resolve_session_task(request, test_mode=False, workers_ok=workers_ok),
        }

    @classmethod
    def pending_age_seconds(cls, request, task_id: str) -> float | None:
        """Âge en secondes depuis la mise en file (session), ou None."""
        for test_mode in (True, False):
            payload = request.session.get(cls._key(test_mode)) or {}
            if payload.get('task_id') != str(task_id):
                continue
            return cls._age_seconds(payload.get('queued_at'))
        return None

    @classmethod
    def is_pending_stale(cls, request, task_id: str, *, state: str | None = None) -> bool:
        """True si PENDING trop longtemps sans démarrage worker."""
        result_state = state or AsyncResult(task_id).state
        if result_state != 'PENDING':
            return False
        age = cls.pending_age_seconds(request, task_id)
        if age is None:
            # Pas de queued_at (ancienne session) → considérer stale
            return True
        return age >= cls.PENDING_STALE_SECONDS

    @classmethod
    def liberate_task(cls, request, task_id: str) -> None:
        """Révoque une tâche orpheline et nettoie la session."""
        result = AsyncResult(task_id)
        try:
            result.revoke(terminate=False)
        except Exception:
            pass
        try:
            result.forget()
        except Exception:
            pass
        cls.clear_if_matches(request, task_id)

    @classmethod
    def _resolve_session_task(cls, request, *, test_mode: bool, workers_ok: bool = True) -> dict | None:
        payload = request.session.get(cls._key(test_mode))
        if not payload:
            return None

        task_id = payload.get('task_id')
        if not task_id:
            cls.clear_task(request, test_mode=test_mode)
            return None

        result = AsyncResult(task_id)

        # PENDING + worker down → libérer immédiatement (évite UI bloquée)
        if result.state == 'PENDING' and not workers_ok:
            cls.liberate_task(request, task_id)
            if test_mode:
                TestDataWindowService.mark_completed(request)
            return None

        if result.state == 'PENDING' and cls.is_pending_stale(request, task_id, state='PENDING'):
            cls.liberate_task(request, task_id)
            if test_mode:
                TestDataWindowService.mark_completed(request)
            return None

        if result.state in _RUNNING_STATES:
            return {
                'task_id': task_id,
                'test_mode': test_mode,
                'job': payload.get('job', ''),
                'etat': result.state,
            }

        cls.clear_task(request, test_mode=test_mode)
        if test_mode:
            TestDataWindowService.mark_completed(request)
        return None

    @staticmethod
    def _age_seconds(queued_at: str | None) -> float | None:
        if not queued_at:
            return None
        try:
            queued = datetime.fromisoformat(queued_at)
        except ValueError:
            return None
        if queued.tzinfo is None:
            queued = queued.replace(tzinfo=dt_timezone.utc)
        return (datetime.now(dt_timezone.utc) - queued).total_seconds()
