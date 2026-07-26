from django.test import TestCase
from django.utils import timezone

from intelligence.models import DiscoveredQuery, SocialComment, SocialPost, TopPurchaseRecommendation
from intelligence.services.product_extraction_service import ProductExtractionService
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService


class ProductExtractionServiceTests(TestCase):
    def test_extract_mini_tracteur_from_caption(self):
        result = ProductExtractionService.extract(
            'Mini Tracteurs Puissants disponibles au Sénégal #MiniTracteur',
            hashtags=['Agriculture', 'MiniTracteur'],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['slug'], 'mini_tracteur')

    def test_extract_motopompe_from_purchase_comment(self):
        result = ProductExtractionService.extract_for_comment(
            "C'est combien la motopompe pour irrigation svp ?",
            SocialComment.Intent.PURCHASE,
        )
        self.assertIsNotNone(result)
        self.assertIn(result['slug'], ('motopompe', 'goutte_a_goutte'))

    def test_no_product_on_off_topic(self):
        result = ProductExtractionService.extract_for_comment(
            'Belle vidéo merci',
            SocialComment.Intent.OFF_TOPIC,
        )
        self.assertIsNone(result)


class PurchaseRecommendationServiceTests(TestCase):
    def setUp(self):
        self.post = SocialPost.objects.create(
            platform=SocialPost.Platform.TIKTOK,
            platform_post_id='1234567890',
            source_url='https://www.tiktok.com/@test/video/1234567890',
            content='Motopompe solaire pour irrigation au Sénégal #irrigation #pompe',
            content_hash=SocialPost.build_content_hash('motopompe test unique hash 1'),
            hashtags=['irrigation', 'pompe'],
            view_count=5000,
            like_count=120,
            analysis_status=SocialPost.AnalysisStatus.DONE,
            extracted_product='Motopompe / Pompe irrigation',
            extracted_product_slug='motopompe',
            category='irrigation',
        )
        SocialComment.objects.create(
            post=self.post,
            text="Je veux acheter cette motopompe, c'est combien ?",
            text_hash=SocialComment.build_text_hash('achat motopompe prix 1'),
            intent=SocialComment.Intent.PURCHASE,
            is_analyzed=True,
            analyzed_at=timezone.now(),
            extracted_product='Motopompe / Pompe irrigation',
            extracted_product_slug='motopompe',
        )
        DiscoveredQuery.objects.create(
            domain=DiscoveredQuery.Domain.AGRICULTURE,
            query='motopompe irrigation',
            query_type=DiscoveredQuery.QueryType.RISING,
            value_display='+120%',
        )

    def test_refresh_top_recommendations(self):
        result = PurchaseRecommendationService.refresh_top_recommendations(window_days=30)
        self.assertGreaterEqual(result['created'], 1)
        top = TopPurchaseRecommendation.objects.first()
        self.assertIsNotNone(top)
        self.assertEqual(top.product_slug, 'motopompe')
        self.assertGreater(top.score_normalized, 0)
        self.assertIn('achat', top.evidence_text)

    def test_get_top_for_display(self):
        PurchaseRecommendationService.refresh_top_recommendations(window_days=30)
        items = PurchaseRecommendationService.get_top_for_display()
        self.assertTrue(items)
        self.assertEqual(items[0]['rank'], 1)
