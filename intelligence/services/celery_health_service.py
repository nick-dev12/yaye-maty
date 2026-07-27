"""Santé Celery — détection worker actif avant mise en file."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

_WORKER_CMD_RE = re.compile(
    r'celery.*(?:\s|^)-A\s+\S+.*\bworker\b|\bcelery\b.*\bworker\b',
    re.IGNORECASE,
)


def celery_workers_online(*, timeout: float = 1.5) -> tuple[bool, str]:
    """
    Vérifie qu'au moins un worker Celery tourne.

    Sur Windows (pool solo), ``inspect.ping()`` échoue tant qu'une longue
    tâche occupe le worker — on bascule alors sur la détection de processus.
    """
    ping_ok, ping_msg = _ping_workers(timeout=timeout)
    if ping_ok:
        return True, ping_msg

    proc_ok, proc_msg = _detect_worker_process()
    if proc_ok:
        return True, proc_msg

    return False, ping_msg


def purge_celery_queue() -> int:
    """Vide la file d'attente Celery (tâches PENDING orphelines)."""
    try:
        from yayematy_project.celery import app

        with app.connection_or_acquire() as conn:
            return int(app.control.purge() or 0)
    except Exception:
        logger.exception('Purge file Celery échouée')
        return 0


def clear_stale_unacked() -> int:
    """
    Supprime les messages ``unacked`` Redis laissés par un worker crashé.

    Sans cela, un worker solo peut rester bloqué / ne plus répondre au ping.
    """
    try:
        import redis
        from django.conf import settings as dj_settings

        url = getattr(dj_settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
        client = redis.Redis.from_url(url)
        removed = int(client.delete('unacked', 'unacked_index') or 0)
        return removed
    except Exception:
        logger.exception('Nettoyage unacked Celery échoué')
        return 0


def _ping_workers(*, timeout: float) -> tuple[bool, str]:
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


def _detect_worker_process() -> tuple[bool, str]:
    """True si un processus ``celery … worker`` est vivant (même occupé)."""
    ui_pid = _ui_managed_worker_pid()
    if ui_pid and _pid_alive(ui_pid):
        cmdline = _process_cmdline(ui_pid)
        if not cmdline or _WORKER_CMD_RE.search(cmdline):
            return True, (
                f'Worker actif (PID {ui_pid}, occupé — pool solo, ping indisponible).'
            )

    for pid, cmdline in _iter_python_processes():
        if _WORKER_CMD_RE.search(cmdline or ''):
            return True, (
                f'Worker actif (PID {pid}, occupé — pool solo, ping indisponible).'
            )
    return False, ''


def _ui_managed_worker_pid() -> int | None:
    import json

    path = Path(settings.BASE_DIR) / '.celery_ui' / 'processes.json'
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        pid = (data.get('worker') or {}).get('pid')
        return int(pid) if pid else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == 'win32':
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
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


def _process_cmdline(pid: int) -> str:
    if sys.platform == 'win32':
        try:
            completed = subprocess.run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    f'(Get-CimInstance Win32_Process -Filter "ProcessId={int(pid)}").CommandLine',
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            return (completed.stdout or '').strip()
        except (OSError, subprocess.TimeoutExpired):
            return ''
    try:
        return Path(f'/proc/{int(pid)}/cmdline').read_bytes().replace(b'\x00', b' ').decode(
            'utf-8', errors='ignore'
        )
    except OSError:
        return ''


def _iter_python_processes() -> list[tuple[int, str]]:
    """Liste (pid, cmdline) des processus Python — Windows via CIM."""
    if sys.platform != 'win32':
        return _iter_python_processes_unix()

    try:
        completed = subprocess.run(
            [
                'powershell',
                '-NoProfile',
                '-Command',
                (
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" "
                    '| Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'
                ),
            ],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    raw = (completed.stdout or '').strip()
    if not raw:
        return []

    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]
    out: list[tuple[int, str]] = []
    for row in data or []:
        try:
            pid = int(row.get('ProcessId') or 0)
        except (TypeError, ValueError):
            continue
        if not pid:
            continue
        out.append((pid, str(row.get('CommandLine') or '')))
    return out


def _iter_python_processes_unix() -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    proc = Path('/proc')
    if not proc.exists():
        return out
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / 'cmdline').read_bytes().replace(b'\x00', b' ').decode(
                'utf-8', errors='ignore'
            )
        except OSError:
            continue
        if 'python' in cmdline.lower():
            out.append((int(entry.name), cmdline))
    return out
