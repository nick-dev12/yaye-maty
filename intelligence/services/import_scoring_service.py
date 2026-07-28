"""
Moteur de scoring Import Master — produits gagnants par mot-clé actif.

Chaque mot-clé actif Paramètres est une unité d'opportunité indépendante
(règle « mots-clés = source de vérité »). Quatre sous-scores 0-100 sont
combinés en un score global pondéré, puis des règles explicites produisent
la décision Acheter / Surveiller / Éviter avec ses raisons lisibles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone
from django.utils.text import slugify

from intelligence.models import (
    DiscoveredQuery,
    ImportOpportunity,
    JijiListing,
    JumiaProduct,
    MarketSearchKeyword,
    SocialComment,
    SocialPost,
    TrendRecord,
)
from intelligence.services.active_keyword_service import ActiveKeywordService

# Pondérations du score global (somme = 1.0)
WEIGHT_DEMAND = 0.35
WEIGHT_TREND = 0.25
WEIGHT_COMPETITION = 0.20
WEIGHT_PRICE = 0.20

# Seuils de décision
BUY_MIN_SCORE = 70
BUY_MIN_DEMAND = 60
AVOID_MAX_SCORE = 40
SATURATION_COMPETITION_MAX = 30

DEFAULT_WINDOW_DAYS = 7


@dataclass
class KeywordSignals:
    """Signaux bruts collectés pour un mot-clé avant scoring."""

    keyword_text: str
    purchase_count: int = 0
    info_count: int = 0
    total_views: int = 0
    posts_recent: int = 0
    posts_previous: int = 0
    trend_avg_recent: float = 0.0
    trend_slope: float = 0.0
    trend_rising_matches: int = 0
    trend_top_matches: int = 0
    jumia_sellers: int = 0
    jumia_products: int = 0
    jumia_out_of_stock: int = 0
    jumia_low_stock: int = 0
    jiji_listings: int = 0
    jiji_views: int = 0
    jumia_price_min: Decimal | None = None
    jumia_price_avg: Decimal | None = None
    jumia_price_max: Decimal | None = None
    jiji_price_min: Decimal | None = None
    jiji_price_avg: Decimal | None = None
    reasons: list[str] = field(default_factory=list)


class ImportScoringService:
    """Calcule et persiste les opportunités d'importation du jour."""

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @classmethod
    def refresh_opportunities(cls, *, window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
        """Recalcule les opportunités du jour pour tous les mots-clés actifs."""
        keywords = cls._unique_active_keywords()
        snapshot_date = timezone.localdate()
        rows: list[ImportOpportunity] = []

        for kw in keywords:
            signals = cls._collect_signals(kw, window_days=window_days)
            scores = cls.compute_scores(signals)
            decision, reasons = cls.decide(scores, signals)
            prices = cls._market_prices(signals)
            rows.append(
                ImportOpportunity(
                    keyword=kw,
                    keyword_text=kw.keyword.strip(),
                    product_slug=slugify(kw.keyword)[:80],
                    product_name=kw.label or kw.keyword,
                    snapshot_date=snapshot_date,
                    score=scores['score'],
                    demand_score=scores['demand'],
                    trend_score=scores['trend'],
                    competition_score=scores['competition'],
                    price_score=scores['price'],
                    decision=decision,
                    decision_reasons=reasons,
                    market_price_min_xof=prices['min'],
                    market_price_avg_xof=prices['avg'],
                    market_price_max_xof=prices['max'],
                    jumia_sellers=signals.jumia_sellers,
                    jiji_listings_count=signals.jiji_listings,
                    purchase_intent_count=signals.purchase_count,
                    total_views=signals.total_views,
                    stock_alert=cls._stock_alert(signals),
                    suggested_price_xof=cls._suggested_price(signals),
                )
            )

        rows.sort(key=lambda r: r.score, reverse=True)
        for rank, row in enumerate(rows, start=1):
            row.rank = rank

        with transaction.atomic():
            ImportOpportunity.objects.filter(snapshot_date=snapshot_date).delete()
            ImportOpportunity.objects.bulk_create(rows)

        buy = sum(1 for r in rows if r.decision == ImportOpportunity.Decision.BUY)
        avoid = sum(1 for r in rows if r.decision == ImportOpportunity.Decision.AVOID)
        return {
            'created': len(rows),
            'buy': buy,
            'watch': len(rows) - buy - avoid,
            'avoid': avoid,
            'snapshot_date': snapshot_date.isoformat(),
        }

    @classmethod
    def compute_scores(cls, signals: KeywordSignals) -> dict:
        """Retourne les 4 sous-scores + score global (0-100 chacun)."""
        demand = cls._demand_score(signals)
        trend = cls._trend_score(signals)
        competition = cls._competition_score(signals)
        price = cls._price_score(signals)
        score = int(round(
            demand * WEIGHT_DEMAND
            + trend * WEIGHT_TREND
            + competition * WEIGHT_COMPETITION
            + price * WEIGHT_PRICE
        ))
        return {
            'demand': demand,
            'trend': trend,
            'competition': competition,
            'price': price,
            'score': max(0, min(100, score)),
        }

    @classmethod
    def decide(cls, scores: dict, signals: KeywordSignals) -> tuple[str, list[str]]:
        """Applique les règles Acheter / Surveiller / Éviter et trace les raisons."""
        reasons: list[str] = []
        saturated = scores['competition'] < SATURATION_COMPETITION_MAX

        if signals.purchase_count:
            reasons.append(
                f'{signals.purchase_count} commentaire{"s" if signals.purchase_count > 1 else ""}'
                ' « je veux acheter » cette semaine'
            )
        if signals.total_views:
            reasons.append(
                f'{signals.total_views:,} vues sur les réseaux (7 j)'.replace(',', ' ')
            )
        if signals.trend_slope > 0:
            reasons.append('recherche Google en hausse')
        if signals.trend_rising_matches:
            reasons.append(
                f'{signals.trend_rising_matches} requête(s) Google Trends en forte progression'
            )
        stock_alert = cls._stock_alert(signals)
        if stock_alert == 'critical':
            reasons.append(
                f'rupture de stock sur Jumia ({signals.jumia_out_of_stock} produit(s))'
            )
        elif stock_alert == 'watch':
            reasons.append('stock Jumia fragile — fenêtre d\'entrée possible')
        if saturated:
            reasons.append(
                f'marché saturé : {signals.jumia_sellers} vendeur(s) Jumia'
                f' et {signals.jiji_listings} annonce(s) Jiji'
            )
        elif signals.jumia_sellers or signals.jiji_listings:
            reasons.append(
                f'concurrence mesurée : {signals.jumia_sellers} vendeur(s) Jumia,'
                f' {signals.jiji_listings} annonce(s) Jiji'
            )

        if (
            scores['score'] >= BUY_MIN_SCORE
            and scores['demand'] >= BUY_MIN_DEMAND
            and not saturated
        ):
            decision = ImportOpportunity.Decision.BUY
            reasons.insert(0, 'Demande forte et marché accessible — opportunité d\'achat')
        elif scores['score'] < AVOID_MAX_SCORE or (saturated and scores['demand'] < 40):
            decision = ImportOpportunity.Decision.AVOID
            if scores['demand'] < 40:
                reasons.append('demande locale trop faible sur la fenêtre observée')
        else:
            decision = ImportOpportunity.Decision.WATCH
            reasons.append('signaux encourageants mais incomplets — à surveiller')

        return decision, reasons

    # ------------------------------------------------------------------
    # Sous-scores
    # ------------------------------------------------------------------

    @staticmethod
    def _demand_score(s: KeywordSignals) -> int:
        """Intentions d'achat + vues réseaux + momentum publications (0-100)."""
        purchase_pts = min(55, s.purchase_count * 12)
        info_pts = min(15, s.info_count * 3)
        views_pts = min(20, s.total_views // 2000)
        momentum_pts = 0
        if s.posts_recent > s.posts_previous and s.posts_recent > 0:
            momentum_pts = 10
        elif s.posts_recent > 0:
            momentum_pts = 5
        return min(100, purchase_pts + info_pts + views_pts + momentum_pts)

    @staticmethod
    def _trend_score(s: KeywordSignals) -> int:
        """Niveau + pente Google Trends + requêtes rising associées (0-100)."""
        base_pts = min(50, int(s.trend_avg_recent * 0.5))
        slope_pts = max(0, min(25, int(round(s.trend_slope))))
        rising_pts = min(15, s.trend_rising_matches * 8)
        top_pts = min(10, s.trend_top_matches * 4)
        return min(100, base_pts + slope_pts + rising_pts + top_pts)

    @staticmethod
    def _competition_score(s: KeywordSignals) -> int:
        """Score inversé : peu de concurrents = opportunité (0-100)."""
        has_market_data = bool(s.jumia_products or s.jiji_listings)
        if not has_market_data:
            return 50  # neutre — pas encore de données marché

        density = s.jumia_sellers + s.jiji_listings / 3.0
        score = 100 - int(round(density * 6))

        # Une rupture chez les concurrents est une porte d'entrée
        if s.jumia_out_of_stock >= 2:
            score += 15
        elif s.jumia_out_of_stock or s.jumia_low_stock:
            score += 8

        return max(0, min(100, score))

    @staticmethod
    def _price_score(s: KeywordSignals) -> int:
        """Marge de positionnement prix entre plancher local et prix catalogue (0-100)."""
        jumia_avg = float(s.jumia_price_avg) if s.jumia_price_avg else None
        jiji_min = float(s.jiji_price_min) if s.jiji_price_min else None

        if jumia_avg and jiji_min and jumia_avg > 0:
            gap = (jumia_avg - jiji_min) / jumia_avg
            return max(0, min(100, int(round(50 + gap * 100))))

        if jumia_avg and s.jumia_price_min and s.jumia_price_max:
            spread = float(s.jumia_price_max) - float(s.jumia_price_min)
            dispersion = spread / jumia_avg if jumia_avg else 0
            return max(0, min(100, int(round(45 + dispersion * 40))))

        if jumia_avg or jiji_min:
            return 50
        return 40  # aucune donnée prix — pénalité légère

    # ------------------------------------------------------------------
    # Collecte des signaux par mot-clé
    # ------------------------------------------------------------------

    @classmethod
    def _collect_signals(
        cls,
        kw: MarketSearchKeyword,
        *,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> KeywordSignals:
        signals = KeywordSignals(keyword_text=kw.keyword.strip())
        now = timezone.now()
        since = now - timedelta(days=window_days)
        previous_since = since - timedelta(days=window_days)

        cls._fill_social_signals(signals, since=since, previous_since=previous_since)
        cls._fill_trend_signals(signals, window_days=window_days)
        cls._fill_marketplace_signals(signals)
        return signals

    @staticmethod
    def _keyword_tokens(keyword_text: str) -> list[str]:
        tokens = [t for t in re.split(r'\W+', keyword_text.lower()) if len(t) >= 3]
        return tokens or [keyword_text.strip().lower()]

    @classmethod
    def _social_posts_q(cls, keyword_text: str) -> Q:
        """Posts dont le contenu contient tous les tokens significatifs du mot-clé."""
        q = Q()
        for token in cls._keyword_tokens(keyword_text):
            q &= Q(content__icontains=token) | Q(extracted_product__icontains=token)
        return q

    @classmethod
    def _fill_social_signals(cls, signals: KeywordSignals, *, since, previous_since) -> None:
        posts_qs = SocialPost.objects.filter(cls._social_posts_q(signals.keyword_text))

        recent = posts_qs.filter(scraped_at__gte=since)
        signals.posts_recent = recent.count()
        signals.posts_previous = posts_qs.filter(
            scraped_at__gte=previous_since,
            scraped_at__lt=since,
        ).count()
        signals.total_views = recent.aggregate(total=Sum('view_count'))['total'] or 0

        post_ids = list(recent.values_list('pk', flat=True))
        if post_ids:
            intents = (
                SocialComment.objects.filter(post_id__in=post_ids, is_analyzed=True)
                .values('intent')
                .annotate(n=Count('id'))
            )
            for row in intents:
                if row['intent'] == SocialComment.Intent.PURCHASE:
                    signals.purchase_count = row['n']
                elif row['intent'] == SocialComment.Intent.INFO:
                    signals.info_count = row['n']

    @classmethod
    def _fill_trend_signals(cls, signals: KeywordSignals, *, window_days: int) -> None:
        keyword_text = signals.keyword_text
        today = timezone.localdate()
        recent_start = today - timedelta(days=window_days)
        previous_start = recent_start - timedelta(days=window_days)

        records = TrendRecord.objects.filter(keyword__iexact=keyword_text)
        if not records.exists():
            first_token = cls._keyword_tokens(keyword_text)[0]
            records = TrendRecord.objects.filter(keyword__icontains=first_token)

        recent_avg = records.filter(date__gte=recent_start).aggregate(
            avg=Avg('score'),
        )['avg'] or 0.0
        previous_avg = records.filter(
            date__gte=previous_start,
            date__lt=recent_start,
        ).aggregate(avg=Avg('score'))['avg'] or 0.0
        signals.trend_avg_recent = float(recent_avg)
        signals.trend_slope = float(recent_avg) - float(previous_avg)

        tokens = cls._keyword_tokens(keyword_text)
        token_q = Q()
        for token in tokens:
            token_q |= Q(query__icontains=token)
        matches = DiscoveredQuery.objects.filter(token_q)
        signals.trend_rising_matches = matches.filter(
            query_type=DiscoveredQuery.QueryType.RISING,
        ).count()
        signals.trend_top_matches = matches.filter(
            query_type=DiscoveredQuery.QueryType.TOP,
        ).count()

    @classmethod
    def _fill_marketplace_signals(cls, signals: KeywordSignals) -> None:
        keyword_text = signals.keyword_text

        jumia_qs = JumiaProduct.objects.filter(search_keyword__iexact=keyword_text)
        jumia_agg = jumia_qs.aggregate(
            products=Count('id'),
            sellers=Count('seller_name', distinct=True),
            out_of_stock=Count('id', filter=Q(stock_status=JumiaProduct.StockStatus.OUT_OF_STOCK)),
            low_stock=Count('id', filter=Q(stock_status=JumiaProduct.StockStatus.LOW_STOCK)),
            price_min=Min('price_xof'),
            price_avg=Avg('price_xof'),
            price_max=Max('price_xof'),
        )
        signals.jumia_products = jumia_agg['products'] or 0
        signals.jumia_sellers = jumia_agg['sellers'] or 0
        signals.jumia_out_of_stock = jumia_agg['out_of_stock'] or 0
        signals.jumia_low_stock = jumia_agg['low_stock'] or 0
        signals.jumia_price_min = jumia_agg['price_min']
        signals.jumia_price_avg = jumia_agg['price_avg']
        signals.jumia_price_max = jumia_agg['price_max']

        jiji_qs = JijiListing.objects.filter(search_keyword__iexact=keyword_text)
        jiji_agg = jiji_qs.aggregate(
            listings=Count('id'),
            views=Sum('views_count'),
            price_min=Min('price_xof'),
            price_avg=Avg('price_xof'),
        )
        signals.jiji_listings = jiji_agg['listings'] or 0
        signals.jiji_views = jiji_agg['views'] or 0
        signals.jiji_price_min = jiji_agg['price_min']
        signals.jiji_price_avg = jiji_agg['price_avg']

    # ------------------------------------------------------------------
    # Helpers persistance
    # ------------------------------------------------------------------

    @staticmethod
    def _unique_active_keywords() -> list[MarketSearchKeyword]:
        """Tous les mots-clés actifs, dédupliqués par texte (toutes plateformes)."""
        seen: set[str] = set()
        unique: list[MarketSearchKeyword] = []
        for kw in ActiveKeywordService.list_for_session():
            key = kw.keyword.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(kw)
        return unique

    @staticmethod
    def _stock_alert(s: KeywordSignals) -> str:
        if s.jumia_out_of_stock >= 2:
            return 'critical'
        if s.jumia_out_of_stock or s.jumia_low_stock:
            return 'watch'
        return ''

    @staticmethod
    def _market_prices(s: KeywordSignals) -> dict:
        """Fusion min/avg/max Jumia + Jiji."""
        mins = [p for p in (s.jumia_price_min, s.jiji_price_min) if p is not None]
        avgs = [p for p in (s.jumia_price_avg, s.jiji_price_avg) if p is not None]
        maxs = [p for p in (s.jumia_price_max,) if p is not None]
        return {
            'min': min(mins) if mins else None,
            'avg': (sum(avgs) / len(avgs)) if avgs else None,
            'max': max(maxs) if maxs else (max(avgs) if avgs else None),
        }

    @staticmethod
    def _suggested_price(s: KeywordSignals) -> Decimal | None:
        """Prix conseillé : sous le prix moyen Jumia, au-dessus du plancher Jiji."""
        jumia_avg = s.jumia_price_avg
        jiji_min = s.jiji_price_min
        if jumia_avg:
            suggested = Decimal(jumia_avg) * Decimal('0.95')
            if jiji_min and suggested < jiji_min:
                suggested = (Decimal(jumia_avg) + Decimal(jiji_min)) / 2
            return suggested.quantize(Decimal('1'))
        if s.jiji_price_avg:
            return Decimal(s.jiji_price_avg).quantize(Decimal('1'))
        return None
