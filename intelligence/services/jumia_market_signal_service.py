"""
Agrégation signaux marché Jumia — prix moyen, ruptures, failles, boost Top10.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.utils import timezone

from intelligence.models.jumia_product import JumiaProduct
from intelligence.models.product_market_signal import ProductMarketSignal
from intelligence.nlp_taxonomy import PRODUCT_CATALOG
from intelligence.services.collection_model_router import CollectionModelRouter

logger = logging.getLogger(__name__)

WEIGHT_STOCKOUT = 18.0
WEIGHT_DEMAND_RATINGS = 0.04
WEIGHT_NEG_RATIO = 8.0
WEIGHT_DISCOUNT = 0.05
MIN_RATINGS_FOR_CRITICAL = 20
MIN_SKUS_FOR_CRITICAL = 2


class JumiaMarketSignalService:
    """Calcule ProductMarketSignal à partir des tables Jumia routées."""

    @classmethod
    def refresh_all(cls) -> dict:
        router = CollectionModelRouter()
        Product = router.jumia_product_model
        Review = router.jumia_review_model
        Signal = router.market_signal_model

        products = list(Product.objects.all())
        by_slug: dict[str, list] = defaultdict(list)
        for p in products:
            slug = (p.catalog_product_slug or '').strip()
            if not slug:
                kw = (p.search_keyword or '').strip().lower()
                if kw in PRODUCT_CATALOG:
                    slug = kw
                elif kw:
                    import re as _re
                    slug = _re.sub(r'[^a-z0-9]+', '_', kw).strip('_')[:80]
            if slug:
                by_slug[slug].append(p)

        created = 0
        with transaction.atomic():
            Signal.objects.all().delete()
            rows = []
            for slug, items in by_slug.items():
                signal = cls._build_signal(slug, items, Review)
                rows.append(Signal(**signal))
            if rows:
                Signal.objects.bulk_create(rows)
                created = len(rows)
        logger.info('Signaux marché Jumia : %d slug(s)', created)
        return {'created': created, 'computed_at': timezone.now().isoformat()}

    @classmethod
    def _build_signal(cls, slug: str, items: list, Review) -> dict:
        label = PRODUCT_CATALOG.get(slug, {}).get('label', slug.replace('_', ' ').title())
        prices = [p.price_xof for p in items if p.price_xof is not None]
        discounts = [p.discount_percent for p in items if p.discount_percent is not None]
        out = sum(1 for p in items if p.stock_status == JumiaProduct.StockStatus.OUT_OF_STOCK)
        low = sum(1 for p in items if p.stock_status == JumiaProduct.StockStatus.LOW_STOCK)
        inn = sum(1 for p in items if p.stock_status == JumiaProduct.StockStatus.IN_STOCK)
        total_stocked = out + low + inn
        stockout_rate = (out / total_stocked) if total_stocked else 0.0

        ratings = [p.rating_value for p in items if p.rating_value is not None]
        total_ratings = sum(int(p.rating_count or 0) for p in items)

        product_ids = [p.pk for p in items]
        neg = Review.objects.filter(
            product_id__in=product_ids,
            sentiment='negative',
        ).count()
        analyzed = Review.objects.filter(
            product_id__in=product_ids,
            is_analyzed=True,
        ).count()
        # fallback étoiles 1-2 si pas encore NLP
        if analyzed == 0:
            neg = Review.objects.filter(
                product_id__in=product_ids,
                rating_stars__lte=2,
            ).count()
            analyzed = Review.objects.filter(product_id__in=product_ids).count()
        neg_ratio = (neg / analyzed) if analyzed else 0.0

        fail_counter: Counter = Counter()
        for rev in Review.objects.filter(product_id__in=product_ids).only('failure_tags', 'aspects'):
            for tag in (rev.failure_tags or []):
                fail_counter[str(tag)] += 1
            for aspect, pol in (rev.aspects or {}).items():
                if pol == 'neg':
                    fail_counter[f'{aspect}_neg'] += 1
        top_fails = [t for t, _ in fail_counter.most_common(5)]

        stock_alert = ''
        if (
            stockout_rate >= 0.5
            and total_ratings >= MIN_RATINGS_FOR_CRITICAL
            and (out >= MIN_SKUS_FOR_CRITICAL or (out >= 1 and total_ratings >= 80))
        ):
            stock_alert = ProductMarketSignal.StockAlert.CRITICAL
        elif stockout_rate >= 0.25 and total_ratings >= 8:
            stock_alert = ProductMarketSignal.StockAlert.WATCH

        avg_price = (sum(prices) / len(prices)) if prices else None
        avg_disc = (sum(discounts) / len(discounts)) if discounts else None
        avg_rating = (sum(ratings) / len(ratings)) if ratings else None

        boost = 0.0
        if stock_alert == ProductMarketSignal.StockAlert.CRITICAL:
            boost += WEIGHT_STOCKOUT
        elif stock_alert == ProductMarketSignal.StockAlert.WATCH:
            boost += WEIGHT_STOCKOUT * 0.45
        boost += min(12.0, total_ratings * WEIGHT_DEMAND_RATINGS)
        if neg_ratio >= 0.35:
            boost += WEIGHT_NEG_RATIO * neg_ratio  # opportunité différenciation qualité
        if avg_disc:
            boost += min(4.0, avg_disc * WEIGHT_DISCOUNT)

        evidence_parts = []
        if avg_price is not None:
            evidence_parts.append(f'Prix moy. {int(avg_price):,} FCFA'.replace(',', ' '))
        if stock_alert:
            evidence_parts.append(
                'Rupture critique Jumia' if stock_alert == 'critical' else 'Stock fragile Jumia'
            )
        if top_fails:
            evidence_parts.append('Failles: ' + ', '.join(top_fails[:3]))
        if avg_rating is not None:
            evidence_parts.append(f'Note {avg_rating:.1f}★ ({total_ratings} avis)')

        return {
            'product_slug': slug,
            'product_label': label[:120],
            'avg_price_xof': avg_price,
            'min_price_xof': min(prices) if prices else None,
            'max_price_xof': max(prices) if prices else None,
            'avg_discount_percent': round(avg_disc, 1) if avg_disc is not None else None,
            'price_sample_size': len(prices),
            'out_of_stock_count': out,
            'in_stock_count': inn,
            'low_stock_count': low,
            'stockout_rate': round(stockout_rate, 3),
            'stock_alert': stock_alert,
            'avg_rating': round(avg_rating, 2) if avg_rating is not None else None,
            'total_ratings': total_ratings,
            'review_neg_ratio': round(neg_ratio, 3),
            'top_failure_tags': top_fails,
            'jumia_boost': round(boost, 2),
            'evidence_text': ' · '.join(evidence_parts)[:400],
        }

    @classmethod
    def get_opportunities(cls, *, limit: int = 12) -> list[dict]:
        router = CollectionModelRouter()
        Signal = router.market_signal_model
        Product = router.jumia_product_model
        qs = Signal.objects.exclude(stock_alert='').order_by('-jumia_boost')[:limit]
        if not qs.exists():
            qs = Signal.objects.order_by('-jumia_boost')[:limit]
        out = []
        for s in qs:
            products = cls._products_for_slug(Product, s.product_slug, limit=15)
            out.append({
                'product_slug': s.product_slug,
                'product_label': s.product_label,
                'avg_price_xof': s.avg_price_xof,
                'stock_alert': s.stock_alert,
                'stockout_rate': s.stockout_rate,
                'avg_rating': s.avg_rating,
                'total_ratings': s.total_ratings,
                'review_neg_ratio': s.review_neg_ratio,
                'top_failure_tags': s.top_failure_tags or [],
                'jumia_boost': s.jumia_boost,
                'evidence_text': s.evidence_text,
                'tone': 'orange' if s.stock_alert == 'critical' else ('jaune' if s.stock_alert == 'watch' else 'bleu'),
                'products': products,
                'products_json': json.dumps(products, ensure_ascii=False),
            })
        return out

    @classmethod
    def _products_for_slug(cls, Product, slug: str, *, limit: int = 15) -> list[dict]:
        """Produits Jumia liés à un slug catalogue."""
        slug = (slug or '').strip()
        if not slug:
            return []
        rows = list(
            Product.objects.filter(catalog_product_slug=slug)
            .order_by('-rating_count', '-scraped_at')[:limit]
        )
        if not rows:
            label = slug.replace('_', ' ')
            rows = list(
                Product.objects.filter(search_keyword__icontains=label[:40])
                .order_by('-rating_count', '-scraped_at')[:limit]
            )
        out = []
        for row in rows:
            price = int(row.price_xof) if row.price_xof is not None else None
            out.append({
                'title': (row.name or '')[:120],
                'url': row.product_url or '',
                'price_xof': price,
                'rating_count': int(row.rating_count or 0),
                'rating_value': row.rating_value,
                'stock_status': row.get_stock_status_display() if hasattr(row, 'get_stock_status_display') else '',
            })
        return out

    @classmethod
    def signals_by_slug(cls) -> dict[str, object]:
        router = CollectionModelRouter()
        return {s.product_slug: s for s in router.market_signals_qs()}
