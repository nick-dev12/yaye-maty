"""
Tests Jiji — parsing listings/annonces, isolation persist, arbitrage.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.test import TestCase

from intelligence.models import (
    JijiListing,
    TestJijiListing,
    TestJumiaProduct,
)
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.jiji_collection_service import JijiCollectionService
from intelligence.services.jiji_market_signal_service import JijiMarketSignalService
from intelligence.services.jiji_scraper import ExtractedJijiListing, JijiScraper
from intelligence.services.test_data_purge_service import TestDataPurgeService

FIXTURE_DIR = Path(__file__).resolve().parents[2] / 'scripts' / '_jiji_probe'

LISTING_HTML = """
<html><body>
<a class="b-list-advert-base qa-advert-list-item" href="/rufisque/farm-machinery-equipment/motopompe-honda-ABC123XYZ789.html">
  <div class="qa-advert-title">Motopompe Honda 3CV</div>
  <div class="qa-advert-price">CFA 189,000</div>
  <div class="b-list-advert-base__location">Région de Dakar, Rufisque</div>
</a>
<a class="b-list-advert-base qa-advert-list-item" href="/dakar/electronics/chargeur-usb-ZZZ999.html">
  <div class="qa-advert-title">Chargeur USB</div>
  <div class="qa-advert-price">CFA 2,000</div>
</a>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<h1 class="qa-advert-title">Motopompe Honda 3CV irrigation</h1>
<div class="qa-advert-price-view-value">CFA 189,000</div>
<div class="qa-advert-price-view-type">Prix fixe</div>
<div class="b-advert-info-statistics--region">Région de Dakar, Rufisque, il y a 2 heures 234 vus</div>
<div class="b-seller-block__name">AgriShop Local</div>
<div class="b-seller-badge">2+ ans sur Jiji</div>
<div class="b-seller-block__info__stat">Répond en une heure</div>
<div class="b-advert-attribute h-pb-5">
  <div class="b-advert-attribute__value">Neuf</div>
  <div class="b-advert-attribute__key">État</div>
</div>
<div class="qa-advert-description">Pompe irrigation agricole occasion rare mais ici neuf.</div>
</body></html>
"""


class JijiScraperParseTests(TestCase):
    def test_parse_listing_cards_and_filter(self):
        scraper = JijiScraper(use_playwright=False)
        cards = scraper._parse_listing_cards(LISTING_HTML)
        self.assertEqual(len(cards), 2)
        filtered = scraper._filter_cards_by_keyword(cards, 'motopompe')
        self.assertEqual(len(filtered), 1)
        self.assertIn('Motopompe', filtered[0]['title'])

    def test_parse_detail_condition_views_seller(self):
        scraper = JijiScraper(use_playwright=False)
        url = 'https://jiji.sn/rufisque/farm-machinery-equipment/motopompe-honda-ABC123XYZ789.html'
        extracted = scraper._parse_listing_page(DETAIL_HTML, url)
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted.listing_id, 'ABC123XYZ789')
        self.assertEqual(extracted.price_xof, Decimal('189000'))
        self.assertFalse(extracted.is_negotiable)
        self.assertEqual(extracted.condition, JijiListing.Condition.NEW)
        self.assertEqual(extracted.views_count, 234)
        self.assertEqual(extracted.seller_name, 'AgriShop Local')
        self.assertEqual(extracted.location_area, 'Rufisque')

    def test_category_path_farm(self):
        self.assertEqual(
            JijiScraper.resolve_category_path('motopompe'),
            '/farm-machinery-equipment',
        )

    def test_fixture_html_if_present(self):
        path = FIXTURE_DIR / 'cat_farm-machinery-equipment.html'
        if not path.exists():
            self.skipTest('Fixture Jiji absente')
        scraper = JijiScraper(use_playwright=False)
        cards = scraper._parse_listing_cards(path.read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(cards), 5)


class JijiPersistAndArbitrageTests(TestCase):
    def test_persist_isolation_and_snapshot(self):
        extracted = ExtractedJijiListing(
            listing_id='ISOJIJI01',
            listing_url='https://jiji.sn/x.html',
            title='Motopompe test',
            price_xof=Decimal('80000'),
            condition=JijiListing.Condition.USED,
            search_keyword='motopompe',
            catalog_product_slug='motopompe',
            views_count=50,
        )
        token = set_collection_context(CollectionRunContext.test())
        try:
            created, updated, snaps = JijiCollectionService._persist_safe(extracted)
            self.assertEqual(created, 1)
            self.assertEqual(snaps, 1)
            self.assertEqual(TestJijiListing.objects.count(), 1)
            self.assertEqual(JijiListing.objects.count(), 0)
        finally:
            reset_collection_context(token)

    def test_arbitrage_vs_jumia(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestDataPurgeService.purge_all()
            TestJumiaProduct.objects.create(
                sku='JUM1',
                product_url='https://www.jumia.sn/a.html',
                name='Motopompe neuf',
                catalog_product_slug='motopompe',
                price_xof=Decimal('150000'),
            )
            TestJijiListing.objects.create(
                listing_id='JIJ1',
                listing_url='https://jiji.sn/a.html',
                title='Motopompe neuf',
                catalog_product_slug='motopompe',
                search_keyword='motopompe',
                price_xof=Decimal('80000'),
                condition=JijiListing.Condition.NEW,
                views_count=120,
            )
            opps = JijiMarketSignalService.get_arbitrage_opportunities(limit=5)
            self.assertTrue(opps)
            self.assertEqual(opps[0]['product_slug'], 'motopompe')
            self.assertIsNotNone(opps[0]['gap_percent'])
            self.assertGreater(opps[0]['gap_percent'], 30)
        finally:
            reset_collection_context(token)

    def test_listing_limit_uses_max_videos(self):
        class _Kw:
            max_videos = 12

        self.assertEqual(
            JijiCollectionService._listing_limit_for_keyword(_Kw(), session_cap=5),
            5,
        )
        self.assertEqual(
            JijiCollectionService._listing_limit_for_keyword(_Kw(), session_cap=0),
            12,
        )
