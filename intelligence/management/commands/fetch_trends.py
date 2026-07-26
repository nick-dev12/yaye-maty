"""
Commande Django : collecte des tendances Google Trends.

Usage :
    python manage.py fetch_trends
    python manage.py fetch_trends --keywords tracteur engrais "pompe solaire"
    python manage.py fetch_trends --timeframe "today 12-m" --region SN
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.controllers.google_trends_controller import (
    DEFAULT_KEYWORDS,
    DEFAULT_REGION,
    DEFAULT_TIMEFRAME,
    GoogleTrendsController,
)


class Command(BaseCommand):
    help = 'Collecte les tendances Google Trends et les enregistre en base de données.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keywords',
            nargs='+',
            default=None,
            help='Mots-clés à interroger (max 5 par requête, lots automatiques).',
        )
        parser.add_argument(
            '--timeframe',
            default=DEFAULT_TIMEFRAME,
            help=f'Période Google Trends (défaut : {DEFAULT_TIMEFRAME}).',
        )
        parser.add_argument(
            '--region',
            default=DEFAULT_REGION,
            help=f'Code pays ISO (défaut : {DEFAULT_REGION} = Sénégal).',
        )

    def handle(self, *args, **options):
        keywords = options['keywords'] or DEFAULT_KEYWORDS
        timeframe = options['timeframe']
        region = options['region']

        self.stdout.write(
            self.style.NOTICE(
                f'Collecte Google Trends — {len(keywords)} mot(s)-clé(s), '
                f'région {region}, période {timeframe}'
            )
        )
        self.stdout.write(f'Mots-clés : {", ".join(keywords)}')

        controller = GoogleTrendsController()

        try:
            stats = controller.fetch_and_save_batches(
                keywords,
                timeframe=timeframe,
                region=region,
            )
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f'Collecte terminée — {stats["batches"]} lot(s), '
                f'{stats["created"]} créé(s), {stats["updated"]} mis à jour, '
                f'{stats["total_rows"]} ligne(s) traitées.'
            )
        )
