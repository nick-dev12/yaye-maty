"""
Synchronisation JSON commentaires → modèle structuré (prod ou test via router).
"""

from __future__ import annotations

from django.utils.dateparse import parse_datetime

from intelligence.scrapers.post_id_utils import build_comment_id
from intelligence.services.collection_model_router import CollectionModelRouter


class SocialCommentService:
    """Persiste les commentaires scrapés pour l'analyse hybride Wolof + CamemBERT."""

    @classmethod
    def sync_post_comments(cls, post) -> dict[str, int]:
        """Importe les commentaires JSON d'une publication vers SocialComment / TestSocialComment."""
        router = CollectionModelRouter()
        Comment = router.comment_model
        stats = {'created': 0, 'updated': 0, 'skipped': 0}

        for index, item in enumerate(post.comments or []):
            if isinstance(item, dict):
                text = str(item.get('text', '')).strip()
                platform_comment_id = str(item.get('platform_comment_id', '')).strip()
                published_raw = item.get('commented_at') or item.get('published_at')
            else:
                text = str(item).strip()
                platform_comment_id = ''
                published_raw = None

            if len(text) < 3:
                stats['skipped'] += 1
                continue

            if not platform_comment_id:
                platform_comment_id = build_comment_id(
                    post.platform,
                    post.platform_post_id or str(post.pk),
                    text,
                    index,
                )

            published_at = cls._parse_datetime(published_raw)
            text_hash = Comment.build_text_hash(text)

            comment = Comment.objects.filter(post=post, text_hash=text_hash).first()
            if comment is None and platform_comment_id:
                comment = Comment.objects.filter(
                    post=post,
                    platform_comment_id=platform_comment_id[:100],
                ).first()

            if comment is None:
                Comment.objects.create(
                    post=post,
                    text=text[:2000],
                    text_hash=text_hash,
                    platform_comment_id=platform_comment_id[:100],
                    published_at=published_at,
                )
                stats['created'] += 1
                continue

            text_changed = comment.text != text[:2000]
            comment.text = text[:2000]
            comment.text_hash = text_hash
            if platform_comment_id:
                comment.platform_comment_id = platform_comment_id[:100]
            if published_at:
                comment.published_at = published_at
            if text_changed:
                comment.is_analyzed = False
                comment.intent = ''
                comment.analysis_method = Comment.AnalysisMethod.PENDING
                comment.confidence_score = None
                comment.analyzed_at = None
            comment.save(update_fields=[
                'text', 'text_hash', 'platform_comment_id', 'published_at',
                'is_analyzed', 'intent', 'analysis_method',
                'confidence_score', 'analyzed_at',
            ])
            stats['updated'] += 1

        return stats

    @classmethod
    def sync_all_from_posts(cls, *, limit: int = 500) -> dict[str, int]:
        router = CollectionModelRouter()
        Post = router.post_model
        totals = {'created': 0, 'updated': 0, 'skipped': 0, 'posts': 0}
        posts = (
            Post.objects
            .exclude(comments=[])
            .exclude(comments__isnull=True)
            .order_by('-scraped_at')[:limit]
        )

        for post in posts:
            totals['posts'] += 1
            result = cls.sync_post_comments(post)
            for key in ('created', 'updated', 'skipped'):
                totals[key] += result[key]

        return totals

    @classmethod
    def repair_comments_scraped_count(cls, *, limit: int = 500) -> dict[str, int]:
        """Recalcule comments_scraped_count depuis le JSON comments."""
        router = CollectionModelRouter()
        Post = router.post_model
        stats = {'checked': 0, 'fixed': 0}
        posts = Post.objects.filter(platform='tiktok').order_by('-scraped_at')[:limit]

        for post in posts:
            stats['checked'] += 1
            expected = len(post.comments or [])
            if post.comments_scraped_count != expected:
                post.comments_scraped_count = expected
                post.save(update_fields=['comments_scraped_count', 'updated_at'])
                stats['fixed'] += 1

        return stats

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None
        if hasattr(value, 'isoformat'):
            return value
        return parse_datetime(str(value))
