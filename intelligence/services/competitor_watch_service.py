"""
Veille concurrentielle par mot-clé actif — vendeurs Jumia, densité Jiji, prix.

Chaque mot-clé Paramètres est traité comme une unité de veille indépendante :
qui vend, à quel prix, avec quelle intensité, et à quel prix se positionner.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from intelligence.models import JijiListing, JumiaProduct
from intelligence.services.active_keyword_service import ActiveKeywordService

TOP_SELLERS_LIMIT = 5
TOP_REGIONS_LIMIT = 4


class CompetitorWatchService:
    """Construit le panorama concurrentiel par mot-clé pour Import Master."""

    @classmethod
    def get_watch_for_keywords(cls, *, limit: int = 0) -> list[dict]:
        """Un bloc de veille par mot-clé actif (dédupliqué par texte)."""
        seen: set[str] = set()
        blocks: list[dict] = []
        for kw in ActiveKeywordService.list_for_session():
            key = kw.keyword.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            block = cls.build_keyword_watch(kw.keyword.strip())
            if block['has_data']:
                blocks.append(block)
            if limit and len(blocks) >= limit:
                break
        blocks.sort(key=lambda b: b['pressure_index'], reverse=True)
        return blocks

    @classmethod
    def build_keyword_watch(cls, keyword_text: str) -> dict:
        """Panorama concurrence pour un mot-clé : vendeurs, prix, régions."""
        jumia = cls._jumia_landscape(keyword_text)
        jiji = cls._jiji_landscape(keyword_text)
        floor_price = cls._floor_price(jumia, jiji)
        suggested = cls._suggested_price(jumia, jiji)

        pressure_index = jumia['sellers_count'] + round(jiji['listings_count'] / 3)

        return {
            'keyword': keyword_text,
            'has_data': bool(jumia['products_count'] or jiji['listings_count']),
            'jumia': jumia,
            'jiji': jiji,
            'floor_price_xof': floor_price,
            'suggested_price_xof': suggested,
            'pressure_index': pressure_index,
            'pressure_label': cls._pressure_label(pressure_index),
            'pressure_tone': cls._pressure_tone(pressure_index),
        }

    # ------------------------------------------------------------------
    # Paysages marketplace
    # ------------------------------------------------------------------

    @classmethod
    def _jumia_landscape(cls, keyword_text: str) -> dict:
        qs = JumiaProduct.objects.filter(search_keyword__iexact=keyword_text)
        agg = qs.aggregate(
            products_count=Count('id'),
            sellers_count=Count('seller_name', distinct=True),
            price_min=Min('price_xof'),
            price_avg=Avg('price_xof'),
            price_max=Max('price_xof'),
            avg_rating=Avg('rating_value'),
        )
        sellers = list(
            qs.exclude(seller_name='')
            .values('seller_name')
            .annotate(
                products=Count('id'),
                avg_price=Avg('price_xof'),
                avg_rating=Avg('rating_value'),
            )
            .order_by('-products')[:TOP_SELLERS_LIMIT]
        )
        return {
            'products_count': agg['products_count'] or 0,
            'sellers_count': agg['sellers_count'] or 0,
            'price_min': agg['price_min'],
            'price_avg': agg['price_avg'],
            'price_max': agg['price_max'],
            'avg_rating': round(agg['avg_rating'], 1) if agg['avg_rating'] else None,
            'top_sellers': sellers,
        }

    @classmethod
    def _jiji_landscape(cls, keyword_text: str) -> dict:
        qs = JijiListing.objects.filter(search_keyword__iexact=keyword_text)
        agg = qs.aggregate(
            listings_count=Count('id'),
            sellers_count=Count('seller_name', distinct=True),
            price_min=Min('price_xof'),
            price_avg=Avg('price_xof'),
            total_views=Sum('views_count'),
        )
        regions = list(
            qs.exclude(location_region='')
            .values('location_region')
            .annotate(
                listings=Count('id'),
                avg_price=Avg('price_xof'),
                views=Sum('views_count'),
            )
            .order_by('-listings')[:TOP_REGIONS_LIMIT]
        )
        week_ago = timezone.now() - timedelta(days=7)
        new_this_week = qs.filter(scraped_at__gte=week_ago).count()
        return {
            'listings_count': agg['listings_count'] or 0,
            'sellers_count': agg['sellers_count'] or 0,
            'price_min': agg['price_min'],
            'price_avg': agg['price_avg'],
            'total_views': agg['total_views'] or 0,
            'regions': regions,
            'new_this_week': new_this_week,
        }

    # ------------------------------------------------------------------
    # Prix
    # ------------------------------------------------------------------

    @staticmethod
    def _floor_price(jumia: dict, jiji: dict) -> Decimal | None:
        candidates = [p for p in (jumia['price_min'], jiji['price_min']) if p is not None]
        return min(candidates) if candidates else None

    @staticmethod
    def _suggested_price(jumia: dict, jiji: dict) -> Decimal | None:
        """Positionnement : sous le prix moyen Jumia, au-dessus du plancher Jiji."""
        jumia_avg = jumia['price_avg']
        jiji_min = jiji['price_min']
        if jumia_avg:
            suggested = Decimal(jumia_avg) * Decimal('0.95')
            if jiji_min and suggested < jiji_min:
                suggested = (Decimal(jumia_avg) + Decimal(jiji_min)) / 2
            return suggested.quantize(Decimal('1'))
        if jiji['price_avg']:
            return Decimal(jiji['price_avg']).quantize(Decimal('1'))
        return None

    @staticmethod
    def _pressure_label(index: int) -> str:
        if index >= 12:
            return 'Marché saturé'
        if index >= 6:
            return 'Concurrence active'
        if index >= 1:
            return 'Concurrence faible'
        return 'Pas encore de données'

    @staticmethod
    def _pressure_tone(index: int) -> str:
        if index >= 12:
            return 'orange'
        if index >= 6:
            return 'jaune'
        return 'bleu'
