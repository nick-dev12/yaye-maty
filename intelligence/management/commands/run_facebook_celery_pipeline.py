"""
Pipeline Celery dédié Facebook : scrape groupes → NLP → Top 10.

Prérequis : session facebook.json (init_social_session).

Usage :
  celery -A yayematy_project worker -l info -P solo -n worker1@%h
  python manage.py run_facebook_celery_pipeline
  python manage.py run_facebook_celery_pipeline --headed  # debug local sync
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.models import SocialScrapeTarget
from intelligence.scrapers.constants import PLATFORM_FACEBOOK
from intelligence.scrapers.social_scraper import SocialScraper


class Command(BaseCommand):
    help = 'Scrape Facebook (Celery) + analyse NLP + Top 10 recommandations.'

    def add_arguments(self, parser):
        parser.add_argument('--wait-timeout', type=int, default=1800)
        parser.add_argument('--nlp-timeout', type=int, default=900)
        parser.add_argument('--headed', action='store_true', help='Scrape local sans Celery.')
        parser.add_argument('--target-id', type=int, default=None)

    def handle(self, *args, **options):
        scraper = SocialScraper()
        if not scraper.session_manager.session_exists(PLATFORM_FACEBOOK):
            raise CommandError(
                'Session Facebook absente. Exécutez d\'abord :\n'
                '  python manage.py init_social_session --platform facebook'
            )

        fb_count = SocialScrapeTarget.objects.filter(
            platform=PLATFORM_FACEBOOK,
            is_active=True,
        ).count()
        if not fb_count:
            raise CommandError(
                'Aucune cible Facebook active. Lancez migrate puis add_facebook_group.'
            )

        if options['headed']:
            return self._run_sync(options)

        self._check_celery()
        from intelligence.tasks import (
            analyze_pending_social_nlp,
            generate_top_purchase_recommendations,
            scrape_social_posts_bottom_up,
        )

        self.stdout.write(self.style.WARNING('[1/3] Scrape Facebook via Celery...'))
        scrape_task = scrape_social_posts_bottom_up.delay(
            target_id=options['target_id'],
            platform=PLATFORM_FACEBOOK if not options['target_id'] else None,
        )
        scrape_result = scrape_task.get(timeout=options['wait_timeout'])
        self.stdout.write(self.style.SUCCESS(f'  task_id={scrape_task.id}'))
        self.stdout.write(str(scrape_result))

        self.stdout.write(self.style.WARNING('[2/3] NLP hybride via Celery...'))
        nlp_task = analyze_pending_social_nlp.delay(comment_limit=200, post_limit=100)
        nlp_result = nlp_task.get(timeout=options['nlp_timeout'])
        self.stdout.write(self.style.SUCCESS(f'  task_id={nlp_task.id}'))
        self.stdout.write(str(nlp_result))

        self.stdout.write(self.style.WARNING('[3/3] Top 10 via Celery...'))
        top_task = generate_top_purchase_recommendations.delay(window_days=7)
        top_result = top_task.get(timeout=120)
        self.stdout.write(self.style.SUCCESS(f'  task_id={top_task.id}'))
        self.stdout.write(str(top_result))
        self.stdout.write(self.style.SUCCESS('Pipeline Facebook terminé.'))

    def _run_sync(self, options):
        from intelligence.controllers.social_scraper_controller import SocialScraperController
        from intelligence.services.nlp_analysis_service import NlpAnalysisService
        from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService

        controller = SocialScraperController()
        if options['target_id']:
            results = [controller.extract_target(options['target_id'], headless=False)]
        else:
            from intelligence.services.social_extraction_service import SocialExtractionService
            service = SocialExtractionService(controller.scraper)
            results = service.run_active_targets(headless=False, platform=PLATFORM_FACEBOOK)

        for result in results:
            self.stdout.write(f'{result.label} : {result.created} créé(s), {result.extracted} extrait(s)')

        nlp = NlpAnalysisService.run_full_pipeline(comment_limit=200, post_limit=100)
        top = PurchaseRecommendationService.refresh_top_recommendations()
        self.stdout.write(str(nlp))
        self.stdout.write(str(top))

    @staticmethod
    def _check_celery():
        from intelligence.tasks import ping_celery

        try:
            result = ping_celery.delay()
            result.get(timeout=20)
        except Exception as exc:
            raise CommandError(
                'Worker Celery requis :\n'
                '  celery -A yayematy_project worker -l info -P solo -n worker1@%h'
            ) from exc
