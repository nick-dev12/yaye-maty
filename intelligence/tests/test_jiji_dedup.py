"""Tests dédoublonnage Jiji, parsing vues anglais, radar accueil."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from intelligence.models import JijiListing, TestJijiListing
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.jiji_dedup_service import JijiDedupService
from intelligence.services.jiji_market_signal_service import JijiMarketSignalService
from intelligence.services.jiji_scraper import JijiScraper

HOMEPAGE_HTML = """
<html><body>
<section class="b-homepage__trending">
  <a class="qa-advert-list-item" href="/dakar/electronics/iphone-15-pro-AbCdEfGhIjKl.html">
    <div class="qa-advert-title">iPhone 15 Pro Max</div>
    <div class="qa-advert-price">CFA 650,000</div>
    <div class="b-list-advert-base__location">Dakar</div>
  </a>
  <a class="qa-advert-list-item" href="/dakar/phones/samsung-galaxy-KnOwNlIsTiNg1.html">
    <div class="qa-advert-title">Samsung Galaxy A55</div>
    <div class="qa-advert-price">CFA 180,000</div>
  </a>
</section>
</body></html>
"""

DETAIL_VIEWS_EN_HTML = """
<html><body>
<h1 class="qa-advert-title">Pompes immergées Vackson</h1>
<div class="qa-advert-price-view-value">CFA 250,000</div>
<div class="b-advert-card__head-region">
  <div class="b-advert-info-statistics-wrapper">
    <div class="b-advert-info-statistics">20 views</div>
  </div>
</div>
<div class="b-seller-block__name">Vackson Sénégal</div>
</body></html>
"""


class JijiDedupServiceTests(TestCase):
    def test_extract_listing_id_from_url(self):
        listing_id = JijiDedupService.extract_listing_id(
            'https://jiji.sn/en/parcelles-assainies/farm-machinery-equipment/'
            'pompes-immergees-oVAw3CoTCpZGcgmcqtO6KuRT.html?page=1'
        )
        self.assertEqual(listing_id, 'oVAw3CoTCpZGcgmcqtO6KuRT')

    def test_filter_new_cards_skips_known_id(self):
        cards = [
            {'url': 'https://jiji.sn/a-KnOwNlIsTiNg1.html', 'title': 'Samsung'},
            {'url': 'https://jiji.sn/b-NeWlIsTiNg9999.html', 'title': 'Nouveau'},
        ]
        known_ids = {'KnOwNlIsTiNg1'}
        known_urls: set[str] = set()
        new_cards, skipped = JijiDedupService.filter_new_cards(
            cards,
            known_ids=known_ids,
            known_urls=known_urls,
            limit=5,
        )
        self.assertEqual(skipped, 1)
        self.assertEqual(len(new_cards), 1)
        self.assertEqual(new_cards[0]['listing_id'], 'NeWlIsTiNg9999')

    def test_load_known_sets_respects_test_context(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestJijiListing.objects.create(
                listing_id='CTXJIJI01',
                listing_url='https://jiji.sn/ctx.html',
                title='Test',
            )
            ids, urls = JijiDedupService.load_known_sets()
            self.assertIn('CTXJIJI01', ids)
            self.assertEqual(JijiListing.objects.count(), 0)
        finally:
            reset_collection_context(token)


class JijiScraperViewsTests(TestCase):
    def test_parse_views_from_b_advert_info_statistics_english(self):
        scraper = JijiScraper(use_playwright=False)
        url = (
            'https://jiji.sn/en/parcelles-assainies/farm-machinery-equipment/'
            'pompes-immergees-oVAw3CoTCpZGcgmcqtO6KuRT.html'
        )
        extracted = scraper._parse_listing_page(DETAIL_VIEWS_EN_HTML, url)
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted.views_count, 20)
        self.assertEqual(extracted.seller_name, 'Vackson Sénégal')

    def test_fetch_homepage_cards_parsing(self):
        scraper = JijiScraper(use_playwright=False)
        cards = scraper._parse_listing_cards(HOMEPAGE_HTML)
        self.assertGreaterEqual(len(cards), 2)
        filtered = scraper.filter_cards_by_keyword(cards, 'iphone')
        self.assertEqual(len(filtered), 1)
        self.assertIn('iPhone', filtered[0]['title'])


class JijiKeywordDemandTests(TestCase):
    def test_keyword_demand_ranking_by_views(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestJijiListing.objects.create(
                listing_id='DEM1',
                listing_url='https://jiji.sn/d1.html',
                title='Pompe A',
                search_keyword='pompe',
                price_xof=Decimal('100000'),
                views_count=120,
            )
            TestJijiListing.objects.create(
                listing_id='DEM2',
                listing_url='https://jiji.sn/d2.html',
                title='Pompe B',
                search_keyword='pompe',
                price_xof=Decimal('90000'),
                views_count=80,
            )
            TestJijiListing.objects.create(
                listing_id='DEM3',
                listing_url='https://jiji.sn/d3.html',
                title='Phone',
                search_keyword='iphone',
                price_xof=Decimal('500000'),
                views_count=50,
            )
            ranking = JijiMarketSignalService.get_keyword_demand_ranking(limit=5)
            self.assertEqual(ranking[0]['keyword'], 'pompe')
            self.assertEqual(ranking[0]['total_views'], 200)
            self.assertEqual(ranking[0]['ads'], 2)
            self.assertEqual(ranking[0]['max_views'], 120)
        finally:
            reset_collection_context(token)
