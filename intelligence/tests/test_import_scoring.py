"""Tests du moteur de scoring Import Master — décisions Acheter/Surveiller/Éviter."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from intelligence.models import (
    ImportOpportunity,
    JijiListing,
    JumiaProduct,
    MarketSearchKeyword,
    SocialComment,
    SocialPost,
    TrendRecord,
)
from intelligence.services.import_scoring_service import (
    ImportScoringService,
    KeywordSignals,
)


def _make_keyword(keyword: str, platform=MarketSearchKeyword.Platform.MARKETPLACE):
    return MarketSearchKeyword.objects.create(
        keyword=keyword,
        platform=platform,
    )


class ImportScoringDecisionTests(TestCase):
    """Les règles Acheter / Surveiller / Éviter sur signaux synthétiques."""

    def test_buy_decision_when_demand_high_and_market_open(self):
        signals = KeywordSignals(
            keyword_text='iphone 15',
            purchase_count=8,
            info_count=4,
            total_views=40000,
            posts_recent=6,
            posts_previous=2,
            trend_avg_recent=80,
            trend_slope=20,
            trend_rising_matches=2,
            jumia_products=3,
            jumia_sellers=2,
            jumia_out_of_stock=2,
            jiji_listings=4,
            jumia_price_min=Decimal('300000'),
            jumia_price_avg=Decimal('400000'),
            jumia_price_max=Decimal('500000'),
            jiji_price_min=Decimal('250000'),
            jiji_price_avg=Decimal('320000'),
        )
        scores = ImportScoringService.compute_scores(signals)
        decision, reasons = ImportScoringService.decide(scores, signals)

        self.assertEqual(decision, ImportOpportunity.Decision.BUY)
        self.assertGreaterEqual(scores['score'], 70)
        self.assertGreaterEqual(scores['demand'], 60)
        self.assertTrue(any('je veux acheter' in r for r in reasons))
        self.assertTrue(any('rupture' in r.lower() for r in reasons))

    def test_avoid_decision_when_no_demand(self):
        signals = KeywordSignals(keyword_text='produit inconnu')
        scores = ImportScoringService.compute_scores(signals)
        decision, reasons = ImportScoringService.decide(scores, signals)

        self.assertEqual(decision, ImportOpportunity.Decision.AVOID)
        self.assertLess(scores['score'], 40)
        self.assertTrue(any('demande locale trop faible' in r for r in reasons))

    def test_avoid_decision_when_market_saturated_and_demand_low(self):
        signals = KeywordSignals(
            keyword_text='chargeur telephone',
            purchase_count=1,
            jumia_products=30,
            jumia_sellers=14,
            jiji_listings=40,
            jumia_price_avg=Decimal('5000'),
            jumia_price_min=Decimal('4500'),
            jumia_price_max=Decimal('5500'),
        )
        scores = ImportScoringService.compute_scores(signals)
        decision, reasons = ImportScoringService.decide(scores, signals)

        self.assertEqual(decision, ImportOpportunity.Decision.AVOID)
        self.assertLess(scores['competition'], 30)
        self.assertTrue(any('saturé' in r for r in reasons))

    def test_watch_decision_for_mixed_signals(self):
        signals = KeywordSignals(
            keyword_text='ventilateur',
            purchase_count=2,
            total_views=8000,
            posts_recent=3,
            posts_previous=3,
            trend_avg_recent=45,
            trend_slope=5,
            jumia_products=4,
            jumia_sellers=3,
            jiji_listings=6,
            jumia_price_avg=Decimal('25000'),
            jumia_price_min=Decimal('18000'),
            jumia_price_max=Decimal('35000'),
            jiji_price_min=Decimal('15000'),
            jiji_price_avg=Decimal('20000'),
        )
        scores = ImportScoringService.compute_scores(signals)
        decision, reasons = ImportScoringService.decide(scores, signals)

        self.assertEqual(decision, ImportOpportunity.Decision.WATCH)
        self.assertTrue(any('surveiller' in r for r in reasons))

    def test_scores_are_bounded_0_100(self):
        signals = KeywordSignals(
            keyword_text='extreme',
            purchase_count=1000,
            info_count=1000,
            total_views=10_000_000,
            posts_recent=500,
            trend_avg_recent=100,
            trend_slope=100,
            trend_rising_matches=50,
            trend_top_matches=50,
        )
        scores = ImportScoringService.compute_scores(signals)
        for key in ('demand', 'trend', 'competition', 'price', 'score'):
            self.assertGreaterEqual(scores[key], 0, key)
            self.assertLessEqual(scores[key], 100, key)


class ImportScoringRefreshTests(TestCase):
    """refresh_opportunities — pipeline complet mots-clés actifs → BDD."""

    def setUp(self):
        # Neutralise les mots-clés seedés par les migrations
        MarketSearchKeyword.objects.update(is_active=False)

    def test_refresh_creates_one_opportunity_per_active_keyword_multi_sector(self):
        # Multi-secteurs : tech, maison, agricole — aucun biais secteur
        _make_keyword('iphone 15')
        _make_keyword('ventilateur')
        _make_keyword('couveuse 24 oeufs', platform=MarketSearchKeyword.Platform.TIKTOK)
        inactive = _make_keyword('produit inactif')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])

        result = ImportScoringService.refresh_opportunities()

        self.assertEqual(result['created'], 3)
        rows = ImportOpportunity.objects.filter(snapshot_date=timezone.localdate())
        self.assertEqual(rows.count(), 3)
        keywords = set(rows.values_list('keyword_text', flat=True))
        self.assertEqual(keywords, {'iphone 15', 'ventilateur', 'couveuse 24 oeufs'})
        ranks = sorted(rows.values_list('rank', flat=True))
        self.assertEqual(ranks, [1, 2, 3])

    def test_refresh_deduplicates_same_keyword_across_platforms(self):
        _make_keyword('iphone 15', platform=MarketSearchKeyword.Platform.TIKTOK)
        _make_keyword('iphone 15', platform=MarketSearchKeyword.Platform.MARKETPLACE)

        result = ImportScoringService.refresh_opportunities()

        self.assertEqual(result['created'], 1)

    def test_refresh_uses_marketplace_and_social_data(self):
        _make_keyword('couveuse 24 oeufs')

        JumiaProduct.objects.create(
            sku='SKU-COUV-1',
            product_url='https://www.jumia.sn/couveuse-1.html',
            name='Couveuse automatique 24 oeufs',
            seller_name='AgroShop',
            price_xof=Decimal('80000'),
            search_keyword='couveuse 24 oeufs',
            stock_status=JumiaProduct.StockStatus.OUT_OF_STOCK,
        )
        JumiaProduct.objects.create(
            sku='SKU-COUV-2',
            product_url='https://www.jumia.sn/couveuse-2.html',
            name='Couveuse 24 oeufs pro',
            seller_name='FarmTech',
            price_xof=Decimal('95000'),
            search_keyword='couveuse 24 oeufs',
            stock_status=JumiaProduct.StockStatus.OUT_OF_STOCK,
        )
        JijiListing.objects.create(
            listing_id='jiji-couv-1',
            listing_url='https://jiji.sn/annonce-couveuse',
            title='Couveuse 24 oeufs neuve',
            price_xof=Decimal('60000'),
            condition=JijiListing.Condition.NEW,
            search_keyword='couveuse 24 oeufs',
            views_count=120,
        )

        post = SocialPost.objects.create(
            platform=SocialPost.Platform.TIKTOK,
            source_url='https://tiktok.com/@x/video/1',
            content='Couveuse 24 oeufs automatique disponible au Sénégal',
            content_hash=SocialPost.build_content_hash('couveuse 24 oeufs dispo'),
            view_count=25000,
        )
        for i in range(6):
            SocialComment.objects.create(
                post=post,
                text=f'je veux acheter la couveuse {i}',
                text_hash=f'hash-couveuse-{i}',
                intent=SocialComment.Intent.PURCHASE,
                is_analyzed=True,
            )
        TrendRecord.objects.create(
            keyword='couveuse 24 oeufs',
            date=timezone.localdate(),
            score=75,
        )

        result = ImportScoringService.refresh_opportunities()
        self.assertEqual(result['created'], 1)

        opp = ImportOpportunity.objects.get(keyword_text='couveuse 24 oeufs')
        self.assertGreater(opp.demand_score, 50)
        self.assertGreater(opp.trend_score, 0)
        self.assertEqual(opp.jumia_sellers, 2)
        self.assertEqual(opp.jiji_listings_count, 1)
        self.assertEqual(opp.stock_alert, 'critical')
        self.assertEqual(opp.purchase_intent_count, 6)
        self.assertIsNotNone(opp.market_price_min_xof)
        self.assertIsNotNone(opp.suggested_price_xof)
        self.assertTrue(opp.decision_reasons)

    def test_refresh_replaces_previous_snapshot_same_day(self):
        _make_keyword('iphone 15')
        ImportScoringService.refresh_opportunities()
        ImportScoringService.refresh_opportunities()

        self.assertEqual(
            ImportOpportunity.objects.filter(snapshot_date=timezone.localdate()).count(),
            1,
        )
