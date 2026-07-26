"""
Extraction des identifiants uniques de publications (TikTok / Facebook).
"""

from __future__ import annotations

import hashlib
import re

from intelligence.scrapers.constants import PLATFORM_FACEBOOK, PLATFORM_TIKTOK


def extract_post_id(platform: str, url: str) -> str:
    """
    Extrait l'ID plateforme depuis l'URL.

    TikTok : https://www.tiktok.com/@user/video/7123456789012345678
    Facebook : https://www.facebook.com/.../posts/123456789
    """
    if not url:
        return ''

    if platform == PLATFORM_TIKTOK:
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)

    if platform == PLATFORM_FACEBOOK:
        for pattern in (
            r'/posts/(\d+)',
            r'[?&]fbid=(\d+)',
            r'/videos/(\d+)',
            r'/permalink/(\d+)',
        ):
            match = re.search(pattern, url)
            if match:
                return match.group(1)

    return ''


def build_comment_id(platform: str, post_id: str, text: str, index: int = 0) -> str:
    """Génère un ID stable pour un commentaire sans identifiant DOM."""
    raw = f'{platform}:{post_id}:{index}:{text[:120]}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]
