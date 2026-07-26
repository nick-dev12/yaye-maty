"""Tests dédoublonnage Jumia et radar accueil."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from intelligence.models import JumiaProduct, TestJumiaProduct
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.jumia_dedup_service import JumiaDedupService
from intelligence.services.jumia_scraper import JumiaScraper


HOMEPAGE_HTML = """
<html><body>
<article class="prd">
  <a class="core" href="/samsung-galaxy-a07-SN123456789.html">
    <div class="name">Samsung GALAXY A07 Noir</div>
    <div class="prc">58900 FCFA</div>
    <div class="_dsct">16%</div>
  </a>
  17 articles restants
</article>
<article class="prd">
  <a class="core" href="/iphone-15-case-ABC999.html">
    <div class="name">Coque iPhone 15</div>
    <div class="prc">3500 FCFA</div>
  </a>
</article>
</body></html>
"""


class JumiaDedupServiceTests(TestCase):
    def test_extract_sku_from_url(self):
        sku = JumiaDedupService.extract_sku_from_url(
            'https://www.jumia.sn/produit-test-SN123456789.html'
        )
        self.assertEqual(sku, 'SN123456789')

    def test_filter_new_cards_skips_known_sku(self):
        cards = [
            {'url': 'https://www.jumia.sn/a-KNOWN001.html', 'name': 'Produit A'},
            {'url': 'https://www.jumia.sn/b-NEW000002.html', 'name': 'Produit B'},
        ]
        known_skus = {'KNOWN001'}
        known_urls: set[str] = set()
        new_cards, skipped = JumiaDedupService.filter_new_cards(
            cards,
            known_skus=known_skus,
            known_urls=known_urls,
            limit=5,
        )
        self.assertEqual(skipped, 1)
        self.assertEqual(len(new_cards), 1)
        self.assertEqual(new_cards[0]['sku'], 'NEW000002')

    def test_load_known_sets_respects_test_context(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestJumiaProduct.objects.create(
                sku='CTX001',
                product_url='https://www.jumia.sn/ctx.html',
                name='Test',
            )
            skus, urls = JumiaDedupService.load_known_sets()
            self.assertIn('CTX001', skus)
            self.assertEqual(JumiaProduct.objects.count(), 0)
        finally:
            reset_collection_context(token)


class JumiaScraperDedupTests(TestCase):
    def test_accessories_category_path_uses_phones(self):
        self.assertEqual(
            JumiaScraper.resolve_category_path('telephone et accessoir'),
            '/telephones-tablettes/',
        )

    def test_search_listing_skips_known_products(self):
        scraper = JumiaScraper(use_playwright_fallback=False)
        known_skus = {'SN123456789'}
        known_urls: set[str] = set()
        with patch.object(scraper, '_get', return_value=HOMEPAGE_HTML):
            cards = scraper.search_listing_urls(
                'iphone',
                max_products=2,
                skip_known=True,
                known_skus=known_skus,
                known_urls=known_urls,
                max_pages=1,
                max_scan_pages=1,
            )
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['sku'], 'ABC999')
        self.assertIn('coque', cards[0]['name'].lower())

    def test_parse_homepage_stock_and_discount(self):
        scraper = JumiaScraper(use_playwright_fallback=False)
        cards = scraper._parse_listing_cards(HOMEPAGE_HTML, source='homepage')
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]['stock_remaining'], 17)
        self.assertEqual(cards[0]['discount_percent'], 16.0)
        self.assertEqual(cards[0]['sku'], 'SN123456789')
