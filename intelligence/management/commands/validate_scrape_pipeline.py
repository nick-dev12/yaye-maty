"""
Validation pipeline : mots-clés TikTok → scrape → NLP → Top 10.

Usage :
  python manage.py validate_scrape_pipeline --max-videos 5
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Q

from intelligence.models import MarketSearchKeyword, SocialComment, SocialPost
from intelligence.services.nlp_analysis_service import NlpAnalysisService
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService
from intelligence.services.search_top_down_service import SearchTopDownService


class Command(BaseCommand):
    help = 'Teste scrape Top-Down (2 mots-clés, 5 vidéos) + NLP + Top 10 + audit métriques.'

    def _safe_write(self, message: str, style=None) -> None:
        """Evite UnicodeEncodeError sur console Windows (cp1252)."""
        text = message.encode('ascii', errors='replace').decode('ascii')
        if style:
            self.stdout.write(style(text))
        else:
            self.stdout.write(text)

    def add_arguments(self, parser):
        parser.add_argument('--max-videos', type=int, default=5, help='Vidéos par mot-clé')
        parser.add_argument('--keyword-count', type=int, default=2)
        parser.add_argument('--skip-scrape', action='store_true')
        parser.add_argument('--headless', action='store_true', default=True)

    def handle(self, *args, **options):
        max_videos = options['max_videos']
        keyword_count = options['keyword_count']

        keywords = list(
            MarketSearchKeyword.objects.filter(is_active=True).order_by('keyword')[:keyword_count]
        )
        if len(keywords) < keyword_count:
            self._safe_write(
                f'Il faut au moins {keyword_count} MarketSearchKeyword actifs en base.',
                self.style.ERROR,
            )
            return

        for kw in keywords:
            kw.max_videos = max_videos
            kw.save(update_fields=['max_videos'])

        scrape_results = []
        if not options['skip_scrape']:
            service = SearchTopDownService()
            for kw in keywords:
                self._safe_write(f'Scrape Top-Down : {kw.keyword} (max {max_videos} videos)...')
                result = service.run_keyword(kw, headless=options['headless'])
                scrape_results.append(result)
                self._safe_write(
                    f"  -> success={result.success} urls={result.urls_harvested} "
                    f"created={result.created} updated={result.updated} extracted={result.extracted}"
                )

        self._safe_write('Pipeline NLP hybride...')
        nlp_stats = NlpAnalysisService.run_full_pipeline(comment_limit=200, post_limit=100)
        self._safe_write(json.dumps(nlp_stats, indent=2, default=str, ensure_ascii=True))

        audit = self._build_audit(keywords, scrape_results)
        self._safe_write('\n=== AUDIT DONNEES ===', self.style.SUCCESS)
        self._safe_write(json.dumps(audit, indent=2, ensure_ascii=True))

        top = PurchaseRecommendationService.get_top_for_display(limit=10)
        self._safe_write('\n=== TOP 10 ===', self.style.SUCCESS)
        if not top:
            self._safe_write('Aucune recommandation (produits non detectes dans les textes).')
        for item in top:
            evidence = item['evidence_text'].replace('\u202f', ' ')
            self._safe_write(
                f"#{item['rank']} {item['product_name']} ({item['score']}/100) - {evidence}"
            )

        issues = audit.get('issues', [])
        if issues:
            self._safe_write('\nPoints a corriger :', self.style.WARNING)
            for issue in issues:
                self._safe_write(f'  - {issue}')
        else:
            self._safe_write('\nAudit OK - metriques et NLP coherents.', self.style.SUCCESS)

    def _build_audit(self, keywords: list[MarketSearchKeyword], scrape_results: list | None = None) -> dict:
        issues: list[str] = []
        keyword_labels = [k.keyword for k in keywords]

        if scrape_results:
            for result in scrape_results:
                if not result.success:
                    issues.append(f"Scrape echoue pour « {result.keyword} » : {result.message}")
                elif result.urls_harvested < 1:
                    issues.append(f"Aucune URL recoltee pour « {result.keyword} ».")
                elif result.extracted < 1:
                    issues.append(f"Aucune video extraite en detail pour « {result.keyword} ».")

        posts = SocialPost.objects.filter(
            Q(content__icontains=keyword_labels[0])
            | Q(content__icontains=keyword_labels[1] if len(keyword_labels) > 1 else keyword_labels[0])
            | Q(keywords__overlap=keyword_labels)
        ).distinct()

        if posts.count() < 2:
            posts = SocialPost.objects.order_by('-scraped_at')[:20]

        posts_data = []
        for post in posts[:20]:
            missing = []
            if post.view_count is None:
                missing.append('views')
            if post.like_count is None:
                missing.append('likes')
            if not post.hashtags:
                missing.append('hashtags')
            if (post.comments_scraped_count or 0) < 1 and not post.comments:
                missing.append('comments')

            analyzed_comments = post.social_comments.filter(is_analyzed=True).count()
            purchase_comments = post.social_comments.filter(
                intent=SocialComment.Intent.PURCHASE,
            ).count()

            posts_data.append({
                'id': post.pk,
                'video_id': post.platform_post_id,
                'views': post.view_count,
                'likes': post.like_count,
                'shares': post.share_count,
                'saves': post.save_count,
                'comment_count_platform': post.comment_count,
                'comments_scraped': post.comments_scraped_count,
                'hashtags': post.hashtags[:8] if post.hashtags else [],
                'analysis_status': post.analysis_status,
                'category': post.category,
                'extracted_product': post.extracted_product,
                'purchase_intents_post': post.purchase_intent_count,
                'analyzed_comments': analyzed_comments,
                'purchase_comments_nlp': purchase_comments,
                'demand_score': post.demand_score,
                'missing_fields': missing,
            })
            if missing:
                issues.append(f"Post {post.pk} : champs manquants {missing}")

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

        if agg['with_views'] < agg['total'] * 0.5:
            issues.append('Plus de 50 % des posts sans vues — vérifier extracteur TikTok.')
        if comments_agg['analyzed'] < comments_agg['total'] * 0.5 and comments_agg['total'] > 0:
            issues.append('Commentaires NLP insuffisamment analysés.')

        return {
            'keywords_tested': keyword_labels,
            'scrape_results': [
                {
                    'keyword': r.keyword,
                    'success': r.success,
                    'urls_harvested': r.urls_harvested,
                    'extracted': r.extracted,
                    'created': r.created,
                    'updated': r.updated,
                    'message': r.message,
                }
                for r in (scrape_results or [])
            ],
            'posts_sample': posts_data,
            'posts_aggregate': agg,
            'comments_aggregate': comments_agg,
            'issues': issues,
        }
