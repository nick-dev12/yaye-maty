"""
Orchestration NLP hybride — Filtre local (FR/Wolof) puis CamemBERT.
"""

from __future__ import annotations

import logging
from typing import Callable

from django.conf import settings
from django.utils import timezone

from intelligence.scrapers.engagement_utils import compute_demand_score, count_purchase_intents
from intelligence.services.camembert_classifier_service import CamembertClassifierService
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.local_keyword_filter import LocalKeywordFilter
from intelligence.services.product_extraction_service import ProductExtractionService

logger = logging.getLogger(__name__)
ShouldCancelCallback = Callable[[], bool]


class NlpAnalysisService:
    """Analyse hybride des publications et commentaires sociaux."""

    @classmethod
    def sync_comments_from_posts(cls, *, limit: int = 200) -> dict[str, int]:
        """Crée des commentaires structurés à partir du JSON comments des publications."""
        from intelligence.services.social_comment_service import SocialCommentService
        return SocialCommentService.sync_all_from_posts(limit=limit)

    @classmethod
    def analyze_pending_comments(
        cls,
        *,
        limit: int = 100,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict[str, int]:
        """Étape 1 : filtre local — Étape 2 : CamemBERT si nécessaire."""
        router = CollectionModelRouter()
        Comment = router.comment_model
        stats = {'keyword': 0, 'camembert': 0, 'skipped': 0, 'total': 0}

        threshold = getattr(settings, 'NLP_CLASSIFIER', {}).get('CONFIDENCE_THRESHOLD', 0.55)
        comments = list(
            Comment.objects.filter(is_analyzed=False).select_related('post')[:limit]
        )
        affected_post_ids: set[int] = set()

        for comment in comments:
            if should_cancel and should_cancel():
                stats['cancelled'] = 1
                break
            stats['total'] += 1
            affected_post_ids.add(comment.post_id)
            fast = LocalKeywordFilter.classify(comment.text)

            if fast:
                cls._apply_comment_result(comment, fast, Comment=Comment)
                stats['keyword'] += 1
                continue

            try:
                deep = CamembertClassifierService.classify_comment_intent(comment.text)
                if deep['confidence'] < threshold:
                    deep['intent'] = Comment.Intent.OFF_TOPIC
                cls._apply_comment_result(comment, deep, Comment=Comment)
                stats['camembert'] += 1
            except Exception as exc:
                logger.exception('CamemBERT commentaire %s : %s', comment.pk, exc)
                stats['skipped'] += 1

        if affected_post_ids:
            cls._refresh_posts_after_comment_analysis(affected_post_ids, router=router)

        return stats

    @classmethod
    def analyze_pending_posts(
        cls,
        *,
        limit: int = 50,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict[str, int]:
        """Analyse catégorie + sentiment des publications en attente."""
        router = CollectionModelRouter()
        Post = router.post_model
        Comment = router.comment_model
        stats = {'keyword': 0, 'camembert': 0, 'updated': 0, 'skipped': 0}

        threshold = getattr(settings, 'NLP_CLASSIFIER', {}).get('CONFIDENCE_THRESHOLD', 0.55)
        posts = list(
            Post.objects.filter(
                analysis_status=Post.AnalysisStatus.PENDING,
            ).order_by('scraped_at')[:limit]
        )

        for post in posts:
            if should_cancel and should_cancel():
                stats['cancelled'] = 1
                break
            full_text = post.content
            comment_texts = [
                c.text for c in post.social_comments.all()[:20]
            ] or [
                item.get('text', '') if isinstance(item, dict) else str(item)
                for item in (post.comments or [])
            ]
            combined = full_text + ' ' + ' '.join(comment_texts)

            category = 'autre'
            cat_confidence = 0.35
            method = 'camembert'

            fast_cat = LocalKeywordFilter.classify_post_category(combined)
            if fast_cat:
                category, cat_confidence = fast_cat
                method = 'keyword'
                stats['keyword'] += 1
            else:
                try:
                    cat_result = CamembertClassifierService.classify_post_category(combined)
                    category = cat_result['category']
                    cat_confidence = cat_result['confidence']
                    stats['camembert'] += 1
                except Exception as exc:
                    logger.exception('CamemBERT post %s : %s', post.pk, exc)
                    stats['skipped'] += 1
                    continue

            try:
                sentiment_result = CamembertClassifierService.classify_sentiment(combined)
                sentiment = sentiment_result['sentiment']
            except Exception:
                sentiment = 'neutral'

            purchase_intent_count = post.social_comments.filter(
                intent=Comment.Intent.PURCHASE,
            ).count()
            if not purchase_intent_count:
                purchase_intent_count = count_purchase_intents(post.comments or [])

            keywords = cls._extract_keywords(combined, category)

            extracted = ProductExtractionService.extract_for_post(post.content, post.hashtags)
            extracted_product = ''
            extracted_slug = ''
            if extracted:
                extracted_product = extracted['label']
                extracted_slug = extracted['slug']
                if not category or category == 'autre':
                    category = extracted.get('category', category)

            post.analysis_status = Post.AnalysisStatus.DONE
            post.category = category[:80]
            post.sentiment = sentiment
            post.keywords = keywords
            post.extracted_product = extracted_product
            post.extracted_product_slug = extracted_slug
            post.purchase_intent_count = purchase_intent_count
            post.analyzed_at = timezone.now()
            post.save(update_fields=[
                'analysis_status', 'category', 'sentiment', 'keywords',
                'extracted_product', 'extracted_product_slug',
                'purchase_intent_count', 'analyzed_at', 'updated_at',
            ])
            stats['updated'] += 1
            logger.debug('Post %s analysé (%s, conf=%.2f)', post.pk, method, cat_confidence)

        return stats

    @classmethod
    def run_full_pipeline(
        cls,
        *,
        comment_limit: int = 100,
        post_limit: int = 50,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        """Sync → analyses → Top 10, avec arrêt propre entre chaque élément."""
        from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService

        result = {
            'sync': cls.sync_comments_from_posts(limit=max(comment_limit * 3, 500)),
            'comments': cls.analyze_pending_comments(
                limit=comment_limit,
                should_cancel=should_cancel,
            ),
        }
        cancelled = bool(result['comments'].get('cancelled'))
        if not cancelled:
            result['posts'] = cls.analyze_pending_posts(
                limit=post_limit,
                should_cancel=should_cancel,
            )
            cancelled = bool(result['posts'].get('cancelled'))
        else:
            result['posts'] = {'updated': 0, 'cancelled': 1}

        # Toujours reconstruire l'affichage à partir des éléments déjà analysés,
        # même si l'utilisateur a interrompu le reste du lot.
        result['backfill_products'] = PurchaseRecommendationService.backfill_extracted_products(
            limit=max(comment_limit * 2, 200),
        )
        result['top_recommendations'] = PurchaseRecommendationService.refresh_top_recommendations()
        result['cancelled'] = cancelled
        return result

    @classmethod
    def _refresh_posts_after_comment_analysis(
        cls,
        post_ids: set[int],
        *,
        router: CollectionModelRouter | None = None,
    ) -> None:
        """Met à jour purchase_intent_count et demand_score après analyse commentaires."""
        router = router or CollectionModelRouter()
        Post = router.post_model
        posts = Post.objects.filter(pk__in=post_ids)
        for post in posts:
            purchase_intent_count = post.social_comments.filter(
                intent=router.comment_model.Intent.PURCHASE,
            ).count()
            if not purchase_intent_count:
                purchase_intent_count = count_purchase_intents(post.comments or [])

            demand_score = compute_demand_score(
                views=post.view_count,
                likes=post.like_count,
                shares=post.share_count,
                saves=post.save_count,
                comment_count=post.comment_count or post.social_comments.count(),
                purchase_intent_count=purchase_intent_count,
            )
            post.purchase_intent_count = purchase_intent_count
            post.demand_score = demand_score
            post.save(update_fields=[
                'purchase_intent_count', 'demand_score', 'updated_at',
            ])

    @staticmethod
    def _apply_comment_result(comment, result: dict, *, Comment) -> None:
        comment.intent = result['intent']
        comment.confidence_score = result.get('confidence')
        comment.analysis_method = result.get('method', Comment.AnalysisMethod.CAMEMBERT)
        comment.is_analyzed = True
        comment.analyzed_at = timezone.now()

        extracted = ProductExtractionService.extract_for_comment(
            comment.text,
            comment.intent,
            context=f'{comment.post.content} {" ".join(comment.post.hashtags or [])}',
        )
        if extracted:
            comment.extracted_product = extracted['label']
            comment.extracted_product_slug = extracted['slug']
        else:
            comment.extracted_product = ''
            comment.extracted_product_slug = ''

        comment.save(update_fields=[
            'intent', 'confidence_score', 'analysis_method',
            'is_analyzed', 'analyzed_at',
            'extracted_product', 'extracted_product_slug',
        ])

    @staticmethod
    def _extract_keywords(text: str, category: str) -> list[str]:
        from intelligence.nlp_taxonomy import CATEGORY_KEYWORDS
        from intelligence.services.local_keyword_filter import LocalKeywordFilter

        normalized = LocalKeywordFilter._normalize(text)
        found = []
        for kw in CATEGORY_KEYWORDS.get(category, ()):
            if kw in normalized and kw not in found:
                found.append(kw)
        return found[:8]
