"""
Orchestration extraction + persistance des réseaux sociaux.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from intelligence.models import MarketSearchKeyword, SocialScrapeTarget
from intelligence.scrapers.extractors import get_extractor
from intelligence.scrapers.human_behavior import (
    organic_scroll,
    random_sleep,
    subtle_mouse_movement,
)
from intelligence.scrapers.social_scraper import SocialScraper
from intelligence.scrapers.tiktok_scrape_schema import clamp_max_comments, MIN_COMMENTS_PER_VIDEO
from intelligence.services.django_orm_safe import run_orm_safe
from intelligence.services.social_post_service import SocialPostService

logger = logging.getLogger(__name__)


@dataclass
class ExtractionRunResult:
    """Résultat d'un scrape + extraction sur une cible."""

    target_id: int
    platform: str
    url: str
    label: str
    success: bool
    message: str
    extracted: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class SocialExtractionService:
    """Scrape une cible, extrait le DOM et persiste en base."""

    def __init__(self, scraper: SocialScraper | None = None):
        self.scraper = scraper or SocialScraper()

    def run_target(
        self,
        target: SocialScrapeTarget,
        *,
        headless: bool | None = None,
        max_posts: int | None = None,
        skip_existing: bool = False,
    ) -> ExtractionRunResult:
        """Scrape et extrait les publications d'une cible configurée."""
        effective_max_posts = max_posts or target.max_posts
        bundle = self.scraper.browser_factory.open(target.platform, headless=headless)
        extracted = []

        try:
            page = bundle.page
            logger.info('Extraction %s — %s (max %s posts)', target.platform, target.url, effective_max_posts)
            page.goto(target.url, wait_until='domcontentloaded', timeout=60_000)
            random_sleep(3.0, 6.0)
            subtle_mouse_movement(page)
            organic_scroll(page, iterations=2)

            extractor = get_extractor(target.platform)
            extracted = extractor.extract(page, max_posts=effective_max_posts)
            logger.info('Phase liste — %s publication(s) sur %s', len(extracted), target.label)

            if (
                target.scrape_comments
                and target.platform == 'tiktok'
                and hasattr(extractor, 'enrich_with_comments')
            ):
                enrich_limit = min(effective_max_posts, len(extracted)) if target.scrape_comments else 0
                if enrich_limit:
                    logger.info('Phase commentaires — %s vidéo(s) à enrichir', enrich_limit)
                    extractor.enrich_with_comments(
                        page,
                        extracted,
                        max_posts=enrich_limit,
                        max_comments=clamp_max_comments(target.max_comments),
                    )

            self.scraper.session_manager.save_storage_state(bundle.context, target.platform)

        except Exception as exc:
            logger.exception('Échec extraction cible %s : %s', target.pk, exc)
            return ExtractionRunResult(
                target_id=target.pk,
                platform=target.platform,
                url=target.url,
                label=target.label,
                success=False,
                message=str(exc),
            )
        finally:
            bundle.close()

        def _persist_target_results() -> dict:
            stats = SocialPostService.save_extracted_posts(
                platform=target.platform,
                source_url=target.url,
                extracted=extracted,
                skip_if_exists=skip_existing,
            )
            SocialPostService.touch_target(target)
            return stats

        save_stats = run_orm_safe(_persist_target_results)

        return ExtractionRunResult(
            target_id=target.pk,
            platform=target.platform,
            url=target.url,
            label=target.label,
            success=True,
            message='Extraction terminée.',
            extracted=save_stats['total'],
            created=save_stats['created'],
            updated=save_stats['updated'],
            skipped=save_stats['skipped'],
        )

    def run_keyword_search(
        self,
        keyword: MarketSearchKeyword,
        *,
        headless: bool | None = None,
        max_posts: int | None = None,
        skip_existing: bool = False,
    ) -> ExtractionRunResult:
        """
        Scrape une page recherche dérivée du mot-clé Paramètres (ex. Facebook).

        Source unique : URL construite via ``keyword.build_search_url()``.
        """
        from django.utils import timezone

        from intelligence.services.collection_model_router import CollectionModelRouter

        url = keyword.build_search_url()
        platform = keyword.platform
        label = keyword.display_label
        effective_max_posts = max_posts or keyword.max_videos or 12
        bundle = self.scraper.browser_factory.open(platform, headless=headless)
        extracted = []

        try:
            page = bundle.page
            logger.info(
                'Recherche %s — %s (max %s posts)',
                platform,
                url,
                effective_max_posts,
            )
            page.goto(url, wait_until='domcontentloaded', timeout=60_000)
            random_sleep(3.0, 6.0)
            subtle_mouse_movement(page)
            organic_scroll(page, iterations=2)

            extractor = get_extractor(platform)
            extracted = extractor.extract(page, max_posts=effective_max_posts)

            if (
                platform == MarketSearchKeyword.Platform.TIKTOK
                and hasattr(extractor, 'enrich_with_comments')
            ):
                enrich_limit = min(effective_max_posts, len(extracted))
                if enrich_limit:
                    extractor.enrich_with_comments(
                        page,
                        extracted,
                        max_posts=enrich_limit,
                        max_comments=clamp_max_comments(keyword.max_comments),
                    )

            self.scraper.session_manager.save_storage_state(bundle.context, platform)

        except Exception as exc:
            logger.exception('Échec recherche mot-clé %s : %s', keyword.pk, exc)
            return ExtractionRunResult(
                target_id=keyword.pk,
                platform=platform,
                url=url,
                label=label,
                success=False,
                message=str(exc),
            )
        finally:
            bundle.close()

        def _persist_keyword_results() -> dict:
            stats = SocialPostService.save_extracted_posts(
                platform=platform,
                source_url=url,
                extracted=extracted,
                skip_if_exists=skip_existing,
            )
            if not CollectionModelRouter().is_test:
                keyword.last_scraped_at = timezone.now()
                keyword.save(update_fields=['last_scraped_at', 'updated_at'])
            return stats

        save_stats = run_orm_safe(_persist_keyword_results)

        return ExtractionRunResult(
            target_id=keyword.pk,
            platform=platform,
            url=url,
            label=label,
            success=True,
            message='Recherche mot-clé terminée.',
            extracted=save_stats['total'],
            created=save_stats['created'],
            updated=save_stats['updated'],
            skipped=save_stats['skipped'],
        )

    def run_active_keyword_searches(
        self,
        *,
        headless: bool | None = None,
        platform: str | None = None,
        limit: int = 0,
        max_posts: int | None = None,
    ) -> list[ExtractionRunResult]:
        """Recherche réseaux — uniquement mots-clés actifs Paramètres (hors TikTok Top-Down)."""
        from intelligence.services.active_keyword_service import ActiveKeywordService

        keywords = ActiveKeywordService.list_for_social(limit=limit)
        if platform:
            keywords = [kw for kw in keywords if kw.platform == platform]
        results: list[ExtractionRunResult] = []

        for keyword in keywords:
            if keyword.platform == MarketSearchKeyword.Platform.TIKTOK:
                continue
            results.append(
                self.run_keyword_search(
                    keyword,
                    headless=headless,
                    max_posts=max_posts,
                    skip_existing=True,
                )
            )
            random_sleep(4.0, 8.0)

        return results

    def run_active_targets(
        self,
        *,
        headless: bool | None = None,
        platform: str | None = None,
    ) -> list[ExtractionRunResult]:
        """Legacy — délègue aux mots-clés actifs Paramètres."""
        return self.run_active_keyword_searches(headless=headless, platform=platform)

    @staticmethod
    def get_active_targets():
        from intelligence.services.active_keyword_service import ActiveKeywordService

        return ActiveKeywordService.list_for_social()
