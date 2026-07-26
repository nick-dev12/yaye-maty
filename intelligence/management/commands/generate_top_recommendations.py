"""Recalcule le Top 10 produits à sourcer."""

from django.core.management.base import BaseCommand

from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService


class Command(BaseCommand):
    help = 'Backfill extraction produit + recalcule le Top 10 recommandations achat.'

    def add_arguments(self, parser):
        parser.add_argument('--window-days', type=int, default=7)
        parser.add_argument('--backfill-limit', type=int, default=1000)

    def handle(self, *args, **options):
        backfill = PurchaseRecommendationService.backfill_extracted_products(
            limit=options['backfill_limit'],
        )
        result = PurchaseRecommendationService.refresh_top_recommendations(
            window_days=options['window_days'],
        )
        self.stdout.write(self.style.SUCCESS(f'Backfill : {backfill}'))
        self.stdout.write(self.style.SUCCESS(f'Top 10 : {result}'))

        top = PurchaseRecommendationService.get_top_for_display(limit=10)
        if not top:
            self.stdout.write(self.style.WARNING('Aucune recommandation — enrichissez les données TikTok/NLP.'))
            return

        self.stdout.write('Classement :')
        for item in top:
            evidence = item['evidence_text'].replace('\u202f', ' ')
            name = item['product_name'].encode('ascii', errors='replace').decode('ascii')
            self.stdout.write(
                f"  #{item['rank']} {name} - {item['score']}/100 - {evidence}"
            )
