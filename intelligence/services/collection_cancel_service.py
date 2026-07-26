"""Signalement d'arrêt coopératif pour les collectes manuelles Celery."""

from __future__ import annotations

import redis
from django.conf import settings

_CANCEL_PREFIX = 'collecte_cancel:'
_TTL_SECONDS = 3600

# Client réutilisé : le flag est interrogé plusieurs fois par seconde pendant
# les pauses anti-bot, une nouvelle connexion à chaque appel épuiserait les sockets.
_client_cache: redis.Redis | None = None


class CollectionCancelService:
    """Flag d'annulation partagé interface Django ↔ worker Celery (Redis)."""

    @classmethod
    def _client(cls) -> redis.Redis:
        global _client_cache
        if _client_cache is None:
            _client_cache = redis.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
            )
        return _client_cache

    @classmethod
    def request_cancel(cls, task_id: str) -> None:
        cls._client().setex(f'{_CANCEL_PREFIX}{task_id}', _TTL_SECONDS, '1')

    @classmethod
    def is_cancelled(cls, task_id: str) -> bool:
        return cls._client().exists(f'{_CANCEL_PREFIX}{task_id}') == 1

    @classmethod
    def clear(cls, task_id: str) -> None:
        cls._client().delete(f'{_CANCEL_PREFIX}{task_id}')
