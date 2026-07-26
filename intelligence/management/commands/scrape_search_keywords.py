"""
Commande : scraping Top-Down par mots-clés de recherche TikTok.

Usage :
    python manage.py scrape_search_keywords --all
    python manage.py scrape_search_keywords --keyword-id 1 --headed
    python manage.py scrape_search_keywords --all --analyze --async
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.models import MarketSearchKeyword
from intelligence.services.search_top_down_service import SearchTopDownService


class Command(BaseCommand):
    help = (
        'Scrape Top-Down TikTok : recherche par mot-clé → URLs vidéo → '
        'métriques + commentaires → base SocialPost.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Scraper tous les mots-clés actifs.',
        )
        parser.add_argument(
            '--keyword-id',
            type=int,
            default=None,
            help='ID d\'un MarketSearchKeyword.',
        )
        parser.add_argument(
            '--headed',
            action='store_true',
            help='Navigateur visible (debug local).',
        )
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Lance le pipeline NLP après le scraping (Celery si --async).',
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Avec --analyze : délègue le NLP à Celery.',
        )
        parser.add_argument(
            '--celery',
            action='store_true',
            help='Délègue le scrape Top-Down à Celery (worker requis).',
        )

    def handle(self, *args, **options):
        if not options['all'] and not options['keyword_id']:
            raise CommandError('Indiquez --all ou --keyword-id <id>.')

        if options['celery']:
            from intelligence.tasks import scrape_market_search_keywords

            task = scrape_market_search_keywords.delay(keyword_id=options['keyword_id'])
            self.stdout.write(self.style.SUCCESS(f'Scrape Top-Down Celery lancé : {task.id}'))
            return

        headless = False if options['headed'] else None
        service = SearchTopDownService()

        if options['keyword_id']:
            keyword = MarketSearchKeyword.objects.filter(
                pk=options['keyword_id'],
                is_active=True,
            ).first()
            if not keyword:
                raise CommandError(f'Mot-clé #{options["keyword_id"]} introuvable ou inactif.')
            results = [service.run_keyword(keyword, headless=headless)]
        else:
            if not MarketSearchKeyword.objects.filter(is_active=True).exists():
                raise CommandError(
                    'Aucun mot-clé actif. Ajoutez-en via Paramètres ou l\'admin Django.'
                )
            results = service.run_active_keywords(headless=headless)

        total_created = 0
        for result in results:
            if result.success:
                total_created += result.created
                self.stdout.write(
                    self.style.SUCCESS(
                        f'[{result.keyword}] {result.urls_harvested} URL(s) — '
                        f'{result.extracted} extrait(s) — '
                        f'{result.created} nouveau(x), {result.updated} maj, '
                        f'{result.skipped} ignoré(s)'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'[{result.keyword}] Échec : {result.message}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Terminé — {total_created} nouvelle(s) publication(s) Top-Down en base.'
            )
        )

        if options['analyze']:
            if options['async']:
                from intelligence.tasks import analyze_pending_social_nlp

                task = analyze_pending_social_nlp.delay()
                self.stdout.write(self.style.SUCCESS(f'Pipeline NLP Celery lancé : {task.id}'))
            else:
                from intelligence.services.nlp_analysis_service import NlpAnalysisService

                nlp_result = NlpAnalysisService.run_full_pipeline()
                self.stdout.write(self.style.SUCCESS(f'Pipeline NLP : {nlp_result}'))
