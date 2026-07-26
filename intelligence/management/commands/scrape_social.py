"""
Commande : test de navigation furtive sur un réseau social.

Usage :
    python manage.py scrape_social --platform tiktok --url "https://www.tiktok.com/tag/agriculteur"
    python manage.py scrape_social --platform facebook --headed
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.controllers.social_scraper_controller import SocialScraperController
from intelligence.scrapers.social_scraper import SocialScraper


class Command(BaseCommand):
    help = 'Teste la navigation Playwright Stealth avec session cookies et comportement humain.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            required=True,
            choices=SocialScraper.supported_platforms(),
            help='Plateforme cible.',
        )
        parser.add_argument(
            '--url',
            required=True,
            help='URL à visiter (groupe Facebook, hashtag TikTok, etc.).',
        )
        parser.add_argument(
            '--headed',
            action='store_true',
            help='Affiche le navigateur (debug local). Sinon utilise SOCIAL_SCRAPER_HEADLESS.',
        )

    def handle(self, *args, **options):
        platform = options['platform']
        url = options['url']
        headless = False if options['headed'] else None

        controller = SocialScraperController()

        if not controller.session_exists(platform):
            self.stdout.write(
                self.style.WARNING(
                    f'Aucune session pour {platform}. '
                    f'Lancez : python manage.py init_social_session --platform {platform}'
                )
            )

        self.stdout.write(self.style.NOTICE(f'Scraping test - {platform} -> {url}'))

        try:
            result = controller.scrape(platform, url, headless=headless)
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        if result.success:
            self.stdout.write(self.style.SUCCESS(f'OK — {result.title}'))
            self.stdout.write(f'Session active : {result.session_exists}')
        else:
            raise CommandError(result.message)
