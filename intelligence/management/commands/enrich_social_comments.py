"""
Commande : ré-enrichissement des commentaires sur publications existantes.

Usage :
    python manage.py enrich_social_comments --limit 10 --headed
    python manage.py enrich_social_comments --all --limit 50 --refresh-metrics --analyze
    python manage.py enrich_social_comments --post-id 170 --analyze
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db.models import Q

from intelligence.models import SocialPost
from intelligence.scrapers.engagement_utils import compute_demand_score, count_purchase_intents
from intelligence.scrapers.extractors.tiktok import TikTokExtractor
from intelligence.scrapers.extractors.tiktok_comment_extractor import TikTokCommentCapture, harvest_video_comments
from intelligence.scrapers.human_behavior import random_sleep
from intelligence.scrapers.social_scraper import SocialScraper
from intelligence.services.social_comment_service import SocialCommentService
from intelligence.services.social_post_service import SocialPostService
from intelligence.scrapers.tiktok_scrape_schema import normalize_comments, MAX_COMMENTS_PER_VIDEO


@dataclass
class _CommentEnrichment:
    post_pk: int
    comments: list[dict]
    comment_count: int
    metrics: dict


class Command(BaseCommand):
    help = 'Ré-extrait commentaires et métriques TikTok sur des publications déjà en base.'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Toutes les publications TikTok avec URL.')
        parser.add_argument('--limit', type=int, default=20, help='Nombre max de publications.')
        parser.add_argument('--post-id', type=int, default=None, help='ID SocialPost ciblé.')
        parser.add_argument('--headed', action='store_true', help='Navigateur visible.')
        parser.add_argument('--max-comments', type=int, default=20, help='Commentaires max / vidéo.')
        parser.add_argument(
            '--refresh-metrics',
            action='store_true',
            help='Met à jour likes/partages/favoris/vues/date même sans nouveaux commentaires.',
        )
        parser.add_argument('--analyze', action='store_true', help='Lance le NLP hybride après enrichissement.')
        parser.add_argument('--async', action='store_true', help='NLP via Celery.')

    def handle(self, *args, **options):
        queryset = (
            SocialPost.objects
            .filter(platform='tiktok')
            .exclude(post_url='')
            .order_by('-scraped_at')
        )

        if options['post_id']:
            queryset = queryset.filter(pk=options['post_id'])
        elif options['all']:
            queryset = queryset[: options['limit']]
        else:
            queryset = queryset.filter(
                Q(comments=[]) | Q(comments__isnull=True) | Q(comments_scraped_count=0),
            )[: options['limit']]

        posts = list(queryset)
        if not posts:
            self.stdout.write(self.style.WARNING('Aucune publication à enrichir.'))
            return

        headless = False if options['headed'] else None
        scraper = SocialScraper()
        extractor = TikTokExtractor()
        bundle = scraper.browser_factory.open('tiktok', headless=headless)
        enrichments: list[_CommentEnrichment] = []

        try:
            page = bundle.page
            for post in posts:
                post_id = post.platform_post_id or ''
                capture = TikTokCommentCapture(post_id=post_id)
                page.on('response', capture.on_response)

                try:
                    page.goto(post.post_url, wait_until='domcontentloaded', timeout=45_000)
                    random_sleep(2.0, 3.5)
                    metrics = extractor._extract_video_page_metrics(page, post_id=post_id)

                    comments = harvest_video_comments(
                        page,
                        post_id=post_id,
                        max_comments=options['max_comments'],
                        capture=capture,
                    )
                finally:
                    try:
                        page.remove_listener('response', capture.on_response)
                    except Exception:
                        pass

                normalized = normalize_comments(
                    comments,
                    video_id=post_id,
                    max_count=options['max_comments'],
                ) if comments else list(post.comments or [])

                if not normalized and not options['refresh_metrics']:
                    self.stdout.write(self.style.WARNING(f'[{post.pk}] Aucun commentaire — {post.post_url}'))
                    continue

                enrichments.append(_CommentEnrichment(
                    post_pk=post.pk,
                    comments=normalized[:MAX_COMMENTS_PER_VIDEO],
                    comment_count=max(post.comment_count or 0, len(normalized)),
                    metrics=metrics,
                ))
                random_sleep(2.0, 4.0)

            scraper.session_manager.save_storage_state(bundle.context, 'tiktok')
        finally:
            bundle.close()

        enriched = 0
        for item in enrichments:
            post = SocialPost.objects.get(pk=item.post_pk)
            update_fields = ['updated_at']

            if item.comments:
                post.comments = item.comments
                post.comment_count = item.comment_count
                post.comments_scraped_count = len(item.comments)
                post.analysis_status = SocialPost.AnalysisStatus.PENDING
                update_fields.extend(['comments', 'comment_count', 'comments_scraped_count', 'analysis_status'])

            metrics = item.metrics
            metric_fields = {
                'view_count': metrics.get('view_count'),
                'like_count': metrics.get('like_count'),
                'share_count': metrics.get('share_count'),
                'save_count': metrics.get('save_count'),
            }
            for field, value in metric_fields.items():
                if value is not None:
                    setattr(post, field, value)
                    update_fields.append(field)

            if metrics.get('published_at') and not post.published_at:
                post.published_at = SocialPostService._parse_published_at(metrics['published_at'])
                update_fields.append('published_at')

            purchase_intent_count = count_purchase_intents(item.comments)
            post.purchase_intent_count = purchase_intent_count
            post.demand_score = compute_demand_score(
                views=post.view_count,
                likes=post.like_count,
                shares=post.share_count,
                saves=post.save_count,
                comment_count=post.comment_count or len(item.comments),
                purchase_intent_count=purchase_intent_count,
            )
            update_fields.extend(['purchase_intent_count', 'demand_score'])

            post.save(update_fields=list(dict.fromkeys(update_fields)))

            sync_stats = SocialCommentService.sync_post_comments(post) if item.comments else {'created': 0, 'updated': 0}
            enriched += 1
            self.stdout.write(self.style.SUCCESS(
                f'[{post.pk}] {len(item.comments)} commentaire(s) — '
                f'likes={post.like_count} shares={post.share_count} saves={post.save_count} — '
                f'sync +{sync_stats["created"]} / ~{sync_stats["updated"]}'
            ))

        repair = SocialCommentService.repair_comments_scraped_count(limit=500)
        self.stdout.write(self.style.SUCCESS(
            f'Terminé — {enriched} publication(s) enrichie(s). '
            f'Compteurs réparés : {repair["fixed"]}/{repair["checked"]}.'
        ))

        if options['analyze']:
            if options['async']:
                from intelligence.tasks import analyze_pending_social_nlp
                task = analyze_pending_social_nlp.delay()
                self.stdout.write(self.style.SUCCESS(f'Pipeline NLP Celery : {task.id}'))
            else:
                from intelligence.services.nlp_analysis_service import NlpAnalysisService
                result = NlpAnalysisService.run_full_pipeline()
                self.stdout.write(self.style.SUCCESS(f'Pipeline NLP : {result}'))
