"""
Commande : connexion manuelle et sauvegarde des cookies.

Usage :
    python manage.py init_social_session --platform facebook
    python manage.py init_social_session --platform tiktok --url "https://www.tiktok.com/"
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.controllers.social_scraper_controller import SocialScraperController
from intelligence.scrapers.constants import PLATFORM_FACEBOOK, PLATFORM_TIKTOK
from intelligence.scrapers.social_scraper import SocialScraper


class Command(BaseCommand):
    help = (
        'Ouvre un navigateur visible pour vous connecter manuellement, '
        'puis sauvegarde les cookies (session_auth) pour le VPS.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            required=True,
            choices=SocialScraper.supported_platforms(),
            help='Plateforme cible (facebook ou tiktok).',
        )
        parser.add_argument(
            '--url',
            default=None,
            help='URL de départ (défaut : page d\'accueil / tag agricole).',
        )
        parser.add_argument(
            '--wait',
            type=int,
            default=120,
            help='Temps d\'attente si le terminal n\'est pas interactif.',
        )

    def handle(self, *args, **options):
        platform = options['platform']
        url = options['url'] or SocialScraper.default_url(platform)
        controller = SocialScraperController()

        self.stdout.write(
            self.style.NOTICE(
                f'Initialisation session {platform} — {url}\n'
                f'Le navigateur va s\'ouvrir en mode visible (headless=False).\n'
            )
        )

        if platform == PLATFORM_FACEBOOK:
            self.stdout.write(self.style.WARNING(
                'FACEBOOK — Étapes :\n'
                '  1. Connectez-vous avec votre compte (email + mot de passe).\n'
                '  2. Validez la 2FA / captcha si Facebook le demande.\n'
                '  3. Visitez un groupe rejoint pour confirmer l\'accès.\n'
                '  4. Revenez ici et appuyez sur ENTRÉE.\n'
                f'Les cookies seront sauvegardés dans data/scraper_sessions/facebook.json\n'
            ))

        try:
            path = controller.init_session(platform, url=url, wait_seconds=options['wait'])
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f'Session sauvegardée : {path}'))
        if platform == PLATFORM_FACEBOOK:
            self.stdout.write(self.style.SUCCESS(
                'Vérifiez la session : python manage.py verify_social_session --platform facebook'
            ))
        self.stdout.write(
            self.style.WARNING(
                'Sur le VPS : placez ce fichier dans data/scraper_sessions/ '
                'et lancez avec SOCIAL_SCRAPER_HEADLESS=True.'
            )
        )
