"""Tests veille concurrentielle — vendeurs Jumia, densité Jiji, prix conseillé."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from intelligence.models import JijiListing, JumiaProduct, MarketSearchKeyword
from intelligence.services.competitor_watch_service import CompetitorWatchService


class CompetitorWatchTests(TestCase):

    def setUp(self):
        MarketSearchKeyword.objects.create(
            keyword='ventilateur',
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
        )
        for i, (seller, price) in enumerate([
            ('CoolAir', '20000'),
            ('CoolAir', '30000'),
            ('VentPro', '25000'),
        ]):
            JumiaProduct.objects.create(
                sku=f'SKU-VENT-{i}',
                product_url=f'https://www.jumia.sn/vent-{i}.html',
                name=f'Ventilateur {i}',
                seller_name=seller,
                price_xof=Decimal(price),
                rating_value=4.0,
                search_keyword='ventilateur',
            )
        for i in range(4):
            JijiListing.objects.create(
                listing_id=f'jiji-vent-{i}',
                listing_url=f'https://jiji.sn/vent-{i}',
                title=f'Ventilateur occasion {i}',
                price_xof=Decimal('12000'),
                condition=JijiListing.Condition.USED,
                location_region='Dakar',
                search_keyword='ventilateur',
                views_count=50,
            )

    def test_build_keyword_watch_aggregates_market(self):
        block = CompetitorWatchService.build_keyword_watch('ventilateur')

        self.assertTrue(block['has_data'])
        self.assertEqual(block['jumia']['products_count'], 3)
        self.assertEqual(block['jumia']['sellers_count'], 2)
        self.assertEqual(block['jiji']['listings_count'], 4)
        self.assertEqual(block['jiji']['regions'][0]['location_region'], 'Dakar')
        # Plancher = min Jiji (12 000) < min Jumia (20 000)
        self.assertEqual(block['floor_price_xof'], Decimal('12000'))
        # Conseillé : 95% du prix moyen Jumia (25 000) = 23 750
        self.assertEqual(block['suggested_price_xof'], Decimal('23750'))
        self.assertIn(block['pressure_tone'], ('orange', 'jaune', 'bleu'))

    def test_top_sellers_sorted_by_product_count(self):
        block = CompetitorWatchService.build_keyword_watch('ventilateur')
        sellers = block['jumia']['top_sellers']
        self.assertEqual(sellers[0]['seller_name'], 'CoolAir')
        self.assertEqual(sellers[0]['products'], 2)

    def test_get_watch_for_keywords_skips_keywords_without_data(self):
        MarketSearchKeyword.objects.create(
            keyword='mot cle sans donnees',
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
        )
        blocks = CompetitorWatchService.get_watch_for_keywords()
        keywords = [b['keyword'] for b in blocks]
        self.assertIn('ventilateur', keywords)
        self.assertNotIn('mot cle sans donnees', keywords)

    def test_no_data_keyword_returns_neutral_block(self):
        block = CompetitorWatchService.build_keyword_watch('inexistant')
        self.assertFalse(block['has_data'])
        self.assertIsNone(block['floor_price_xof'])
        self.assertEqual(block['pressure_label'], 'Pas encore de données')
