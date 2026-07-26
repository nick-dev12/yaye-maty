"""Tests mots-clés marketplace — Paramètres et collecte."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from intelligence.models import MarketSearchKeyword
from intelligence.services.active_keyword_service import ActiveKeywordService
from intelligence.services.jiji_collection_service import JijiCollectionService
from intelligence.services.jumia_collection_service import JumiaCollectionService


class MarketplaceKeywordServiceTests(TestCase):
    def setUp(self):
        MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.TIKTOK,
            keyword='tiktok only',
            region='SN',
            is_active=True,
            max_videos=10,
        )
        self.marketplace_kw = MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
            keyword='motopompe',
            product_category='irrigation',
            region='SN',
            is_active=True,
            max_videos=7,
            max_comments=12,
        )
        MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
            keyword='inactif marketplace',
            region='SN',
            is_active=False,
            max_videos=5,
        )

    def test_list_for_jumia_and_jiji_use_same_marketplace_keywords(self):
        jumia = ActiveKeywordService.list_for_jumia()
        jiji = ActiveKeywordService.list_for_jiji()
        keywords = {kw.keyword for kw in jumia}
        self.assertEqual(keywords, {'motopompe'})
        self.assertEqual(jumia, jiji)
        self.assertEqual(jumia[0].max_videos, 7)

    def test_build_search_urls_marketplace(self):
        self.assertIn('jumia.sn', self.marketplace_kw.build_jumia_url())
        self.assertTrue(self.marketplace_kw.build_jiji_url().startswith('https://jiji.sn'))

    @patch('intelligence.services.jumia_collection_service.JumiaScraper')
    def test_jumia_collection_uses_keyword_product_limit(self, scraper_cls):
        mock_scraper = MagicMock()
        mock_scraper.search_listing_urls.return_value = []
        mock_scraper.request_count = 0
        mock_scraper.playwright_fetches = 0
        scraper_cls.return_value = mock_scraper

        result = JumiaCollectionService.run(test_mode=True)

        self.assertTrue(result['success'])
        mock_scraper.search_listing_urls.assert_called_once()
        _args, kwargs = mock_scraper.search_listing_urls.call_args
        self.assertEqual(_args[0], 'motopompe')
        self.assertEqual(kwargs['max_products'], 5)
        self.assertEqual(kwargs['product_category'], 'irrigation')

    @patch('intelligence.services.jiji_collection_service.JijiScraper')
    def test_jiji_collection_uses_same_keyword_list(self, scraper_cls):
        mock_scraper = MagicMock()
        mock_scraper.search_listing_urls.return_value = []
        mock_scraper.request_count = 0
        scraper_cls.return_value = mock_scraper

        result = JijiCollectionService.run(test_mode=True)

        self.assertTrue(result['success'])
        mock_scraper.search_listing_urls.assert_called_once()
        _args, kwargs = mock_scraper.search_listing_urls.call_args
        self.assertEqual(_args[0], 'motopompe')
        self.assertEqual(kwargs['max_products'], 5)

    def test_jumia_run_fails_without_marketplace_keywords(self):
        MarketSearchKeyword.objects.filter(
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
        ).delete()
        result = JumiaCollectionService.run(test_mode=True)
        self.assertFalse(result['success'])
        self.assertIn('marketplace', result['message'].lower())

    def test_jiji_run_fails_without_marketplace_keywords(self):
        MarketSearchKeyword.objects.filter(
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
        ).delete()
        result = JijiCollectionService.run(test_mode=True)
        self.assertFalse(result['success'])
        self.assertIn('marketplace', result['message'].lower())
