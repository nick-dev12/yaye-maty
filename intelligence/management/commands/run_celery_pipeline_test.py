"""
Test complet du pipeline via Celery (worker + Redis requis).

Usage :
  # Terminal 1 — worker
  celery -A yayematy_project worker -l info -P solo

  # Terminal 2 — test
  python manage.py run_celery_pipeline_test
  python manage.py run_celery_pipeline_test --max-videos 5 --keyword-count 2 --wait-timeout 1800
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Count, Q

from intelligence.models import MarketSearchKeyword, SocialComment, SocialPost
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService


class Command(BaseCommand):
    help = (
        'Pipeline Celery : scrape Top-Down (2 mots-cles) -> NLP hybride -> Top 10 -> audit.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--max-videos', type=int, default=5)
        parser.add_argument('--keyword-count', type=int, default=2)
        parser.add_argument('--wait-timeout', type=int, default=1800, help='Timeout scrape (s)')
        parser.add_argument('--nlp-timeout', type=int, default=900, help='Timeout NLP (s)')
        parser.add_argument('--skip-scrape', action='store_true')
        parser.add_argument('--skip-enrich', action='store_true')

    def handle(self, *args, **options):
        self._check_redis()
        self._check_celery_worker()

        keywords = list(
            MarketSearchKeyword.objects.filter(is_active=True).order_by('keyword')[
                : options['keyword_count']
            ]
        )
        if len(keywords) < options['keyword_count']:
            raise CommandError(
                f'Il faut au moins {options["keyword_count"]} MarketSearchKeyword actifs.'
            )

        for kw in keywords:
            kw.max_videos = options['max_videos']
            kw.save(update_fields=['max_videos', 'updated_at'])
            self.stdout.write(f'Mot-cle #{kw.pk} : {kw.keyword} (max {kw.max_videos} videos)')

        scrape_summary = []
        if not options['skip_scrape']:
            from intelligence.tasks import scrape_market_search_keywords

            self.stdout.write(self.style.WARNING('\n[1/4] Scrape Top-Down via Celery...'))
            for kw in keywords:
                self.stdout.write(f'  -> Tache scrape keyword_id={kw.pk} ({kw.keyword})')
                async_result = scrape_market_search_keywords.delay(keyword_id=kw.pk)
                payload = async_result.get(timeout=options['wait_timeout'])
                scrape_summary.append(payload)
                self.stdout.write(self.style.SUCCESS(f'     task_id={async_result.id} OK'))
                self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            self.stdout.write(self.style.WARNING('Scrape ignore (--skip-scrape).'))

        if not options['skip_enrich']:
            from intelligence.tasks import enrich_social_comments_batch

            self.stdout.write(self.style.WARNING('\n[2/4] Enrichissement metriques + commentaires (Celery)...'))
            enrich_result = enrich_social_comments_batch.delay(
                limit=20,
                max_comments=20,
                refresh_metrics=True,
                analyze=False,
            )
            enrich_payload = enrich_result.get(timeout=options['nlp_timeout'])
            self.stdout.write(self.style.SUCCESS(f'  task_id={enrich_result.id}'))
            self.stdout.write(json.dumps(enrich_payload, indent=2, ensure_ascii=True, default=str))

        from intelligence.tasks import analyze_pending_social_nlp

        self.stdout.write(self.style.WARNING('\n[3/4] Analyse NLP hybride via Celery...'))
        nlp_result = analyze_pending_social_nlp.delay(
            comment_limit=200,
            post_limit=100,
        )
        nlp_payload = nlp_result.get(timeout=options['nlp_timeout'])
        self.stdout.write(self.style.SUCCESS(f'  task_id={nlp_result.id}'))
        self.stdout.write(json.dumps(nlp_payload, indent=2, ensure_ascii=True, default=str))

        from intelligence.tasks import generate_top_purchase_recommendations

        self.stdout.write(self.style.WARNING('\n[4/4] Top 10 recommandations via Celery...'))
        top_result = generate_top_purchase_recommendations.delay(window_days=7)
        top_payload = top_result.get(timeout=120)
        self.stdout.write(self.style.SUCCESS(f'  task_id={top_result.id}'))
        self.stdout.write(json.dumps(top_payload, indent=2, ensure_ascii=True, default=str))

        audit = self._build_audit(keywords, scrape_summary)
        self.stdout.write(self.style.SUCCESS('\n=== AUDIT FINAL ==='))
        self.stdout.write(json.dumps(audit, indent=2, ensure_ascii=True, default=str))

        top = PurchaseRecommendationService.get_top_for_display(limit=10)
        self.stdout.write(self.style.SUCCESS('\n=== TOP 10 AFFICHE ==='))
        for item in top:
            evidence = item['evidence_text'].replace('\u202f', ' ')
            self.stdout.write(
                f"#{item['rank']} {item['product_name']} ({item['score']}/100) - {evidence}"
            )

        if audit.get('issues'):
            self.stdout.write(self.style.WARNING('\nPoints a surveiller :'))
            for issue in audit['issues']:
                self.stdout.write(f'  - {issue}')
        else:
            self.stdout.write(self.style.SUCCESS('\nPipeline Celery OK.'))

    def _check_redis(self) -> None:
        try:
            from django.conf import settings
            import redis

            client = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=5)
            if not client.ping():
                raise CommandError('Redis/Memurai ne repond pas au PING.')
            self.stdout.write(self.style.SUCCESS(f'Redis OK ({settings.CELERY_BROKER_URL})'))
        except ImportError as exc:
            raise CommandError('Package redis manquant : pip install redis') from exc
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                f'Redis indisponible : {exc}. Lancez Memurai/Redis puis le worker Celery.'
            ) from exc

    def _check_celery_worker(self) -> None:
        from intelligence.tasks import ping_celery

        try:
            result = ping_celery.delay()
            payload = result.get(timeout=20)
            self.stdout.write(self.style.SUCCESS(
                f'Celery worker OK — task_id={result.id}, response={payload}'
            ))
        except Exception as exc:
            raise CommandError(
                'Worker Celery indisponible. Terminal separe :\n'
                '  celery -A yayematy_project worker -l info -P solo'
            ) from exc

    def _build_audit(self, keywords, scrape_summary) -> dict:
        issues: list[str] = []
        keyword_labels = [k.keyword for k in keywords]

        for payload in scrape_summary:
            if not payload.get('success', payload.get('keywords', 0)):
                issues.append(f'Scrape partiel : {payload}')
            for detail in payload.get('details', []):
                if not detail.get('success'):
                    issues.append(f"Echec scrape « {detail.get('keyword')} »")
                elif detail.get('urls_harvested', 0) < 1:
                    issues.append(f"Aucune URL pour « {detail.get('keyword')} »")

        recent = SocialPost.objects.order_by('-scraped_at')[:15]
        posts_data = []
        for post in recent:
            missing = []
            if post.view_count is None:
                missing.append('views')
            if post.like_count is None:
                missing.append('likes')
            if not post.hashtags:
                missing.append('hashtags')
            if (post.comments_scraped_count or 0) < 1 and not post.comments:
                missing.append('comments')

            posts_data.append({
                'id': post.pk,
                'video_id': post.platform_post_id,
                'views': post.view_count,
                'likes': post.like_count,
                'comments_scraped': post.comments_scraped_count,
                'hashtags_count': len(post.hashtags or []),
                'extracted_product': post.extracted_product,
                'purchase_intents': post.purchase_intent_count,
                'demand_score': post.demand_score,
                'missing': missing,
            })
            if missing:
                issues.append(f'Post {post.pk} : manque {missing}')

        agg = SocialPost.objects.aggregate(
            total=Count('id'),
            with_views=Count('id', filter=Q(view_count__isnull=False)),
            with_likes=Count('id', filter=Q(like_count__isnull=False)),
            with_hashtags=Count('id', filter=~Q(hashtags=[])),
            analyzed=Count('id', filter=Q(analysis_status=SocialPost.AnalysisStatus.DONE)),
            avg_demand=Avg('demand_score'),
        )
        comments_agg = SocialComment.objects.aggregate(
            total=Count('id'),
            analyzed=Count('id', filter=Q(is_analyzed=True)),
            with_product=Count('id', filter=~Q(extracted_product_slug='')),
            purchase=Count('id', filter=Q(intent=SocialComment.Intent.PURCHASE)),
        )

        return {
            'keywords_tested': keyword_labels,
            'scrape_summary': scrape_summary,
            'recent_posts': posts_data,
            'posts_aggregate': agg,
            'comments_aggregate': comments_agg,
            'top_count': PurchaseRecommendationService.get_top_for_display(limit=10).__len__(),
            'issues': issues,
        }
