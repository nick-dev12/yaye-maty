"""
Factory Playwright « fantôme » : Stealth + contexte réaliste.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from playwright.sync_api import Browser, BrowserContext, Page, Playwright
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from intelligence.scrapers.constants import (
    CHROMIUM_LAUNCH_ARGS,
    DEFAULT_LOCALE,
    DEFAULT_TIMEZONE,
    DEFAULT_USER_AGENT,
    DEFAULT_VIEWPORT,
)
from intelligence.scrapers.session_manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class StealthBrowserBundle:
    """Ressources Playwright ouvertes pour une session de scraping."""

    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    stealth_cm: object

    def close(self) -> None:
        try:
            self.browser.close()
        finally:
            self.stealth_cm.__exit__(None, None, None)


class StealthBrowserFactory:
    """Crée un navigateur Chromium indétectable."""

    def __init__(self, session_manager: SessionManager | None = None):
        self.session_manager = session_manager or SessionManager()
        scraper_settings = getattr(settings, 'SOCIAL_SCRAPER', {})
        self.headless = scraper_settings.get('HEADLESS', False)
        self.viewport = scraper_settings.get('VIEWPORT', DEFAULT_VIEWPORT)
        self.user_agent = scraper_settings.get('USER_AGENT', DEFAULT_USER_AGENT)
        self.locale = scraper_settings.get('LOCALE', DEFAULT_LOCALE)
        self.timezone = scraper_settings.get('TIMEZONE', DEFAULT_TIMEZONE)
        self.proxy_server = scraper_settings.get('PROXY_SERVER', '')

    def open(
        self,
        platform: str,
        *,
        headless: bool | None = None,
        storage_state: str | None = None,
    ) -> StealthBrowserBundle:
        """
        Ouvre un navigateur stealth.

        Si storage_state est fourni ou si une session existe pour la plateforme,
        les cookies sont rechargés automatiquement.
        """
        resolved_headless = self.headless if headless is None else headless
        session_path = storage_state or self.session_manager.load_storage_state(platform)

        stealth = Stealth(navigator_languages_override=(self.locale, self.locale.split('-')[0]))
        stealth_cm = stealth.use_sync(sync_playwright())
        playwright = stealth_cm.__enter__()

        browser = playwright.chromium.launch(
            headless=resolved_headless,
            args=CHROMIUM_LAUNCH_ARGS,
        )

        context_kwargs = {
            'viewport': self.viewport,
            'user_agent': self.user_agent,
            'locale': self.locale,
            'timezone_id': self.timezone,
        }

        if session_path:
            context_kwargs['storage_state'] = session_path
            logger.info('Session %s chargée.', platform)
        else:
            logger.info('Nouvelle session vierge pour %s.', platform)

        if self.proxy_server:
            context_kwargs['proxy'] = {'server': self.proxy_server}
            logger.info('Proxy actif pour %s : %s', platform, self.proxy_server)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        return StealthBrowserBundle(
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
            stealth_cm=stealth_cm,
        )
