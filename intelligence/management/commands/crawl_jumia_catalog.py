"""
Crawl catalogue Jumia → JumiaCategory + JumiaProduct (+ avis).

Usage :
    python manage.py crawl_jumia_catalog
    python manage.py crawl_jumia_catalog --category telephones-tablettes
    python manage.py crawl_jumia_catalog --with-reviews
"""

from django.core.management.base import BaseCommand

from intelligence.services.jumia_catalog_crawl_service import JumiaCatalogCrawlService


class Command(BaseCommand):
    help = (
        'Crawl catalogue Jumia SN (toutes catégories par défaut) '
        'vers la BDD — produits + avis.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            default='',
            help='Limiter à une catégorie racine (sinon tout le catalogue).',
        )
        parser.add_argument(
            '--with-reviews',
            action='store_true',
            help='Récupérer tous les avis par produit.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse sans écrire en base.',
        )

    def handle(self, *args, **options):
        def progress(pct, msg):
            if pct is not None and int(pct) >= 0:
                self.stdout.write(f'[{int(pct):3d}%] {msg}')
            else:
                self.stdout.write(msg)

        def log(msg):
            self.stdout.write(msg)

        category = (options.get('category') or '').strip()
        result = JumiaCatalogCrawlService.crawl(
            category,
            with_reviews=bool(options['with_reviews']),
            dry_run=bool(options['dry_run']),
            progress=progress,
            log=log,
        )
        if result.get('success'):
            self.stdout.write(self.style.SUCCESS(result.get('message', 'OK')))
        else:
            self.stderr.write(self.style.ERROR(result.get('message', 'Échec')))
        if result.get('errors'):
            for err in result['errors'][:10]:
                self.stderr.write(f'  · {err}')
        self.stdout.write(
            f"Vu: {result.get('products_seen', 0)} | "
            f"Créés: {result.get('products_created', 0)} | "
            f"Maj: {result.get('products_updated', 0)} | "
            f"Ignorés: {result.get('products_skipped', 0)} | "
            f"Avis: {result.get('reviews_created', 0)} | "
            f"Racines: {result.get('roots_total', 0)} | "
            f"Sous-cats: {result.get('subs_total', 0)}"
        )
        if not result.get('success'):
            raise SystemExit(1)
