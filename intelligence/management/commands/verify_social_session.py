"""
Vérifie qu'une session Playwright (cookies) est valide pour une plateforme.

Usage :
    python manage.py verify_social_session --platform facebook
    python manage.py verify_social_session --platform facebook --headed
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.scrapers.constants import PLATFORM_FACEBOOK
from intelligence.scrapers.social_scraper import SocialScraper


class Command(BaseCommand):
    help = 'Teste la session cookies sauvegardée (connexion toujours active ?).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            required=True,
            choices=SocialScraper.supported_platforms(),
        )
        parser.add_argument(
            '--headed',
            action='store_true',
            help='Navigateur visible pour contrôle visuel.',
        )

    def handle(self, *args, **options):
        platform = options['platform']
        scraper = SocialScraper()

        if not scraper.session_manager.session_exists(platform):
            raise CommandError(
                f'Aucune session {platform}. Lancez d\'abord :\n'
                f'  python manage.py init_social_session --platform {platform}'
            )

        session_path = scraper.session_manager.get_session_path(platform)
        self.stdout.write(f'Session trouvée : {session_path}')

        test_url = 'https://www.facebook.com/' if platform == PLATFORM_FACEBOOK else SocialScraper.default_url(platform)
        headless = False if options['headed'] else None

        result = scraper.scrape_target(platform, test_url, headless=headless, save_session=True)

        if not result.success:
            raise CommandError(f'Échec navigation : {result.message}')

        self.stdout.write(self.style.SUCCESS(f'Navigation OK — {result.title}'))

        if platform == PLATFORM_FACEBOOK:
            bundle = scraper.browser_factory.open(platform, headless=headless)
            try:
                page = bundle.page
                page.goto('https://www.facebook.com/', wait_until='domcontentloaded', timeout=60_000)
                content = page.content().lower()
                logged_in = (
                    'logout' in content
                    or 'déconnexion' in content
                    or page.locator('[aria-label="Compte"]').count() > 0
                    or page.locator('[aria-label="Account"]').count() > 0
                    or page.locator('[data-pagelet="LeftRail"]').count() > 0
                )
                if logged_in:
                    self.stdout.write(self.style.SUCCESS('Session Facebook : connecté (fil détecté).'))
                else:
                    self.stdout.write(self.style.WARNING(
                        'Session chargée mais connexion incertaine. '
                        'Relancez init_social_session --platform facebook.'
                    ))
            finally:
                bundle.close()

        self.stdout.write(self.style.SUCCESS('Session rafraîchie et sauvegardée.'))
