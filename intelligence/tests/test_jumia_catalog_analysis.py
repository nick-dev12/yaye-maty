"""Tests catalogue Jumia → analyse TI (100 produits/tour, max 3 tours)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from intelligence.models import JumiaCategory, JumiaProduct, JumiaReview
from intelligence.services.trade_research_collection_service import TradeResearchCollectionService

# Token unique pour éviter les collisions avec des produits réels en BDD partagée
QUERY = 'zorphonex'


class JumiaCatalogAnalysisTests(TestCase):
    def setUp(self):
        self.cat = JumiaCategory.objects.create(
            slug='cat-zorphonex',
            name='Zorphonex Cat',
            path='/cat-zorphonex/',
            url='https://www.jumia.sn/cat-zorphonex/',
        )
        rows = [
            JumiaProduct(
                sku=f'SKU-ZORPH-{i:04d}',
                product_url=f'https://www.jumia.sn/zorphonex-{i}/',
                name=f'Zorphonex Ultra modèle {i}',
                brand='Zorphonex',
                category='Gadgets',
                jumia_category=self.cat,
                price_xof=Decimal('450000') + i,
                old_price_xof=Decimal('500000'),
                discount_percent=10.0,
                rating_value=4.5,
                rating_count=10 + i,
                seller_name='Jumia',
            )
            for i in range(250)
        ]
        JumiaProduct.objects.bulk_create(rows)
        # Avis sur le produit le mieux noté (premier du slice tour 0)
        top = JumiaProduct.objects.filter(sku='SKU-ZORPH-0249').first()
        JumiaReview.objects.create(
            product=top,
            review_hash='hash-zorph-1',
            rating_stars=5,
            title='Excellent',
            comment_text='Très bon produit zorphonex, livraison rapide.',
            author='Awa',
            verified_purchase=True,
        )

    def tearDown(self):
        JumiaProduct.objects.filter(sku__startswith='SKU-ZORPH-').delete()
        JumiaCategory.objects.filter(slug='cat-zorphonex').delete()

    def test_collect_from_catalog_tour_limits(self):
        t0 = TradeResearchCollectionService.collect_jumia_from_catalog(
            QUERY, tour_index=0, limit=100,
        )
        self.assertTrue(t0['success'])
        self.assertEqual(t0['source'], 'catalog')
        self.assertEqual(t0['products_count'], 100)
        self.assertEqual(t0['total_matching'], 250)
        self.assertTrue(t0['has_more'])
        self.assertGreaterEqual(len(t0['reviews_sample']), 1)

        t1 = TradeResearchCollectionService.collect_jumia_from_catalog(
            QUERY, tour_index=1, limit=100,
        )
        self.assertEqual(t1['products_count'], 100)
        self.assertEqual(t1['offset'], 100)

        t2 = TradeResearchCollectionService.collect_jumia_from_catalog(
            QUERY, tour_index=2, limit=100,
        )
        self.assertEqual(t2['products_count'], 50)
        self.assertFalse(t2['has_more'])

        t3 = TradeResearchCollectionService.collect_jumia_from_catalog(
            QUERY, tour_index=3, limit=100,
        )
        self.assertEqual(t3['products_count'], 0)
        self.assertFalse(t3['has_more'])

    def test_collect_jumia_prefers_catalog(self):
        with patch(
            'intelligence.services.trade_research_collection_service.JumiaCollectionService.run_for_keywords'
        ) as mock_live:
            result = TradeResearchCollectionService.collect_jumia(
                QUERY, tour_index=0,
            )
            self.assertEqual(result['source'], 'catalog')
            self.assertEqual(result['products_count'], 100)
            mock_live.assert_not_called()

    def test_aggregate_payload_includes_catalog_meta(self):
        t0 = TradeResearchCollectionService.collect_jumia_from_catalog(
            QUERY, tour_index=0, limit=100,
        )
        payload = TradeResearchCollectionService.aggregate_payload(
            QUERY,
            collect_results={'jumia': t0, 'jumia_tours': [t0]},
        )
        self.assertEqual(payload['jumia']['source'], 'catalog')
        self.assertEqual(payload['jumia']['tours_used'], 1)
        self.assertEqual(payload['jumia']['products_scanned'], 100)
        self.assertTrue(payload['jumia']['products'])
        self.assertTrue(payload['jumia']['reviews_sample'])

    @override_settings(TRADE_RESEARCH={
        'JUMIA_CATALOG_PRODUCTS_PER_TOUR': 100,
        'JUMIA_CATALOG_MAX_TOURS': 3,
        'JUMIA_SOURCE': 'catalog',
        'MAX_PRODUCTS': 500,
        'MAX_LISTINGS': 500,
        'MAX_SOCIAL_POSTS': 200,
        'MAX_REVIEWS': 20,
    })
    def test_catalog_max_tours_cap_is_three(self):
        """Simule 4 appels catalogue : seuls 3 tours utiles (offsets 0/100/200)."""
        max_tours = 3
        per_tour = 100
        scanned = 0
        for tour_index in range(max_tours + 1):
            if tour_index >= max_tours:
                break
            result = TradeResearchCollectionService.collect_jumia_from_catalog(
                QUERY, tour_index=tour_index, limit=per_tour,
            )
            scanned += result['products_count']
            if not result.get('has_more'):
                break
        self.assertEqual(scanned, 250)
        # Un 4ᵉ tour ne doit pas être lancé par l'orchestrateur (plafond 3)
        fourth = TradeResearchCollectionService.collect_jumia_from_catalog(
            QUERY, tour_index=3, limit=per_tour,
        )
        self.assertEqual(fourth['products_count'], 0)


class JumiaCatalogDedupTests(TestCase):
    """Anti-doublon catalogue : ignorer si inchangé, maj note/nouveaux avis."""

    def setUp(self):
        self.cat = JumiaCategory.objects.create(
            slug='cat-dedup-zorph',
            name='Dedup Cat',
            path='/cat-dedup-zorph/',
            url='https://www.jumia.sn/cat-dedup-zorph/',
        )
        self.product = JumiaProduct.objects.create(
            sku='SKU-DEDUP-001',
            product_url='https://www.jumia.sn/dedup-1/',
            name='Produit Dedup',
            brand='Brand',
            category='Gadgets',
            jumia_category=self.cat,
            price_xof=Decimal('10000'),
            rating_value=4.0,
            rating_count=5,
            comments_count=5,
        )
        JumiaReview.objects.create(
            product=self.product,
            review_hash=JumiaReview.build_review_hash(
                title='ok', comment_text='déjà là', author='A', rating_stars=4,
            ),
            rating_stars=4,
            title='ok',
            comment_text='déjà là',
            author='A',
        )

    def tearDown(self):
        JumiaProduct.objects.filter(sku='SKU-DEDUP-001').delete()
        JumiaCategory.objects.filter(slug='cat-dedup-zorph').delete()

    def test_skip_unchanged_duplicate(self):
        from intelligence.services.jumia_catalog_crawl_service import JumiaCatalogCrawlService

        class DummyScraper:
            def _parse_price(self, text):
                return Decimal('10000')

            def fetch_product(self, *a, **k):
                raise AssertionError('ne doit pas fetcher un doublon inchangé')

        card = {
            'url': self.product.product_url,
            'name': self.product.name,
            'brand': 'Brand',
            'category': 'Gadgets',
            'price': '10000',
            'old_price': '',
            'discount_percent': None,
            'rating': 4.0,
            'review_count': 5,
        }
        created, updated, reviews, skipped = JumiaCatalogCrawlService._persist_card(
            DummyScraper(),
            card=card,
            sku=self.product.sku,
            category=self.cat,
            category_label='Dedup',
            with_reviews=True,
        )
        self.assertEqual((created, updated, reviews, skipped), (0, 0, 0, 1))

    def test_update_when_rating_changes(self):
        from intelligence.services.jumia_catalog_crawl_service import JumiaCatalogCrawlService

        class DummyScraper:
            def _parse_price(self, text):
                return Decimal('10000')

            def fetch_product(self, *a, **k):
                return None

            def fetch_reviews(self, *a, **k):
                return [], {}, 0

        card = {
            'url': self.product.product_url,
            'name': self.product.name,
            'price': '10000',
            'old_price': '',
            'discount_percent': None,
            'rating': 4.7,
            'review_count': 5,
        }
        created, updated, reviews, skipped = JumiaCatalogCrawlService._persist_card(
            DummyScraper(),
            card=card,
            sku=self.product.sku,
            category=self.cat,
            category_label='Dedup',
            with_reviews=False,
        )
        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        self.assertEqual(skipped, 0)
        self.product.refresh_from_db()
        self.assertAlmostEqual(self.product.rating_value, 4.7)

    def test_add_only_new_reviews(self):
        from dataclasses import dataclass
        from intelligence.services.jumia_catalog_crawl_service import JumiaCatalogCrawlService

        @dataclass
        class FakeRev:
            title: str = ''
            comment_text: str = ''
            author: str = ''
            rating_stars: int | None = None
            review_date: None = None
            verified_purchase: bool = False

        class DummyScraper:
            def _parse_price(self, text):
                return Decimal('10000')

            def fetch_product(self, *a, **k):
                return None

            def fetch_reviews(self, *a, **k):
                return [
                    FakeRev(title='ok', comment_text='déjà là', author='A', rating_stars=4),
                    FakeRev(title='nouveau', comment_text='avis frais', author='B', rating_stars=5),
                ], {}, 6

        card = {
            'url': self.product.product_url,
            'name': self.product.name,
            'price': '10000',
            'old_price': '',
            'discount_percent': None,
            'rating': 4.0,
            'review_count': 6,  # > 5 → déclenche maj avis
        }
        created, updated, reviews, skipped = JumiaCatalogCrawlService._persist_card(
            DummyScraper(),
            card=card,
            sku=self.product.sku,
            category=self.cat,
            category_label='Dedup',
            with_reviews=True,
        )
        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        self.assertEqual(reviews, 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(JumiaReview.objects.filter(product=self.product).count(), 2)
