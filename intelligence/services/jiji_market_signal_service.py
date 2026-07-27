"""
Signaux marché Jiji — demande locale, top vendeurs, arbitrage neuf Jumia vs occasion Jiji.
"""

from __future__ import annotations

import json
import logging

from django.db.models import Avg, Count, Max, Min, Sum

from intelligence.services.collection_model_router import CollectionModelRouter

logger = logging.getLogger(__name__)


class JijiMarketSignalService:
    """Agrégats Jiji + hints d'arbitrage vs prix Jumia."""

    @classmethod
    def refresh_arbitrage_hints(cls) -> dict:
        """Calcule des opportunités en mémoire (pas de table dédiée pour l'instant)."""
        opps = cls.get_arbitrage_opportunities(limit=20)
        sellers = cls.get_top_sellers(limit=20)
        logger.info('Jiji arbitrage=%d top_sellers=%d', len(opps), len(sellers))
        return {'arbitrage': len(opps), 'top_sellers': len(sellers)}

    @classmethod
    def get_arbitrage_opportunities(cls, *, limit: int = 12) -> list[dict]:
        """
        Compare prix moyen Jumia (neuf) vs Jiji (souvent occasion) par slug / mot-clé.
        """
        router = CollectionModelRouter()
        Jumia = router.jumia_product_model
        Jiji = router.jiji_listing_model

        jumia_by_slug = {
            row['catalog_product_slug']: row
            for row in Jumia.objects.exclude(catalog_product_slug='')
            .exclude(price_xof__isnull=True)
            .values('catalog_product_slug')
            .annotate(avg_price=Avg('price_xof'), n=Count('id'))
        }
        jiji_agg = (
            Jiji.objects.filter(condition=Jiji.Condition.NEW)
            .exclude(price_xof__isnull=True)
            .values('catalog_product_slug', 'search_keyword')
            .annotate(
                avg_price=Avg('price_xof'),
                min_price=Min('price_xof'),
                n=Count('id'),
                views=Sum('views_count'),
            )
        )

        opportunities = []
        for row in jiji_agg:
            slug = (row['catalog_product_slug'] or '').strip()
            key = slug or (row['search_keyword'] or '').strip()
            if not key:
                continue
            jiji_avg = row['avg_price']
            jumia = jumia_by_slug.get(slug) if slug else None
            jumia_avg = jumia['avg_price'] if jumia else None
            gap_pct = None
            tone = 'bleu'
            label = key
            if jumia_avg and jiji_avg and jumia_avg > 0:
                gap_pct = round(float((jumia_avg - jiji_avg) / jumia_avg * 100), 1)
                if gap_pct >= 35:
                    tone = 'orange'
                elif gap_pct >= 15:
                    tone = 'jaune'
            opportunities.append({
                'product_slug': slug or key,
                'product_label': label,
                'search_keyword': (row['search_keyword'] or '').strip(),
                'jiji_avg_price': jiji_avg,
                'jiji_min_price': row['min_price'],
                'jiji_sample': row['n'],
                'jiji_views': int(row['views'] or 0),
                'jumia_avg_price': jumia_avg,
                'gap_percent': gap_pct,
                'tone': tone,
                'evidence_text': cls._evidence(jiji_avg, jumia_avg, gap_pct, row['n']),
            })

        for opp in opportunities:
            listings = cls._listings_for_key(
                Jiji,
                slug=opp['product_slug'] if opp['product_slug'] != opp['product_label'] else '',
                keyword=opp.get('search_keyword') or opp['product_label'],
                limit=15,
            )
            opp['listings'] = listings
            opp['listings_json'] = json.dumps(listings, ensure_ascii=False)

        opportunities.sort(
            key=lambda o: (
                -(o['gap_percent'] if o['gap_percent'] is not None else -1),
                -o['jiji_views'],
            )
        )
        return opportunities[:limit]

    @classmethod
    def get_top_sellers(cls, *, limit: int = 15) -> list[dict]:
        router = CollectionModelRouter()
        Jiji = router.jiji_listing_model
        rows = (
            Jiji.objects.exclude(seller_name='')
            .values('seller_name')
            .annotate(
                ads=Count('id'),
                views=Sum('views_count'),
                avg_price=Avg('price_xof'),
            )
            .order_by('-ads', '-views')[:limit]
        )
        out = []
        for r in rows:
            sample = Jiji.objects.filter(seller_name=r['seller_name']).order_by('-views_count').first()
            out.append({
                'seller_name': r['seller_name'],
                'ads_count': r['ads'],
                'views': int(r['views'] or 0),
                'avg_price': r['avg_price'],
                'member_since': getattr(sample, 'seller_member_since', '') if sample else '',
                'is_premium': bool(getattr(sample, 'seller_is_premium', False)) if sample else False,
                'is_verified': bool(getattr(sample, 'seller_is_verified', False)) if sample else False,
                'regions': list(
                    Jiji.objects.filter(seller_name=r['seller_name'])
                    .exclude(location_region='')
                    .values_list('location_region', flat=True)
                    .distinct()[:5]
                ),
            })
        return out

    @classmethod
    def get_location_heatmap(cls, *, limit: int = 20) -> list[dict]:
        router = CollectionModelRouter()
        Jiji = router.jiji_listing_model
        rows = (
            Jiji.objects.exclude(location_region='')
            .values('location_region', 'location_area')
            .annotate(ads=Count('id'), views=Sum('views_count'))
            .order_by('-ads', '-views')[:limit]
        )
        return [
            {
                'region': r['location_region'],
                'area': r['location_area'],
                'ads': r['ads'],
                'views': int(r['views'] or 0),
            }
            for r in rows
        ]

    @classmethod
    def get_keyword_demand_ranking(cls, *, limit: int = 12) -> list[dict]:
        """
        Classement demande locale par mot-clé — proxy : somme des vues Jiji.
        """
        router = CollectionModelRouter()
        Jiji = router.jiji_listing_model
        rows = (
            Jiji.objects.exclude(search_keyword='')
            .values('search_keyword')
            .annotate(
                ads=Count('id'),
                views=Sum('views_count'),
                avg_price=Avg('price_xof'),
                max_views=Max('views_count'),
            )
            .order_by('-views', '-ads')[:limit]
        )
        out = []
        for r in rows:
            top = (
                Jiji.objects.filter(search_keyword=r['search_keyword'])
                .order_by('-views_count', '-scraped_at')
                .first()
            )
            listings = cls._listings_for_key(
                Jiji, keyword=r['search_keyword'], limit=12,
            )
            out.append({
                'keyword': r['search_keyword'],
                'ads': r['ads'],
                'total_views': int(r['views'] or 0),
                'avg_price': r['avg_price'],
                'max_views': int(r['max_views'] or 0),
                'top_listing_title': getattr(top, 'title', '')[:80] if top else '',
                'top_listing_views': int(getattr(top, 'views_count', 0) or 0) if top else 0,
                'top_listing_url': getattr(top, 'listing_url', '') if top else '',
                'listings': listings,
                'listings_json': json.dumps(listings, ensure_ascii=False),
            })
        return out

    @classmethod
    def _listings_for_key(
        cls,
        Jiji,
        *,
        slug: str = '',
        keyword: str = '',
        limit: int = 15,
    ) -> list[dict]:
        """Annonces Jiji liées à un slug catalogue ou mot-clé."""
        qs = Jiji.objects.all()
        slug = (slug or '').strip()
        keyword = (keyword or '').strip()
        if slug:
            by_slug = Jiji.objects.filter(catalog_product_slug=slug)
            if by_slug.exists():
                qs = by_slug
            elif keyword:
                qs = Jiji.objects.filter(search_keyword__iexact=keyword)
            else:
                qs = Jiji.objects.filter(search_keyword__icontains=slug.replace('_', ' ')[:40])
        elif keyword:
            qs = Jiji.objects.filter(search_keyword__iexact=keyword)
        else:
            return []

        rows = qs.order_by('-views_count', '-scraped_at')[:limit]
        out = []
        for row in rows:
            price = int(row.price_xof) if row.price_xof is not None else None
            out.append({
                'title': (row.title or '')[:120],
                'url': row.listing_url or '',
                'price_xof': price,
                'views_count': int(row.views_count or 0),
                'condition': row.get_condition_display() if hasattr(row, 'get_condition_display') else '',
                'location': (row.location_area or row.location_region or '')[:80],
            })
        return out

    @staticmethod
    def _evidence(jiji_avg, jumia_avg, gap_pct, n) -> str:
        parts = [f'{n} annonce(s) Jiji']
        if jiji_avg is not None:
            parts.append(f'moy. Jiji {int(jiji_avg):,} FCFA'.replace(',', ' '))
        if jumia_avg is not None:
            parts.append(f'moy. Jumia {int(jumia_avg):,} FCFA'.replace(',', ' '))
        if gap_pct is not None:
            parts.append(f'écart {gap_pct}%')
        return ' · '.join(parts)
