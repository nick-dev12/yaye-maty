"""
Contrôleur du scraping réseaux sociaux.
"""

from intelligence.scrapers.social_scraper import ScrapeResult, SocialScraper
from intelligence.services.social_extraction_service import (
    ExtractionRunResult,
    SocialExtractionService,
)


class SocialScraperController:
    """Orchestre l'initialisation de session et les extractions."""

    def __init__(self):
        self.scraper = SocialScraper()
        self.extraction_service = SocialExtractionService(self.scraper)

    def init_session(self, platform: str, *, url: str | None = None, wait_seconds: int = 120) -> str:
        return self.scraper.init_session_interactive(
            platform,
            url=url,
            wait_seconds=wait_seconds,
        )

    def scrape(self, platform: str, url: str, *, headless: bool | None = None) -> ScrapeResult:
        return self.scraper.scrape_target(platform, url, headless=headless)

    def extract_target(self, target_id: int, *, headless: bool | None = None, max_posts: int | None = None) -> ExtractionRunResult:
        from intelligence.models import SocialScrapeTarget

        target = SocialScrapeTarget.objects.get(pk=target_id, is_active=True)
        return self.extraction_service.run_target(target, headless=headless, max_posts=max_posts)

    def extract_all_active(self, *, headless: bool | None = None) -> list[ExtractionRunResult]:
        return self.extraction_service.run_active_targets(headless=headless)

    def session_exists(self, platform: str) -> bool:
        return self.scraper.session_manager.session_exists(platform)
