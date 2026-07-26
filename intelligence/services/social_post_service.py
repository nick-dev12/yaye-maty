"""Persistance des publications sociales extraites."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from intelligence.models import SocialScrapeTarget
from intelligence.scrapers.constants import PLATFORM_TIKTOK
from intelligence.scrapers.engagement_utils import (
    compute_demand_score,
    count_purchase_intents,
    extract_hashtags,
)
from intelligence.scrapers.extractors.base import ExtractedPost
from intelligence.scrapers.tiktok_scrape_schema import (
    MAX_COMMENTS_PER_VIDEO,
    normalize_comments,
    normalize_extracted_post,
    validation_warnings,
)
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.social_comment_service import SocialCommentService

logger = logging.getLogger(__name__)


class SocialPostService:
    """Enregistre et met à jour les publications sociales."""

    @classmethod
    def save_extracted_posts(
        cls,
        platform: str,
        source_url: str,
        extracted: list[ExtractedPost],
        *,
        skip_if_exists: bool = False,
    ) -> dict[str, int]:
        """
        Persiste les publications extraites.

        TikTok : structure rigoureuse (video_id, métriques, caption, 10–20 commentaires).
        Déduplication par ID plateforme (prioritaire) ou empreinte contenu.
        """
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'total': 0,
            'comments_synced': 0,
            'warnings': 0,
        }
        router = CollectionModelRouter()
        Post = router.post_model

        with transaction.atomic():
            for raw_item in extracted:
                item = normalize_extracted_post(raw_item, platform=platform)

                if not item.is_valid():
                    stats['skipped'] += 1
                    continue

                if platform == PLATFORM_TIKTOK and not item.platform_post_id:
                    logger.warning('TikTok ignoré — video_id manquant : %s', item.post_url)
                    stats['skipped'] += 1
                    continue

                for warning in validation_warnings(item):
                    logger.info('TikTok %s : %s', item.platform_post_id or '?', warning)
                    stats['warnings'] += 1

                content = item.content.strip()[:5000]
                content_hash = Post.build_content_hash(content)
                platform_post_id = item.platform_post_id or Post.resolve_platform_post_id(
                    platform,
                    item.post_url,
                    item.platform_post_id,
                )

                if skip_if_exists:
                    if platform_post_id and Post.objects.filter(
                        platform=platform,
                        platform_post_id=platform_post_id,
                    ).exists():
                        stats['skipped'] += 1
                        continue
                    if Post.objects.filter(platform=platform, content_hash=content_hash).exists():
                        stats['skipped'] += 1
                        continue

                hashtags = item.hashtags or extract_hashtags(content)
                normalized_comments = normalize_comments(
                    item.comments,
                    video_id=platform_post_id,
                    max_count=MAX_COMMENTS_PER_VIDEO,
                )
                stats['total'] += 1

                purchase_intent_count = count_purchase_intents(normalized_comments)
                demand_score = item.metadata.get('demand_score') or compute_demand_score(
                    views=item.view_count,
                    likes=item.like_count,
                    shares=item.share_count,
                    saves=item.save_count,
                    comment_count=item.comment_count or len(normalized_comments),
                    purchase_intent_count=purchase_intent_count,
                )
                published_at = cls._parse_published_at(item.published_at)

                defaults = {
                    'source_url': source_url,
                    'post_url': item.post_url[:500] if item.post_url else '',
                    'author': item.author[:120] if item.author else '',
                    'content': content,
                    'platform_post_id': platform_post_id,
                    'hashtags': hashtags,
                    'view_count': item.view_count,
                    'like_count': item.like_count,
                    'share_count': item.share_count,
                    'save_count': item.save_count,
                    'comment_count': item.comment_count or len(normalized_comments),
                    'comments': normalized_comments,
                    'comments_scraped_count': len(normalized_comments),
                    'purchase_intent_count': purchase_intent_count,
                    'demand_score': demand_score,
                    'published_at': published_at,
                }

                if platform_post_id:
                    post, created = Post.objects.get_or_create(
                        platform=platform,
                        platform_post_id=platform_post_id,
                        defaults={
                            **defaults,
                            'content_hash': content_hash,
                            'analysis_status': Post.AnalysisStatus.PENDING,
                        },
                    )
                else:
                    post, created = Post.objects.get_or_create(
                        platform=platform,
                        content_hash=content_hash,
                        defaults={
                            **defaults,
                            'analysis_status': Post.AnalysisStatus.PENDING,
                        },
                    )

                if not created:
                    for field, value in defaults.items():
                        setattr(post, field, value)
                    post.content_hash = content_hash
                    post.save(update_fields=[*defaults.keys(), 'content_hash', 'updated_at'])

                if normalized_comments:
                    sync_stats = SocialCommentService.sync_post_comments(post)
                    stats['comments_synced'] += sync_stats['created'] + sync_stats['updated']
                    if sync_stats['created'] > 0 and post.analysis_status == Post.AnalysisStatus.DONE:
                        post.analysis_status = Post.AnalysisStatus.PENDING
                        post.save(update_fields=['analysis_status', 'updated_at'])

                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1

        return stats

    @classmethod
    def get_pending_for_nlp(cls, *, limit: int = 50) -> list:
        cls._reset_stale_processing()
        router = CollectionModelRouter()
        Post = router.post_model
        return list(
            Post.objects.filter(
                analysis_status=Post.AnalysisStatus.PENDING,
            ).order_by('scraped_at')[:limit]
        )

    @classmethod
    def _reset_stale_processing(cls, minutes: int = 15) -> int:
        """Remet en attente les posts bloqués en « processing » trop longtemps."""
        from datetime import timedelta

        router = CollectionModelRouter()
        Post = router.post_model
        cutoff = timezone.now() - timedelta(minutes=minutes)
        return Post.objects.filter(
            analysis_status=Post.AnalysisStatus.PROCESSING,
            updated_at__lt=cutoff,
        ).update(analysis_status=Post.AnalysisStatus.PENDING)

    @classmethod
    def mark_processing(cls, post_ids: list[int]) -> int:
        router = CollectionModelRouter()
        Post = router.post_model
        return Post.objects.filter(
            pk__in=post_ids,
            analysis_status=Post.AnalysisStatus.PENDING,
        ).update(analysis_status=Post.AnalysisStatus.PROCESSING)

    @classmethod
    def apply_analysis_results(cls, results: list[dict]) -> dict[str, int]:
        """
        Applique les résultats NLP renvoyés par la machine locale.

        Chaque item : {id, category?, sentiment?, keywords?, status?}
        """
        stats = {'updated': 0, 'not_found': 0, 'invalid': 0}
        router = CollectionModelRouter()
        Post = router.post_model

        for item in results:
            post_id = item.get('id')
            if not post_id:
                stats['invalid'] += 1
                continue

            try:
                post = Post.objects.get(pk=post_id)
            except Post.DoesNotExist:
                stats['not_found'] += 1
                continue

            status = item.get('status', Post.AnalysisStatus.DONE)
            if status not in Post.AnalysisStatus.values:
                status = Post.AnalysisStatus.DONE

            post.analysis_status = status
            post.category = str(item.get('category', ''))[:80]
            post.sentiment = str(item.get('sentiment', ''))[:20]
            post.keywords = item.get('keywords') or []
            post.analyzed_at = timezone.now()
            post.save(
                update_fields=[
                    'analysis_status', 'category', 'sentiment',
                    'keywords', 'analyzed_at', 'updated_at',
                ]
            )
            stats['updated'] += 1

        return stats

    @staticmethod
    def _parse_published_at(value: str):
        if not value:
            return None
        return parse_datetime(value)

    @classmethod
    def touch_target(cls, target: SocialScrapeTarget) -> None:
        if CollectionModelRouter().is_test:
            return
        target.last_scraped_at = timezone.now()
        target.save(update_fields=['last_scraped_at'])

    @classmethod
    def get_overview_stats(cls) -> dict[str, int]:
        router = CollectionModelRouter()
        Post = router.post_model
        return {
            'total': Post.objects.count(),
            'pending': Post.objects.filter(
                analysis_status=Post.AnalysisStatus.PENDING,
            ).count(),
            'analyzed': Post.objects.filter(
                analysis_status=Post.AnalysisStatus.DONE,
            ).count(),
        }
