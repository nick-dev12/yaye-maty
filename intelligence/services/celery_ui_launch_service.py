"""
Lancement Celery worker / beat depuis l'interface — développement local uniquement.

Sur le VPS de production, ces processus doivent rester gérés par systemd ou Supervisor.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from intelligence.services.celery_health_service import (
    celery_workers_online,
    clear_stale_unacked,
    purge_celery_queue,
)

logger = logging.getLogger(__name__)

STATE_DIR_NAME = '.celery_ui'
STATE_FILE_NAME = 'processes.json'
WORKER_READY_WAIT_SECONDS = 20.0


class CeleryUiLaunchError(Exception):
    """Erreur métier lors du démarrage/arrêt UI."""


class CeleryUiLaunchService:
    """Démarre worker et beat Celery via subprocess (Windows / dev local)."""

    COMPONENT_WORKER = 'worker'
    COMPONENT_BEAT = 'beat'
    VALID_COMPONENTS = {COMPONENT_WORKER, COMPONENT_BEAT}

    @classmethod
    def is_enabled(cls) -> bool:
        return bool(getattr(settings, 'CELERY_UI_LAUNCH', False))

    @classmethod
    def get_ui_context(cls) -> dict:
        if not cls.is_enabled():
            return {'celery_ui_enabled': False}
        return {
            'celery_ui_enabled': True,
            'celery_ui_status': cls.get_status(),
        }

    @classmethod
    def get_status(cls) -> dict:
        worker_online, worker_message = celery_workers_online(timeout=1.2)
        state = cls._load_state()
        worker_pid = state.get(cls.COMPONENT_WORKER, {}).get('pid')
        beat_pid = state.get(cls.COMPONENT_BEAT, {}).get('pid')
        beat_online = cls._pid_alive(beat_pid) if beat_pid else False

        if worker_online and not cls._pid_alive(worker_pid):
            worker_pid = None

        if beat_pid and not beat_online:
            cls._clear_component(cls.COMPONENT_BEAT)
            beat_pid = None

        return {
            'enabled': True,
            'platform': sys.platform,
            'worker_online': worker_online,
            'worker_message': worker_message,
            'worker_pid': worker_pid,
            'beat_online': beat_online,
            'beat_pid': beat_pid,
            'pool': getattr(settings, 'CELERY_WORKER_POOL', 'solo'),
            'concurrency': getattr(settings, 'CELERY_WORKER_CONCURRENCY', 1),
            'ui_managed': bool(worker_pid or beat_pid),
        }

    @classmethod
    def start(cls, component: str) -> dict:
        cls._ensure_enabled()
        if component not in cls.VALID_COMPONENTS:
            raise CeleryUiLaunchError('Composant Celery invalide.')

        if component == cls.COMPONENT_WORKER:
            online, message = celery_workers_online(timeout=1.0)
            if online:
                return {
                    'ok': True,
                    'already_running': True,
                    'message': message,
                    'status': cls.get_status(),
                }
            # Tâches Beat orphelines / unacked bloquent le pool solo au démarrage.
            purged = purge_celery_queue()
            clear_stale_unacked()
            result = cls._start_process(
                component=component,
                args=cls._worker_command(),
                label='Worker Celery',
                wait_worker_ready=True,
            )
            if purged:
                result['message'] = (
                    f'{result.get("message", "")} '
                    f'File Redis nettoyée ({purged} tâche(s) orpheline(s)).'
                ).strip()
            return result

        state = cls._load_state()
        beat_pid = state.get(cls.COMPONENT_BEAT, {}).get('pid')
        if cls._pid_alive(beat_pid):
            return {
                'ok': True,
                'already_running': True,
                'message': f'Celery Beat déjà actif (PID {beat_pid}).',
                'status': cls.get_status(),
            }

        return cls._start_process(
            component=component,
            args=cls._beat_command(),
            label='Celery Beat',
        )

    @classmethod
    def stop(cls, component: str) -> dict:
        cls._ensure_enabled()
        if component not in cls.VALID_COMPONENTS:
            raise CeleryUiLaunchError('Composant Celery invalide.')

        state = cls._load_state()
        entry = state.get(component) or {}
        pid = entry.get('pid')
        if not pid or not cls._pid_alive(pid):
            cls._clear_component(component)
            return {
                'ok': True,
                'stopped': False,
                'message': (
                    'Aucun processus lancé depuis l’interface pour ce composant. '
                    'Fermez la fenêtre terminal manuelle si besoin (Ctrl+C).'
                ),
                'status': cls.get_status(),
            }

        cls._terminate_pid(pid)
        cls._clear_component(component)
        label = 'Worker' if component == cls.COMPONENT_WORKER else 'Beat'
        return {
            'ok': True,
            'stopped': True,
            'message': f'{label} Celery arrêté (PID {pid}).',
            'status': cls.get_status(),
        }

    @classmethod
    def _start_process(
        cls,
        *,
        component: str,
        args: list[str],
        label: str,
        wait_worker_ready: bool = False,
    ) -> dict:
        cls._ensure_redis()
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NEW_CONSOLE

        try:
            process = subprocess.Popen(
                args,
                cwd=str(settings.BASE_DIR),
                creationflags=creationflags,
            )
        except OSError as exc:
            logger.exception('Échec lancement %s : %s', label, exc)
            raise CeleryUiLaunchError(f'Impossible de lancer {label} : {exc}') from exc

        cls._save_component(component, process.pid)

        ready_note = ''
        if wait_worker_ready and component == cls.COMPONENT_WORKER:
            ready, ready_msg = cls._wait_until_worker_ready(process.pid)
            if not ready:
                if not cls._pid_alive(process.pid):
                    cls._clear_component(component)
                    raise CeleryUiLaunchError(
                        'Le worker a démarré puis s’est arrêté immédiatement. '
                        'Vérifiez la fenêtre terminal Celery (erreur Python / Redis).'
                    )
                ready_note = (
                    f' Processus vivant (PID {process.pid}) mais pas encore joignable '
                    f'au ping — {ready_msg}'
                )
            else:
                ready_note = f' {ready_msg}'

        return {
            'ok': True,
            'already_running': False,
            'message': (
                f'{label} démarré — une fenêtre terminal s’ouvre (PID {process.pid}). '
                'Laissez-la ouverte pendant vos collectes.'
                f'{ready_note}'
            ),
            'pid': process.pid,
            'status': cls.get_status(),
        }

    @classmethod
    def _wait_until_worker_ready(cls, pid: int) -> tuple[bool, str]:
        import time

        deadline = time.monotonic() + WORKER_READY_WAIT_SECONDS
        last_msg = 'en attente…'
        while time.monotonic() < deadline:
            if not cls._pid_alive(pid):
                return False, 'processus terminé'
            online, message = celery_workers_online(timeout=0.8)
            last_msg = message
            if online:
                return True, message
            time.sleep(0.7)
        return False, last_msg

    @classmethod
    def _worker_command(cls) -> list[str]:
        python = cls._python_executable()
        pool = getattr(settings, 'CELERY_WORKER_POOL', 'solo')
        concurrency = getattr(settings, 'CELERY_WORKER_CONCURRENCY', 1)
        return [
            python,
            '-m',
            'celery',
            '-A',
            'yayematy_project',
            'worker',
            '-l',
            'info',
            '-P',
            pool,
            '--concurrency',
            str(concurrency),
        ]

    @classmethod
    def _beat_command(cls) -> list[str]:
        python = cls._python_executable()
        return [
            python,
            '-m',
            'celery',
            '-A',
            'yayematy_project',
            'beat',
            '-l',
            'info',
        ]

    @classmethod
    def _python_executable(cls) -> str:
        venv_python = Path(settings.BASE_DIR) / 'venv' / 'Scripts' / 'python.exe'
        if venv_python.exists():
            return str(venv_python)
        venv_python_unix = Path(settings.BASE_DIR) / 'venv' / 'bin' / 'python'
        if venv_python_unix.exists():
            return str(venv_python_unix)
        return sys.executable

    @classmethod
    def _ensure_enabled(cls) -> None:
        if not cls.is_enabled():
            raise CeleryUiLaunchError(
                'Le lancement Celery depuis l’interface est désactivé sur cet environnement.'
            )

    @classmethod
    def _ensure_redis(cls) -> None:
        try:
            from yayematy_project.celery import app

            conn = app.connection()
            conn.ensure_connection(max_retries=1)
            conn.release()
        except Exception as exc:
            raise CeleryUiLaunchError(
                f'Redis / broker Celery injoignable ({exc}). '
                'Démarrez Memurai ou Redis avant le worker.'
            ) from exc

    @classmethod
    def _state_path(cls) -> Path:
        path = Path(settings.BASE_DIR) / STATE_DIR_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path / STATE_FILE_NAME

    @classmethod
    def _load_state(cls) -> dict:
        path = cls._state_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return {}

    @classmethod
    def _save_state(cls, state: dict) -> None:
        path = cls._state_path()
        path.write_text(json.dumps(state, indent=2), encoding='utf-8')

    @classmethod
    def _save_component(cls, component: str, pid: int) -> None:
        state = cls._load_state()
        state[component] = {
            'pid': pid,
            'started_at': datetime.now(timezone.utc).isoformat(),
        }
        cls._save_state(state)

    @classmethod
    def _clear_component(cls, component: str) -> None:
        state = cls._load_state()
        state.pop(component, None)
        cls._save_state(state)

    @classmethod
    def _pid_alive(cls, pid: int | None) -> bool:
        if not pid:
            return False
        if sys.platform == 'win32':
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False

        try:
            import os

            os.kill(int(pid), 0)
            return True
        except OSError:
            return False

    @classmethod
    def _terminate_pid(cls, pid: int) -> None:
        if sys.platform == 'win32':
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/T', '/F'],
                check=False,
                capture_output=True,
            )
            return

        import os
        import signal

        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
