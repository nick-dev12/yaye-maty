"""
Gestion des sessions Playwright (cookies / storage_state).

Connexion manuelle une seule fois, puis réutilisation sur le VPS.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings

from intelligence.scrapers.constants import (
    PLATFORM_FACEBOOK,
    PLATFORM_TIKTOK,
    SESSION_FILENAME_TEMPLATE,
    SUPPORTED_PLATFORMS,
    get_sessions_dir,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Charge et sauvegarde les fichiers de session par plateforme."""

    def __init__(self, sessions_dir: Path | None = None):
        base_dir = Path(settings.BASE_DIR)
        self.sessions_dir = sessions_dir or get_sessions_dir(base_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def get_session_path(self, platform: str) -> Path:
        self._validate_platform(platform)
        return self.sessions_dir / SESSION_FILENAME_TEMPLATE.format(platform=platform)

    def session_exists(self, platform: str) -> bool:
        path = self.get_session_path(platform)
        return path.is_file() and path.stat().st_size > 0

    def load_storage_state(self, platform: str) -> str | None:
        """Retourne le chemin du fichier session s'il existe."""
        path = self.get_session_path(platform)
        if not path.is_file():
            return None

        try:
            json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning('Session invalide pour %s : %s', platform, exc)
            return None

        return str(path)

    def save_storage_state(self, context, platform: str) -> Path:
        """Persiste l'état de session (cookies) après navigation."""
        self._validate_platform(platform)
        path = self.get_session_path(platform)
        context.storage_state(path=str(path))
        logger.info('Session sauvegardée : %s', path)
        return path

    @staticmethod
    def _validate_platform(platform: str) -> None:
        if platform not in SUPPORTED_PLATFORMS:
            supported = ', '.join(SUPPORTED_PLATFORMS)
            raise ValueError(
                f'Plateforme « {platform} » non supportée. Valeurs : {supported}.'
            )

    @staticmethod
    def platform_label(platform: str) -> str:
        labels = {
            PLATFORM_FACEBOOK: 'Facebook',
            PLATFORM_TIKTOK: 'TikTok',
        }
        return labels.get(platform, platform)
