"""
Arrêt coopératif global des collectes (test et production).

Les scrapers passent beaucoup de temps dans des pauses anti-bot. Sans point de
contrôle, un « Arrêter » demandé depuis le tableau de bord n'était honoré qu'à
la fin de l'étape en cours (jusqu'à plusieurs minutes).

Ce module expose un *hook* d'annulation installé par la tâche Celery, consulté
par ``random_sleep`` et les temporisations des scrapers.

``CollectionAborted`` hérite volontairement de ``BaseException`` : les scrapers
contiennent de nombreux ``except Exception`` défensifs qui, sinon, avaleraient
la demande d'arrêt et relanceraient l'étape suivante.
"""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from typing import Callable

ShouldCancel = Callable[[], bool]

CANCEL_POLL_SECONDS = 0.4

HOOK_CACHE_SECONDS = 0.75

_abort_hook: ContextVar[ShouldCancel | None] = ContextVar('collection_abort_hook', default=None)

# Repli process-wide : les scrapers Playwright/Jumia exécutent une partie du
# travail dans des threads secondaires qui n'héritent pas toujours du contexte.
# Le worker tourne en pool=solo (une collecte à la fois), ce repli est donc sûr.
_fallback_hook: ShouldCancel | None = None

# Le hook interroge Redis : on mémorise brièvement le résultat négatif pour ne
# pas le solliciter à chaque tranche de pause.
_last_check_at: float = 0.0


class CollectionAborted(BaseException):
    """Arrêt demandé par l'utilisateur — les données déjà collectées sont conservées."""

    def __init__(self, message: str = 'Collecte interrompue par l’utilisateur.'):
        super().__init__(message)


def set_abort_hook(should_cancel: ShouldCancel | None) -> Token:
    """Installe le hook d'annulation pour la durée d'une collecte."""
    global _fallback_hook, _last_check_at
    _fallback_hook = should_cancel
    _last_check_at = 0.0
    return _abort_hook.set(should_cancel)


def reset_abort_hook(token: Token) -> None:
    """Retire le hook installé par :func:`set_abort_hook`."""
    global _fallback_hook, _last_check_at
    _fallback_hook = None
    _last_check_at = 0.0
    _abort_hook.reset(token)


def abort_requested(*, force: bool = False) -> bool:
    """
    Indique si un arrêt a été demandé (sans lever d'exception).

    Args:
        force: Ignore le cache anti-rafale et interroge Redis immédiatement.
    """
    global _last_check_at

    hook = _abort_hook.get() or _fallback_hook
    if hook is None:
        return False

    now = time.monotonic()
    if not force and (now - _last_check_at) < HOOK_CACHE_SECONDS:
        return False

    _last_check_at = now
    try:
        return bool(hook())
    except Exception:
        # Un incident Redis ne doit jamais interrompre une collecte en cours.
        return False


def check_abort(*, force: bool = False) -> None:
    """Lève :class:`CollectionAborted` si un arrêt a été demandé."""
    if abort_requested(force=force):
        raise CollectionAborted()


def interruptible_sleep(seconds: float) -> None:
    """
    Pause découpée en tranches courtes, annulable en moins d'une seconde.

    Raises:
        CollectionAborted: Si un arrêt est demandé pendant la pause.
    """
    remaining = max(0.0, float(seconds))
    check_abort(force=True)
    while remaining > 0:
        step = min(CANCEL_POLL_SECONDS, remaining)
        time.sleep(step)
        remaining -= step
        check_abort()
