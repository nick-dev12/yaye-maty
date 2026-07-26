"""
Contexte d'exécution collecte — production vs session test (contextvar).
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionRunContext:
    """Indique si la collecte en cours écrit dans les tables test."""

    test_mode: bool = False

    @classmethod
    def production(cls) -> CollectionRunContext:
        return cls(test_mode=False)

    @classmethod
    def test(cls) -> CollectionRunContext:
        return cls(test_mode=True)

    @property
    def is_test(self) -> bool:
        return self.test_mode


_default_ctx = CollectionRunContext.production()
_collection_ctx: ContextVar[CollectionRunContext] = ContextVar(
    'collection_run_ctx',
    default=_default_ctx,
)


def get_collection_context() -> CollectionRunContext:
    return _collection_ctx.get()


def set_collection_context(ctx: CollectionRunContext) -> Token:
    return _collection_ctx.set(ctx)


def reset_collection_context(token: Token) -> None:
    _collection_ctx.reset(token)
