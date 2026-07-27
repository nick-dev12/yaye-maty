"""
Pont ORM Django ↔ Playwright sync.

Playwright (greenlet) marque le thread comme « async » : les requêtes ORM
directes lèvent SynchronousOnlyOperation. Exécuter l'ORM dans un worker thread
avec propagation du ContextVar de collecte (prod/test).
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import TypeVar

from django.db import close_old_connections

T = TypeVar('T')


def run_orm_safe(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """Exécute une opération Django ORM hors du contexte async Playwright."""
    ctx = copy_context()

    def _worker() -> T:
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(ctx.run, _worker).result()
