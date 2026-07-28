"""Recalcule les opportunités d'importation du jour (Import Master)."""

from django.core.management.base import BaseCommand

from intelligence.models import ImportOpportunity
from intelligence.services.import_scoring_service import ImportScoringService


class Command(BaseCommand):
    help = "Recalcule le classement Import Master (Acheter / Surveiller / Éviter) par mot-clé actif."

    def add_arguments(self, parser):
        parser.add_argument('--window-days', type=int, default=7)

    def handle(self, *args, **options):
        result = ImportScoringService.refresh_opportunities(
            window_days=options['window_days'],
        )
        self.stdout.write(self.style.SUCCESS(f'Import Master : {result}'))

        rows = ImportOpportunity.objects.filter(
            snapshot_date=result['snapshot_date'],
        ).order_by('rank')
        if not rows:
            self.stdout.write(self.style.WARNING(
                'Aucune opportunité — activez des mots-clés dans Paramètres puis collectez des données.'
            ))
            return

        self.stdout.write('Classement du jour :')
        for row in rows:
            name = row.product_name.encode('ascii', errors='replace').decode('ascii')
            self.stdout.write(
                f'  #{row.rank} {name} - {row.score}/100 - {row.get_decision_display()}'
            )
