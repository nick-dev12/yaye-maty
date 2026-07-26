"""Tests IntelligenceReportService et rankings Top 10."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from intelligence.models import (
    JijiListing,
    JumiaProduct,
    SocialPost,
    TestJijiListing,
    TestJumiaProduct,
    TestSocialPost,
)
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.intelligence_report_service import IntelligenceReportService
from intelligence.services.jiji_ranking_service import JijiRankingService
from intelligence.services.jumia_ranking_service import JumiaRankingService
from intelligence.services.social_ranking_service import SocialRankingService


class IntelligenceReportServiceTests(TestCase):
    def test_build_report_returns_six_sections(self):
        report = IntelligenceReportService.build_report(limit=10)
        self.assertIn('sections', report)
        self.assertEqual(len(report['sections']), 6)
        keys = {s['key'] for s in report['sections']}
        self.assertIn('top_sourcing', keys)
        self.assertIn('top_jiji_views', keys)

    def test_build_report_items_have_why_here_when_data(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestJijiListing.objects.create(
                listing_id='RPT001',
                listing_url='https://jiji.sn/rpt.html',
                title='Pompe test rapport',
                views_count=500,
                search_keyword='pompe',
            )
            report = IntelligenceReportService.build_report(limit=10)
            jiji_items = report['rankings']['top_jiji_views']
            self.assertTrue(jiji_items)
            self.assertTrue(jiji_items[0]['why_here'])
            self.assertEqual(jiji_items[0]['primary_value'], 500)
        finally:
            reset_collection_context(token)


class SocialRankingServiceTests(TestCase):
    def test_top_posts_by_views_test_isolation(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestSocialPost.objects.create(
                platform='tiktok',
                source_url='https://tiktok.com/v/1',
                content='Vidéo pompe très vue',
                content_hash='hashviews001',
                view_count=9000,
                like_count=120,
            )
            rows = SocialRankingService.get_top_posts(metric='views', limit=5)
            self.assertEqual(rows[0]['primary_value'], 9000)
            self.assertIn('vues', rows[0]['why_here'])
            self.assertEqual(SocialPost.objects.count(), 0)
        finally:
            reset_collection_context(token)


class JumiaJijiRankingTests(TestCase):
    def test_jumia_top_by_ratings(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestJumiaProduct.objects.create(
                sku='RANKJ01',
                product_url='https://www.jumia.sn/a.html',
                name='Produit populaire',
                rating_count=250,
                rating_value=4.5,
                price_xof=Decimal('50000'),
            )
            rows = JumiaRankingService.get_top_products(limit=5)
            self.assertEqual(rows[0]['primary_value'], 250)
            self.assertIn('250', rows[0]['why_here'])
        finally:
            reset_collection_context(token)

    def test_jiji_top_listings(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestJijiListing.objects.create(
                listing_id='RANKJ02',
                listing_url='https://jiji.sn/b.html',
                title='Annonce vue',
                views_count=88,
            )
            rows = JijiRankingService.get_top_listings(limit=5)
            self.assertEqual(rows[0]['primary_value'], 88)
        finally:
            reset_collection_context(token)


class IntelligencePageReportLayoutTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username='intel-report',
            password='test-password',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_intelligence_page_contains_top10_hub(self):
        response = self.client.get('/intelligence/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="top10-hub"', content)
        self.assertIn('Comment lire les Top 10', content)
        self.assertIn('ir10-tabs', content)
        self.assertIn('intel-expert', content)
