"""
Scraper réseaux sociaux — navigation furtive Playwright Stealth.

Phase 1 : configuration anti-détection + sessions cookies.
Phase 2 (à venir) : extraction et persistance des publications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from intelligence.scrapers.browser_factory import StealthBrowserFactory
from intelligence.scrapers.constants import (
    DEFAULT_PLATFORM_URLS,
    NAVIGATION_SLEEP_MAX,
    NAVIGATION_SLEEP_MIN,
    PLATFORM_FACEBOOK,
    PLATFORM_TIKTOK,
)
from intelligence.scrapers.human_behavior import (
    organic_scroll,
    random_sleep,
    subtle_mouse_movement,
)
from intelligence.scrapers.session_manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """Résultat minimal d'une navigation test."""

    platform: str
    url: str
    title: str
    session_saved: bool
    session_exists: bool
    success: bool
    message: str


class SocialScraper:
    """
    Scraper social indétectable.

    Méthode anti-bot :
    1. Playwright Stealth (masque navigator.webdriver)
    2. Cookies persistés (pas de login automatisé)
    3. Comportement organique (scroll, pauses, souris)
    """

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        browser_factory: StealthBrowserFactory | None = None,
    ):
        self.session_manager = session_manager or SessionManager()
        self.browser_factory = browser_factory or StealthBrowserFactory(self.session_manager)

    def init_session_interactive(
        self,
        platform: str,
        *,
        url: str | None = None,
        wait_seconds: int = 120,
    ) -> str:
        """
        Ouvre un navigateur visible pour connexion manuelle.

        L'utilisateur se connecte à la main, puis la session est sauvegardée.
        """
        target_url = url or DEFAULT_PLATFORM_URLS.get(platform)
        if not target_url:
            raise ValueError(f'URL par défaut introuvable pour {platform}.')

        bundle = self.browser_factory.open(platform, headless=False)

        try:
            page = bundle.page
            page.goto(target_url, wait_until='domcontentloaded', timeout=60_000)
            random_sleep(NAVIGATION_SLEEP_MIN, NAVIGATION_SLEEP_MAX)

            print(
                f'\n>>> Connectez-vous manuellement sur {SessionManager.platform_label(platform)} '
                f'({wait_seconds}s max).\n'
                f'>>> Quand c\'est fait, revenez ici et appuyez sur Entrée.\n'
            )

            try:
                input('Appuyez sur Entrée pour sauvegarder la session… ')
            except EOFError:
                logger.info('Mode non interactif — attente %ss avant sauvegarde.', wait_seconds)
                random_sleep(wait_seconds, wait_seconds + 2)

            subtle_mouse_movement(page)
            organic_scroll(page, iterations=1)

            path = self.session_manager.save_storage_state(bundle.context, platform)
            return str(path)

        finally:
            bundle.close()

    def scrape_target(
        self,
        platform: str,
        url: str,
        *,
        headless: bool | None = None,
        save_session: bool = True,
    ) -> ScrapeResult:
        """
        Navigue vers une cible avec comportement humain.

        Utile pour valider que la session et le stealth fonctionnent.
        """
        had_session = self.session_manager.session_exists(platform)
        bundle = self.browser_factory.open(platform, headless=headless)

        try:
            page = bundle.page
            logger.info('Navigation vers %s', url)
            page.goto(url, wait_until='domcontentloaded', timeout=60_000)
            random_sleep(NAVIGATION_SLEEP_MIN, NAVIGATION_SLEEP_MAX)

            subtle_mouse_movement(page)
            organic_scroll(page)

            title = page.title()
            session_saved = False

            if save_session:
                self.session_manager.save_storage_state(bundle.context, platform)
                session_saved = True

            return ScrapeResult(
                platform=platform,
                url=url,
                title=title,
                session_saved=session_saved,
                session_exists=had_session or session_saved,
                success=True,
                message='Navigation réussie sans erreur.',
            )

        except Exception as exc:
            logger.exception('Échec scraping %s : %s', platform, exc)
            return ScrapeResult(
                platform=platform,
                url=url,
                title='',
                session_saved=False,
                session_exists=had_session,
                success=False,
                message=str(exc),
            )
        finally:
            bundle.close()

    @staticmethod
    def default_url(platform: str) -> str:
        url = DEFAULT_PLATFORM_URLS.get(platform)
        if not url:
            raise ValueError(f'Plateforme inconnue : {platform}')
        return url

    @staticmethod
    def supported_platforms() -> tuple[str, ...]:
        return (PLATFORM_FACEBOOK, PLATFORM_TIKTOK)
