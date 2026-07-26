"""
Client HTTP vers l'API Intelligence du VPS.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from local_nlp.config import ClientConfig

logger = logging.getLogger(__name__)


class IntelligenceApiClient:
    """Échange données brutes ↔ analyses NLP avec le VPS."""

    def __init__(self, config: ClientConfig | None = None):
        self.config = config or ClientConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update(self.config.headers)

    def fetch_raw_posts(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Récupère les publications en attente d'analyse."""
        params = {}
        if limit is not None:
            params['limit'] = limit

        url = self.config.endpoint('raw-data/')
        response = self.session.get(
            url,
            params=params,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        posts = payload.get('posts', [])
        logger.info('%s publication(s) reçue(s) du VPS.', len(posts))
        return posts

    def submit_analysis(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Envoie les résultats NLP analysés localement."""
        if not results:
            return {'success': True, 'stats': {'updated': 0}}

        url = self.config.endpoint('analyzed-data/')
        response = self.session.post(
            url,
            json={'results': results},
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        logger.info('Analyses envoyées : %s', payload.get('stats', {}))
        return payload

    def health_check(self) -> bool:
        """Vérifie que l'API répond (via social-posts)."""
        url = self.config.endpoint('social-posts/')
        response = self.session.get(url, params={'limit': 1}, timeout=10)
        return response.status_code == 200
