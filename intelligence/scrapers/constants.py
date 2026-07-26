"""Constantes du scraping réseaux sociaux."""

from pathlib import Path

# Plateformes supportées
PLATFORM_FACEBOOK = 'facebook'
PLATFORM_TIKTOK = 'tiktok'
PLATFORM_JUMIA = 'jumia'
PLATFORM_JIJI = 'jiji'
PLATFORM_MARKETPLACE = 'marketplace'

SUPPORTED_PLATFORMS = (PLATFORM_FACEBOOK, PLATFORM_TIKTOK)
MARKETPLACE_PLATFORMS = (PLATFORM_MARKETPLACE, PLATFORM_JUMIA, PLATFORM_JIJI)

DEFAULT_PLATFORM_URLS = {
    PLATFORM_FACEBOOK: 'https://www.facebook.com/',
    PLATFORM_TIKTOK: 'https://www.tiktok.com/tag/agriculturesenegal',
}

# Commentaires TikTok — collecte pour analyse hybride NLP
TIKTOK_MIN_COMMENTS = 10
TIKTOK_MAX_COMMENTS = 20
TIKTOK_DEFAULT_MAX_COMMENTS = 20

# Comportement humain simulé
SCROLL_MIN_PX = 280
SCROLL_MAX_PX = 720
SCROLL_ITERATIONS_MIN = 2
SCROLL_ITERATIONS_MAX = 4
SLEEP_MIN_SECONDS = 1.5
SLEEP_MAX_SECONDS = 4.5
NAVIGATION_SLEEP_MIN = 3.0
NAVIGATION_SLEEP_MAX = 6.0

# Navigateur « fantôme »
DEFAULT_VIEWPORT = {'width': 1920, 'height': 1080}
DEFAULT_LOCALE = 'fr-FR'
DEFAULT_TIMEZONE = 'Africa/Dakar'
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)

CHROMIUM_LAUNCH_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-dev-shm-usage',
    '--no-first-run',
    '--no-default-browser-check',
    '--start-maximized',
]

SESSION_FILENAME_TEMPLATE = '{platform}.json'


def get_sessions_dir(base_dir: Path) -> Path:
    """Répertoire des sessions Playwright (cookies)."""
    return base_dir / 'data' / 'scraper_sessions'
