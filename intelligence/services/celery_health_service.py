"""Santé Celery — détection worker actif avant mise en file."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def celery_workers_online(*, timeout: float = 1.5) -> tuple[bool, str]:
    """
    Vérifie qu'au moins un worker répond au ping.

    Returns:
        (ok, message)
    """
    try:
        from yayematy_project.celery import app

        inspector = app.control.inspect(timeout=timeout)
        if inspector is None:
            return False, 'Inspecteur Celery indisponible.'
        pong = inspector.ping() or {}
        if not pong:
            return False, (
                'Aucun worker Celery actif. Lancez : '
                '.\\scripts\\run_celery_worker.ps1'
            )
        names = ', '.join(pong.keys())
        return True, f'Worker(s) : {names}'
    except Exception as exc:
        logger.warning('Ping Celery échoué : %s', exc)
        return False, (
            f'Impossible de joindre Celery/Redis ({exc}). '
            'Vérifiez Redis (Memurai) et le worker.'
        )


def purge_celery_queue() -> int:
    """Vide la file d'attente Celery (tâches PENDING orphelines)."""
    try:
        from yayematy_project.celery import app

        with app.connection_or_acquire() as conn:
            return int(app.control.purge() or 0)
    except Exception:
        logger.exception('Purge file Celery échouée')
        return 0
