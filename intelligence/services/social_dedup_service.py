"""
Anti-doublon — évite de revisiter des publications déjà en base (prod ou test).
"""

from __future__ import annotations

from intelligence.scrapers.constants import PLATFORM_FACEBOOK, PLATFORM_TIKTOK
from intelligence.scrapers.post_id_utils import extract_post_id
from intelligence.services.collection_model_router import CollectionModelRouter


class SocialDedupService:
    """Filtre URLs et publications déjà collectées."""

    @classmethod
    def is_known_url(cls, platform: str, url: str) -> bool:
        router = CollectionModelRouter()
        post_id = extract_post_id(platform, url)
        if post_id:
            return router.posts_qs().filter(
                platform=platform,
                platform_post_id=post_id,
            ).exists()
        return False

    @classmethod
    def filter_new_urls(cls, platform: str, urls: list[str]) -> list[str]:
        """Conserve uniquement les URLs dont la publication n'est pas déjà en base."""
        known_ids = cls.known_ids_for_platform(platform)
        return cls.filter_urls_with_known_ids(platform, urls, known_ids)

    @classmethod
    def filter_urls_with_known_ids(
        cls,
        platform: str,
        urls: list[str],
        known_ids: set[str],
    ) -> list[str]:
        """Filtre en mémoire — utilisable pendant Playwright (sans requête ORM)."""
        fresh: list[str] = []
        seen: set[str] = set()

        for url in urls:
            if url in seen:
                continue
            seen.add(url)

            post_id = extract_post_id(platform, url)
            if post_id and post_id in known_ids:
                continue

            fresh.append(url)

        return fresh

    @classmethod
    def is_url_in_known_ids(cls, platform: str, url: str, known_ids: set[str]) -> bool:
        post_id = extract_post_id(platform, url)
        return bool(post_id and post_id in known_ids)

    @classmethod
    def known_ids_for_platform(cls, platform: str) -> set[str]:
        """Ensemble des IDs plateforme déjà stockés (usage scroll long)."""
        router = CollectionModelRouter()
        return set(
            router.posts_qs().filter(platform=platform)
            .exclude(platform_post_id='')
            .values_list('platform_post_id', flat=True)
        )

    @classmethod
    def skip_post_id(cls, platform: str, post_id: str) -> bool:
        if not post_id:
            return False
        return cls._is_known_id(platform, post_id)

    @classmethod
    def _is_known_id(cls, platform: str, post_id: str) -> bool:
        router = CollectionModelRouter()
        return router.posts_qs().filter(
            platform=platform,
            platform_post_id=post_id,
        ).exists()

    @classmethod
    def platform_from_url(cls, url: str) -> str:
        if 'tiktok.com' in url:
            return PLATFORM_TIKTOK
        if 'facebook.com' in url:
            return PLATFORM_FACEBOOK
        return ''
