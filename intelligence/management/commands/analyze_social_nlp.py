"""Lance le pipeline NLP hybride (filtre Wolof/FR + CamemBERT)."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Analyse NLP des publications et commentaires sociaux (hybride + CamemBERT).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--async',
            action='store_true',
            help='Délègue à Celery (nécessite worker + Redis actifs).',
        )
        parser.add_argument(
            '--sync-only',
            action='store_true',
            help='Synchronise uniquement les commentaires JSON → SocialComment.',
        )
        parser.add_argument(
            '--comments-only',
            action='store_true',
            help='Analyse uniquement les intentions de commentaires.',
        )
        parser.add_argument(
            '--comment-limit',
            type=int,
            default=100,
            help='Nombre max de commentaires à analyser.',
        )
        parser.add_argument(
            '--post-limit',
            type=int,
            default=50,
            help='Nombre max de publications à analyser.',
        )

    def handle(self, *args, **options):
        if options['async']:
            from intelligence.tasks import analyze_pending_social_nlp

            result = analyze_pending_social_nlp.delay(
                comment_limit=options['comment_limit'],
                post_limit=options['post_limit'],
            )
            self.stdout.write(self.style.SUCCESS(
                f'Tâche Celery lancée : {result.id}'
            ))
            return

        from intelligence.services.nlp_analysis_service import NlpAnalysisService

        if options['sync_only']:
            stats = NlpAnalysisService.sync_comments_from_posts(limit=options['comment_limit'] * 2)
            self.stdout.write(self.style.SUCCESS(f'Sync commentaires : {stats}'))
            return

        if options['comments_only']:
            NlpAnalysisService.sync_comments_from_posts(limit=options['comment_limit'] * 2)
            stats = NlpAnalysisService.analyze_pending_comments(limit=options['comment_limit'])
            self.stdout.write(self.style.SUCCESS(f'Analyse commentaires : {stats}'))
            return

        result = NlpAnalysisService.run_full_pipeline(
            comment_limit=options['comment_limit'],
            post_limit=options['post_limit'],
        )
        self.stdout.write(self.style.SUCCESS(f'Pipeline NLP : {result}'))
