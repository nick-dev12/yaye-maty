"""
Commande : extraction des publications depuis les cibles configurées.

Usage :
    python manage.py scrape_social_posts --all
    python manage.py scrape_social_posts --target-id 1 --headed
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.controllers.social_scraper_controller import SocialScraperController
from intelligence.models import SocialScrapeTarget


class Command(BaseCommand):
    help = 'Extrait les publications des cibles réseaux sociaux actives et les enregistre en base.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Scraper toutes les cibles actives.',
        )
        parser.add_argument(
            '--target-id',
            type=int,
            default=None,
            help='ID d\'une cible SocialScrapeTarget.',
        )
        parser.add_argument(
            '--headed',
            action='store_true',
            help='Navigateur visible (debug local).',
        )
        parser.add_argument(
            '--platform',
            choices=('facebook', 'tiktok'),
            default=None,
            help='Limite le scrape aux cibles de cette plateforme (avec --all).',
        )
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Lance le pipeline NLP après le scraping (Celery si --async).',
        )
        parser.add_argument(
            '--max-posts',
            type=int,
            default=None,
            help='Limite temporaire de publications (override cible).',
        )
        parser.add_argument(
            '--celery',
            action='store_true',
            help='Délègue le scrape Bottom-Up à Celery.',
        )
        parser.add_argument(
            '--async',
            action='store_true',
            dest='run_async',
            help='Pipeline NLP via Celery (avec --analyze).',
        )

    def handle(self, *args, **options):
        if not options['all'] and not options['target_id']:
            raise CommandError('Indiquez --all ou --target-id <id>.')

        if options['celery']:
            from intelligence.tasks import scrape_social_posts_bottom_up
            task = scrape_social_posts_bottom_up.delay(
                target_id=options['target_id'],
                max_posts=options['max_posts'],
                platform=options['platform'],
            )
            self.stdout.write(self.style.SUCCESS(f'Scrape Bottom-Up Celery lancé : {task.id}'))
            return

        controller = SocialScraperController()
        headless = False if options['headed'] else None

        if options['target_id']:
            results = [controller.extract_target(
                options['target_id'],
                headless=headless,
                max_posts=options['max_posts'],
            )]
        else:
            if not SocialScrapeTarget.objects.filter(is_active=True).exists():
                raise CommandError('Aucune cible active. Ajoutez-en via l\'admin Django.')
            if options['platform']:
                from intelligence.services.social_extraction_service import SocialExtractionService
                service = SocialExtractionService(controller.scraper)
                results = service.run_active_targets(headless=headless, platform=options['platform'])
            else:
                results = controller.extract_all_active(headless=headless)

        total_created = 0
        for result in results:
            if result.success:
                total_created += result.created
                self.stdout.write(
                    self.style.SUCCESS(
                        f'[{result.label}] {result.extracted} extrait(s) — '
                        f'{result.created} nouveau(x), {result.updated} maj, {result.skipped} ignoré(s)'
                    )
                )
            else:
                self.stdout.write(self.style.ERROR(f'[{result.label}] Echec : {result.message}'))

        self.stdout.write(
            self.style.SUCCESS(f'Terminé — {total_created} nouvelle(s) publication(s) en base.')
        )

        if options['analyze']:
            if options['run_async']:
                from intelligence.tasks import analyze_pending_social_nlp
                task = analyze_pending_social_nlp.delay()
                self.stdout.write(self.style.SUCCESS(f'Pipeline NLP Celery lancé : {task.id}'))
            else:
                from intelligence.services.nlp_analysis_service import NlpAnalysisService
                result = NlpAnalysisService.run_full_pipeline()
                self.stdout.write(self.style.SUCCESS(f'Pipeline NLP : {result}'))
