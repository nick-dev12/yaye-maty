"""
Configuration du client NLP local.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

LOCAL_NLP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = LOCAL_NLP_DIR.parent

# Charge .env racine puis local_nlp/.env (prioritaire)
load_dotenv(PROJECT_ROOT / '.env')
load_dotenv(LOCAL_NLP_DIR / '.env', override=True)


@dataclass(frozen=True)
class ClientConfig:
    """Paramètres de connexion au VPS."""

    base_url: str
    api_key: str
    batch_limit: int = 50
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> 'ClientConfig':
        base_url = os.getenv('YAYEMATY_API_URL', 'http://127.0.0.1:8000').rstrip('/')
        api_key = os.getenv('INTELLIGENCE_API_KEY', '').strip()

        if not api_key:
            raise ValueError(
                'INTELLIGENCE_API_KEY manquante. '
                'Définissez-la dans local_nlp/.env ou .env à la racine.'
            )

        try:
            batch_limit = min(int(os.getenv('NLP_BATCH_LIMIT', '50')), 200)
        except ValueError:
            batch_limit = 50

        try:
            timeout = int(os.getenv('NLP_TIMEOUT_SECONDS', '30'))
        except ValueError:
            timeout = 30

        return cls(
            base_url=base_url,
            api_key=api_key,
            batch_limit=batch_limit,
            timeout_seconds=timeout,
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            'X-API-Key': self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def endpoint(self, path: str) -> str:
        return f'{self.base_url}/intelligence/api/{path.lstrip("/")}'
