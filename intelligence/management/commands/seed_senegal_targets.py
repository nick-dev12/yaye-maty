"""Réactive les cibles TikTok orientées Sénégal."""

from django.core.management.base import BaseCommand

from intelligence.models import SocialScrapeTarget
from intelligence.scrapers.senegal_targets import LEGACY_GENERIC_URLS, get_all_senegal_targets


class Command(BaseCommand):
    help = 'Configure les cibles TikTok Sénégal (hashtags + recherches locales).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--deactivate-legacy',
            action='store_true',
            help='Désactive les anciens hashtags génériques (#agriculture, #elevage).',
        )

    def handle(self, *args, **options):
        if options['deactivate_legacy']:
            updated = SocialScrapeTarget.objects.filter(
                url__in=LEGACY_GENERIC_URLS,
            ).update(is_active=False)
            self.stdout.write(self.style.WARNING(f'{updated} cible(s) générique(s) désactivée(s).'))

        created = 0
        updated = 0

        for data in get_all_senegal_targets():
            _, was_created = SocialScrapeTarget.objects.update_or_create(
                url=data['url'],
                defaults=data,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Cibles Sénégal : {created} créée(s), {updated} mise(s) à jour.'
        ))
