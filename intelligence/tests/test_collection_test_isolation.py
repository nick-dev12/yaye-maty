"""
Tests d'isolation collecte test — tables miroir vs production.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from intelligence.models import (
    SocialPost,
    TestDiscoveredQuery,
    TestSocialComment,
    TestSocialPost,
    TestTopPurchaseRecommendation,
    TopPurchaseRecommendation,
)
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService
from intelligence.services.test_data_purge_service import TestDataPurgeService


class TestDataPurgeServiceTests(TestCase):
    def test_purge_clears_test_tables(self):
        TestSocialPost.objects.create(
            platform=TestSocialPost.Platform.TIKTOK,
            platform_post_id='purge-test-1',
            source_url='https://www.tiktok.com/@x/video/1',
            content='purge test',
            content_hash=TestSocialPost.build_content_hash('purge test unique'),
        )
        TestDiscoveredQuery.objects.create(
            domain=TestDiscoveredQuery.Domain.AGRICULTURE,
            query='purge query',
            query_type=TestDiscoveredQuery.QueryType.TOP,
            value_display='100',
        )
        counts = TestDataPurgeService.purge_all()
        self.assertGreaterEqual(counts['posts'], 1)
        self.assertEqual(TestSocialPost.objects.count(), 0)
        self.assertEqual(TestDiscoveredQuery.objects.count(), 0)


class TestCollectionIsolationTests(TestCase):
    def setUp(self):
        self.prod_post = SocialPost.objects.create(
            platform=SocialPost.Platform.TIKTOK,
            platform_post_id='prod-top10-guard',
            source_url='https://www.tiktok.com/@prod/video/1',
            content='prod guard',
            content_hash=SocialPost.build_content_hash('prod guard unique'),
        )
        TopPurchaseRecommendation.objects.create(
            rank=1,
            product_slug='prod_slug',
            product_name='Produit prod',
            category='irrigation',
            score=50,
            score_normalized=80,
            purchase_intent_count=2,
            info_intent_count=1,
            total_views=1000,
            trends_boost=0,
            related_posts=1,
            evidence_text='prod evidence',
        )

    def test_test_collecte_does_not_write_prod_posts(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestSocialPost.objects.create(
                platform=TestSocialPost.Platform.TIKTOK,
                platform_post_id='test-only-1',
                source_url='https://www.tiktok.com/@test/video/1',
                content='test isolation',
                content_hash=TestSocialPost.build_content_hash('test isolation unique'),
            )
        finally:
            reset_collection_context(token)

        self.assertEqual(TestSocialPost.objects.count(), 1)
        self.assertEqual(SocialPost.objects.filter(platform_post_id='test-only-1').count(), 0)

    def test_refresh_top_in_test_does_not_delete_prod(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            post = TestSocialPost.objects.create(
                platform=TestSocialPost.Platform.TIKTOK,
                platform_post_id='test-nlp-1',
                source_url='https://www.tiktok.com/@test/video/2',
                content='Motopompe test isolation',
                content_hash=TestSocialPost.build_content_hash('motopompe test isolation'),
                hashtags=['irrigation'],
                view_count=2000,
                analysis_status=TestSocialPost.AnalysisStatus.DONE,
                extracted_product='Motopompe',
                extracted_product_slug='motopompe',
                category='irrigation',
            )
            TestSocialComment.objects.create(
                post=post,
                text="Je veux acheter cette motopompe",
                text_hash=TestSocialComment.build_text_hash('achat motopompe test iso'),
                intent=TestSocialComment.Intent.PURCHASE,
                is_analyzed=True,
                analyzed_at=timezone.now(),
                extracted_product='Motopompe',
                extracted_product_slug='motopompe',
            )
            PurchaseRecommendationService.refresh_top_recommendations(window_days=30)
        finally:
            reset_collection_context(token)

        self.assertEqual(TopPurchaseRecommendation.objects.filter(product_slug='prod_slug').count(), 1)
        self.assertGreaterEqual(TestTopPurchaseRecommendation.objects.count(), 1)

    def test_test_results_page_reads_test_tables_only(self):
        SocialPost.objects.create(
            platform=SocialPost.Platform.TIKTOK,
            platform_post_id='prod-hidden-on-test-page',
            source_url='https://www.tiktok.com/@prod/video/2',
            content='prod hidden',
            content_hash=SocialPost.build_content_hash('prod hidden unique'),
        )
        TestSocialPost.objects.create(
            platform=TestSocialPost.Platform.TIKTOK,
            platform_post_id='visible-on-test-page',
            source_url='https://www.tiktok.com/@test/video/3',
            content='visible test page',
            content_hash=TestSocialPost.build_content_hash('visible test page unique'),
        )

        client = Client()
        user = get_user_model().objects.create_user(username='tester', password='test-pass-123')
        client.force_login(user)
        response = client.get(reverse('intelligence:collecte_test_donnees'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'visible test page')
        self.assertNotContains(response, 'prod hidden')

    def test_router_selects_models_by_context(self):
        prod_router = CollectionModelRouter(CollectionRunContext.production())
        test_router = CollectionModelRouter(CollectionRunContext.test())
        self.assertFalse(prod_router.is_test)
        self.assertTrue(test_router.is_test)
        self.assertEqual(prod_router.post_model, SocialPost)
        self.assertEqual(test_router.post_model, TestSocialPost)

    def test_google_test_skips_auto_nlp(self):
        from intelligence.services.manual_collection_service import ManualCollectionService

        self.assertFalse(
            ManualCollectionService._should_chain_nlp(
                ManualCollectionService.JOB_GOOGLE,
                test_mode=True,
                auto_nlp_after=True,
            )
        )
        self.assertTrue(
            ManualCollectionService._should_chain_nlp(
                ManualCollectionService.JOB_SOCIAL,
                test_mode=True,
                auto_nlp_after=True,
            )
        )
        self.assertTrue(
            ManualCollectionService._should_chain_nlp(
                ManualCollectionService.JOB_GOOGLE,
                test_mode=False,
                auto_nlp_after=True,
            )
        )
