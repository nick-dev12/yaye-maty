"""
Agrégation Top 10 produits à sourcer — NLP hybride + engagement + Google Trends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from intelligence.models import DiscoveredQuery
from intelligence.nlp_taxonomy import PRODUCT_CATALOG
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.market_data_window_service import MarketDataWindowService
from intelligence.services.product_extraction_service import ProductExtractionService

WEIGHT_PURCHASE = 10.0
WEIGHT_INFO = 5.0
WEIGHT_VIEWS = 0.01
WEIGHT_TRENDS_RISING = 15.0
WEIGHT_TRENDS_TOP = 8.0
DEFAULT_WINDOW_DAYS = 7
TOP_LIMIT = 10


@dataclass
class ProductAggregate:
    slug: str
    label: str
    category: str
    purchase_count: int
    info_count: int
    total_views: int
    related_posts: int
    trends_boost: float
    raw_score: float
    jumia_boost: float = 0.0
    avg_market_price_xof: object = None
    stock_alert: str = ''
    jumia_evidence: str = ''


class PurchaseRecommendationService:
    """Calcule et persiste le Top 10 des produits à approvisionner."""

    @classmethod
    def get_top_for_display(cls, *, limit: int = TOP_LIMIT, since=None, until=None) -> list[dict]:
        """Retourne le Top 10 stocké pour l'UI Intelligence."""
        router = CollectionModelRouter()
        Recommendation = router.recommendation_model
        qs = MarketDataWindowService.filter_recommendations(
            Recommendation.objects.all(),
            since=since,
            until=until,
        ).order_by('rank')
        if since is not None and not router.is_test and not qs.exists():
            qs = Recommendation.objects.order_by('rank')
        rows = qs[:limit]
        return [
            {
                'rank': row.rank,
                'product_name': row.product_name,
                'product_slug': row.product_slug,
                'category': row.category,
                'score': row.score_normalized,
                'score_raw': round(row.score, 1),
                'purchase_intent_count': row.purchase_intent_count,
                'info_intent_count': row.info_intent_count,
                'total_views': row.total_views,
                'trends_boost': row.trends_boost,
                'related_posts': row.related_posts,
                'evidence_text': row.evidence_text,
                'why_here': cls._why_here_for_row(row),
                'avg_market_price_xof': row.avg_market_price_xof,
                'stock_alert': getattr(row, 'stock_alert', '') or '',
                'jumia_boost': getattr(row, 'jumia_boost', 0) or 0,
                'jumia_evidence': getattr(row, 'jumia_evidence', '') or '',
                'tone': cls._rank_tone(row.rank),
                'is_hot': row.rank <= 3 or (getattr(row, 'stock_alert', '') == 'critical'),
                'computed_at': row.computed_at,
            }
            for row in rows
        ]

    @classmethod
    def refresh_top_recommendations(
        cls,
        *,
        window_days: int = DEFAULT_WINDOW_DAYS,
        limit: int = TOP_LIMIT,
    ) -> dict:
        """Recalcule et remplace le Top 10 en base (prod ou test selon contexte)."""
        router = CollectionModelRouter()
        Recommendation = router.recommendation_model
        since = timezone.now() - timedelta(days=window_days)
        aggregates = cls._build_aggregates(since, router=router)

        if not aggregates:
            deleted, _ = Recommendation.objects.all().delete()
            return {'created': 0, 'deleted': deleted, 'window_days': window_days}

        max_score = max(item.raw_score for item in aggregates) or 1.0
        top_items = aggregates[:limit]

        with transaction.atomic():
            Recommendation.objects.all().delete()
            created = []
            for rank, item in enumerate(top_items, start=1):
                normalized = min(100, max(5, int(round(item.raw_score / max_score * 100))))
                created.append(
                    Recommendation(
                        rank=rank,
                        product_slug=item.slug,
                        product_name=item.label,
                        category=item.category,
                        score=item.raw_score,
                        score_normalized=normalized,
                        purchase_intent_count=item.purchase_count,
                        info_intent_count=item.info_count,
                        total_views=item.total_views,
                        trends_boost=item.trends_boost,
                        related_posts=item.related_posts,
                        evidence_text=cls._build_evidence(item, window_days),
                        avg_market_price_xof=item.avg_market_price_xof,
                        stock_alert=item.stock_alert or '',
                        jumia_boost=item.jumia_boost or 0,
                        jumia_evidence=item.jumia_evidence or '',
                    )
                )
            Recommendation.objects.bulk_create(created)

        return {
            'created': len(created),
            'deleted': 0,
            'window_days': window_days,
            'top_product': top_items[0].label if top_items else '',
        }

    @classmethod
    def _build_aggregates(cls, since, *, router: CollectionModelRouter) -> list[ProductAggregate]:
        Post = router.post_model
        Comment = router.comment_model
        slug_data: dict[str, dict] = {}

        def ensure(slug: str, label: str = '', category: str = '') -> dict:
            if slug not in slug_data:
                meta = PRODUCT_CATALOG.get(slug, {})
                slug_data[slug] = {
                    'label': label or meta.get('label') or ProductExtractionService.get_label(slug),
                    'category': category or meta.get('category', ''),
                    'purchase': 0,
                    'info': 0,
                    'views': 0,
                    'post_ids': set(),
                }
            return slug_data[slug]

        comments_qs = Comment.objects.filter(
            is_analyzed=True,
        ).exclude(extracted_product_slug='').select_related('post')
        if not router.is_test:
            comments_qs = comments_qs.filter(analyzed_at__gte=since)

        for comment in comments_qs:
            bucket = ensure(
                comment.extracted_product_slug,
                comment.extracted_product,
            )
            if comment.intent == Comment.Intent.PURCHASE:
                bucket['purchase'] += 1
            elif comment.intent == Comment.Intent.INFO:
                bucket['info'] += 1
            bucket['post_ids'].add(comment.post_id)

        posts_qs = Post.objects.exclude(extracted_product_slug='')
        if not router.is_test:
            posts_qs = posts_qs.filter(scraped_at__gte=since)

        for post in posts_qs:
            bucket = ensure(
                post.extracted_product_slug,
                post.extracted_product,
                post.category,
            )
            bucket['post_ids'].add(post.pk)
            bucket['views'] += post.view_count or 0

        for slug, bucket in slug_data.items():
            post_ids = bucket['post_ids']
            if post_ids:
                extra_views = (
                    Post.objects.filter(pk__in=post_ids)
                    .aggregate(total=Sum('view_count'))['total']
                    or 0
                )
                bucket['views'] = max(bucket['views'], extra_views)

        aggregates: list[ProductAggregate] = []
        jumia_map = cls._jumia_signals_map(router=router)

        # Injecte les slugs Jumia même sans signal social (opportunité marché)
        for slug, signal in jumia_map.items():
            ensure(slug, getattr(signal, 'product_label', '') or '')

        for slug, bucket in slug_data.items():
            trends_boost = cls._trends_boost(slug, router=router)
            jumia = jumia_map.get(slug)
            jumia_boost = float(getattr(jumia, 'jumia_boost', 0) or 0) if jumia else 0.0
            raw_score = (
                bucket['purchase'] * WEIGHT_PURCHASE
                + bucket['info'] * WEIGHT_INFO
                + bucket['views'] * WEIGHT_VIEWS
                + trends_boost
                + jumia_boost
            )
            if raw_score <= 0:
                continue
            aggregates.append(
                ProductAggregate(
                    slug=slug,
                    label=bucket['label'],
                    category=bucket['category'],
                    purchase_count=bucket['purchase'],
                    info_count=bucket['info'],
                    total_views=bucket['views'],
                    related_posts=len(bucket['post_ids']),
                    trends_boost=trends_boost,
                    raw_score=raw_score,
                    jumia_boost=jumia_boost,
                    avg_market_price_xof=getattr(jumia, 'avg_price_xof', None) if jumia else None,
                    stock_alert=getattr(jumia, 'stock_alert', '') if jumia else '',
                    jumia_evidence=getattr(jumia, 'evidence_text', '') if jumia else '',
                )
            )

        aggregates.sort(key=lambda item: item.raw_score, reverse=True)
        return aggregates

    @classmethod
    def _jumia_signals_map(cls, *, router: CollectionModelRouter) -> dict:
        try:
            return {s.product_slug: s for s in router.market_signals_qs()}
        except Exception:
            return {}

    @classmethod
    def _trends_boost(cls, product_slug: str, *, router: CollectionModelRouter | None = None) -> float:
        router = router or CollectionModelRouter()
        Discovered = router.discovered_model
        meta = PRODUCT_CATALOG.get(product_slug, {})
        keywords = meta.get('keywords', ())
        if not keywords:
            return 0.0

        boost = 0.0
        queries = Discovered.objects.all()
        for query in queries:
            normalized = ProductExtractionService._normalize(query.query)
            if not any(kw in normalized for kw in keywords):
                continue
            if query.query_type == Discovered.QueryType.RISING:
                boost += WEIGHT_TRENDS_RISING
            else:
                boost += WEIGHT_TRENDS_TOP
        return boost

    @staticmethod
    def _build_evidence(item: ProductAggregate, window_days: int) -> str:
        parts = []
        if item.purchase_count:
            parts.append(
                f"{item.purchase_count} demande(s) d'achat sur {window_days} j"
            )
        if item.info_count:
            parts.append(f"{item.info_count} question(s) prix/info")
        if item.total_views:
            parts.append(f"{item.total_views:,}".replace(',', '\u202f') + ' vues réseaux')
        if item.trends_boost >= WEIGHT_TRENDS_RISING:
            parts.append('signal Google Trends en hausse')
        elif item.trends_boost > 0:
            parts.append('présent dans les recherches Google Trends')
        if item.avg_market_price_xof is not None:
            parts.append(
                f'Prix moy. marché {int(item.avg_market_price_xof):,} FCFA'.replace(',', ' ')
            )
        if item.stock_alert == 'critical':
            parts.append('opportunité rupture Jumia')
        elif item.stock_alert == 'watch':
            parts.append('stock Jumia fragile')
        if item.jumia_evidence and item.jumia_evidence not in ' · '.join(parts):
            # Ajoute failles si présentes
            if 'Failles:' in item.jumia_evidence:
                fail_part = item.jumia_evidence.split('Failles:')[-1].strip()
                if fail_part:
                    parts.append('Failles Jumia: ' + fail_part.split('·')[0].strip())
        return ' · '.join(parts) if parts else 'Signal faible — surveiller'

    @staticmethod
    def _why_here_for_row(row) -> str:
        """Phrase simple pour l'UI Top 10 (non-initiés)."""
        parts = []
        purchase = int(getattr(row, 'purchase_intent_count', 0) or 0)
        info = int(getattr(row, 'info_intent_count', 0) or 0)
        views = int(getattr(row, 'total_views', 0) or 0)
        if purchase:
            parts.append(
                f'{purchase} commentaire{"s" if purchase > 1 else ""} « je veux acheter »'
            )
        if info:
            parts.append(f'{info} demande{"s" if info > 1 else ""} d\'information')
        if views:
            parts.append(f'{views:,} vues sur les réseaux'.replace(',', ' '))
        if getattr(row, 'trends_boost', 0):
            parts.append('recherche Google en hausse')
        if getattr(row, 'stock_alert', '') == 'critical':
            parts.append('rupture de stock sur Jumia')
        return ' · '.join(parts) if parts else (getattr(row, 'evidence_text', '') or '')

    @staticmethod
    def _rank_tone(rank: int) -> str:
        if rank == 1:
            return 'orange'
        if rank <= 3:
            return 'jaune'
        if rank <= 6:
            return 'bleu'
        return 'gris'

    @classmethod
    def backfill_extracted_products(cls, *, limit: int = 500) -> dict:
        """Rétro-extraction produit sur commentaires/posts déjà analysés."""
        router = CollectionModelRouter()
        Post = router.post_model
        Comment = router.comment_model
        updated_comments = 0
        updated_posts = 0

        comments = Comment.objects.filter(
            is_analyzed=True,
            extracted_product_slug='',
        ).filter(
            Q(intent=Comment.Intent.PURCHASE) | Q(intent=Comment.Intent.INFO),
        ).select_related('post')[:limit]

        for comment in comments:
            extracted = ProductExtractionService.extract_for_comment(
                comment.text,
                comment.intent,
                context=f'{comment.post.content} {" ".join(comment.post.hashtags or [])}',
            )
            if not extracted and comment.post.extracted_product_slug:
                if comment.intent in (Comment.Intent.PURCHASE, Comment.Intent.INFO):
                    comment.extracted_product = comment.post.extracted_product
                    comment.extracted_product_slug = comment.post.extracted_product_slug
                    comment.save(update_fields=['extracted_product', 'extracted_product_slug'])
                    updated_comments += 1
                continue
            if not extracted:
                continue
            comment.extracted_product = extracted['label']
            comment.extracted_product_slug = extracted['slug']
            comment.save(update_fields=['extracted_product', 'extracted_product_slug'])
            updated_comments += 1

        posts = Post.objects.filter(extracted_product_slug='')[:limit]
        for post in posts:
            extracted = ProductExtractionService.extract_for_post(post.content, post.hashtags)
            if not extracted:
                continue
            post.extracted_product = extracted['label']
            post.extracted_product_slug = extracted['slug']
            if not post.category:
                post.category = extracted.get('category', '')
            post.save(update_fields=['extracted_product', 'extracted_product_slug', 'category', 'updated_at'])
            updated_posts += 1

        return {'comments': updated_comments, 'posts': updated_posts}
