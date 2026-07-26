"""
Ajoute une cible Facebook (groupe ou page) pour le scraping Bottom-Up.

Usage :
    python manage.py add_facebook_group --url "https://www.facebook.com/groups/123456789/" --label "Agriculture SN"
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.models import SocialScrapeTarget


class Command(BaseCommand):
    help = 'Enregistre un groupe ou une page Facebook comme cible de scraping.'

    def add_arguments(self, parser):
        parser.add_argument('--url', required=True, help='URL du groupe Facebook.')
        parser.add_argument('--label', required=True, help='Libellé affiché dans l\'admin.')
        parser.add_argument('--max-posts', type=int, default=15)
        parser.add_argument('--inactive', action='store_true', help='Créer sans activer.')

    def handle(self, *args, **options):
        url = options['url'].strip()
        if 'facebook.com' not in url:
            raise CommandError('URL invalide — doit contenir facebook.com')

        target, created = SocialScrapeTarget.objects.update_or_create(
            url=url,
            defaults={
                'label': options['label'],
                'platform': SocialScrapeTarget.Platform.FACEBOOK,
                'region': 'SN',
                'max_posts': options['max_posts'],
                'scrape_comments': False,
                'max_comments': 0,
                'is_active': not options['inactive'],
            },
        )

        action = 'Créée' if created else 'Mise à jour'
        self.stdout.write(self.style.SUCCESS(
            f'{action} — cible #{target.pk} : {target.label} ({target.url})'
        ))
        self.stdout.write(
            'Scrape : python manage.py scrape_social_posts --target-id '
            f'{target.pk} --headed'
        )
