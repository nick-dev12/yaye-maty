"""Audit infrastructure scraping + NLP — sortie JSON."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django
django.setup()

from django.utils import timezone

from intelligence.models import MarketSearchKeyword, SocialComment, SocialPost
from intelligence.scrapers.tiktok_scrape_schema import serialize_post_for_nlp
from intelligence.services.nlp_analysis_service import NlpAnalysisService
from intelligence.services.social_comment_service import SocialCommentService

REQUIRED_POST_FIELDS = [
    'platform_post_id', 'content', 'view_count', 'like_count',
    'share_count', 'save_count', 'hashtags', 'published_at', 'comments_scraped_count',
]


def audit_posts(limit=20):
    tiktok = SocialPost.objects.filter(platform='tiktok').order_by('-scraped_at')
    samples = []
    stats = {
        'total_tiktok': tiktok.count(),
        'with_video_id': tiktok.exclude(platform_post_id='').count(),
        'with_metrics': tiktok.filter(view_count__isnull=False).count(),
        'with_saves': tiktok.filter(save_count__isnull=False).count(),
        'with_comments_json': 0,
        'with_comments_10_plus': 0,
        'comments_scraped_total': 0,
        'analysis_pending': tiktok.filter(analysis_status='pending').count(),
        'analysis_done': tiktok.filter(analysis_status='done').count(),
    }

    for post in tiktok[:limit]:
        comments = post.comments or []
        if comments:
            stats['with_comments_json'] += 1
        if len(comments) >= 10:
            stats['with_comments_10_plus'] += 1
        stats['comments_scraped_total'] += len(comments)

        missing = [f for f in REQUIRED_POST_FIELDS if not getattr(post, f, None) and f != 'comments_scraped_count']
        if f := 'comments_scraped_count':
            if post.comments_scraped_count == 0 and not comments:
                missing.append('comments')

        first_comment = comments[0] if comments else {}
        samples.append({
            'id': post.pk,
            'video_id': post.platform_post_id,
            'metrics': {
                'views': post.view_count,
                'likes': post.like_count,
                'shares': post.share_count,
                'saves': post.save_count,
            },
            'hashtags_count': len(post.hashtags or []),
            'published_at': post.published_at.isoformat() if post.published_at else None,
            'comments_count': len(comments),
            'comments_scraped_count': post.comments_scraped_count,
            'analysis_status': post.analysis_status,
            'category': post.category,
            'sentiment': post.sentiment,
            'demand_score': post.demand_score,
            'missing_fields': missing,
            'first_comment_keys': list(first_comment.keys()) if isinstance(first_comment, dict) else [],
            'nlp_export_keys': list(serialize_post_for_nlp(post).keys()),
        })

    return stats, samples


def main():
    report = {
        'timestamp': timezone.now().isoformat(),
        'keywords_active': MarketSearchKeyword.objects.filter(is_active=True).count(),
        'social_comments_before': SocialComment.objects.count(),
    }

    stats, samples = audit_posts()
    report['post_stats'] = stats
    report['samples'] = samples

    sync_stats = SocialCommentService.sync_all_from_posts(limit=500)
    report['comment_sync'] = sync_stats
    report['social_comments_after_sync'] = SocialComment.objects.count()

    nlp_result = NlpAnalysisService.run_full_pipeline(comment_limit=50, post_limit=20)
    report['nlp_pipeline'] = nlp_result

    analyzed_comments = SocialComment.objects.filter(is_analyzed=True).count()
    report['comments_analyzed'] = analyzed_comments
    report['comment_intents'] = list(
        SocialComment.objects.filter(is_analyzed=True)
        .values_list('intent', flat=True)
        .distinct()
    )

    out_path = Path(__file__).parent / 'infrastructure_audit_report.json'
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
