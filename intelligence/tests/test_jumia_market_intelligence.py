"""
Tests Jumia — parsing, historique, signaux marché, NLP lexical, isolation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from intelligence.models import (
    JumiaProduct,
    JumiaReview,
    ProductMarketSignal,
    TestJumiaProduct,
    TestJumiaReview,
    TestProductMarketSignal,
)
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.jumia_market_signal_service import JumiaMarketSignalService
from intelligence.services.jumia_nlp_analysis_service import JumiaNlpAnalysisService
from intelligence.services.jumia_scraper import ExtractedJumiaProduct, JumiaScraper
from intelligence.services.jumia_collection_service import JumiaCollectionService
from intelligence.services.test_data_purge_service import TestDataPurgeService


PRODUCT_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Motopompe Honda 3CV irrigation",
  "sku": "TESTSKU001",
  "brand": {"@type": "Brand", "name": "Honda"},
  "category": "Pompes",
  "description": "Pompe irrigation agricole",
  "offers": {
    "@type": "Offer",
    "price": "189000.00",
    "priceCurrency": "XOF",
    "availability": "http://schema.org/InStock",
    "seller": {"@type": "Organization", "name": "AgriShop SN"}
  },
  "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.5, "ratingCount": 42},
  "image": {"contentUrl": ["https://sn.jumia.is/img.jpg"]}
}
</script>
<span class="old">250000 FCFA</span>
<div>Il n'en reste plus que 3. Ajouter au panier</div>
</body></html>
"""

REVIEWS_HTML = """
<html><body>
<article class="-pvm">
  <div class="stars">1 out of 5</div>
  <h3>Fragile</h3>
  <p>Le produit est fragile et en panne après 2 jours, livraison en retard</p>
  <div><span>10-06-2026</span><span>par Awa</span>Achat vérifié</div>
</article>
<article class="-pvm">
  <div class="stars">5 out of 5</div>
  <h3>Top</h3>
  <p>Bon produit, prix abordable</p>
  <div><span>11-06-2026</span><span>par Mamadou</span>Achat vérifié</div>
</article>
<div>Avis vérifiés (2) 5 (1) 4 (0) 3 (0) 2 (0) 1 (1) Commentaires (2)</div>
</body></html>
"""

LISTING_HTML = """
<html><body>
<article class="prd">
  <a class="core" href="/motopompe-honda-3cv-123.html">
    <div class="name">Motopompe Honda 3CV</div>
    <div class="prc">189000 FCFA</div>
    <div class="old">250000 FCFA</div>
    <div class="stars">4.5 out of 5 (42)</div>
  </a>
</article>
<article class="prd">
  <a class="core" href="/chargeur-usb-999.html">
    <div class="name">Chargeur USB</div>
    <div class="prc">2000 FCFA</div>
  </a>
</article>
</body></html>
"""


class JumiaScraperParseTests(TestCase):
    def test_parse_product_brand_discount_stock(self):
        scraper = JumiaScraper(use_playwright_fallback=False)
        product = scraper._parse_product_page(PRODUCT_HTML, '/motopompe.html')
        self.assertIsNotNone(product)
        self.assertEqual(product.sku, 'TESTSKU001')
        self.assertEqual(product.brand, 'Honda')
        self.assertEqual(product.price_xof, Decimal('189000.00'))
        self.assertEqual(product.old_price_xof, Decimal('250000'))
        self.assertAlmostEqual(product.discount_percent, 24.4, places=0)
        self.assertEqual(product.stock_status, JumiaProduct.StockStatus.LOW_STOCK)
        self.assertEqual(product.stock_quantity, 3)
        self.assertTrue(product.is_in_stock)
        self.assertEqual(product.catalog_product_slug or scraper._guess_catalog_slug(product.name), 'motopompe')

    def test_parse_discount_badge_reconstructs_old_price(self):
        html = """
        <html><body>
        <script type="application/ld+json">
        {
          "@type": "Product",
          "name": "Tecno Pop",
          "sku": "DISC001",
          "offers": {"@type": "Offer", "price": "82900.00", "priceCurrency": "XOF",
                     "availability": "http://schema.org/InStock"}
        }
        </script>
        <span class="bdg _dsct">11%</span>
        </body></html>
        """
        scraper = JumiaScraper(use_playwright_fallback=False)
        product = scraper._parse_product_page(html, '/tecno.html')
        self.assertIsNotNone(product)
        self.assertEqual(product.discount_percent, 11.0)
        self.assertIsNotNone(product.old_price_xof)
        self.assertGreater(product.old_price_xof, product.price_xof)

    def test_accessories_category_path_uses_phones(self):
        self.assertEqual(
            JumiaScraper.resolve_category_path('telephone et accessoir'),
            '/telephones-tablettes/',
        )

    def test_filter_accessory_keyword_rejects_sports(self):
        scraper = JumiaScraper(use_playwright_fallback=False)
        cards = [
            {'name': 'Chargeur iPhone Type-C', 'url': '/a.html'},
            {'name': 'Coque Samsung Galaxy', 'url': '/b.html'},
            {'name': 'Lot De 40 Cônes Coupelles', 'url': '/c.html'},
            {'name': 'Téléphone Tecno Pop', 'url': '/d.html'},
        ]
        filtered = scraper._filter_cards_by_keyword(cards, 'telephone et accessoir')
        names = [c['name'] for c in filtered]
        self.assertIn('Chargeur iPhone Type-C', names)
        self.assertIn('Coque Samsung Galaxy', names)
        self.assertNotIn('Lot De 40 Cônes Coupelles', names)

    def test_product_limit_uses_keyword_max_videos(self):
        class _Kw:
            max_videos = 12
            max_comments = 18

        self.assertEqual(
            JumiaCollectionService._product_limit_for_keyword(_Kw(), session_cap=0),
            12,
        )
        self.assertEqual(
            JumiaCollectionService._product_limit_for_keyword(_Kw(), session_cap=5),
            5,
        )
        self.assertEqual(
            JumiaCollectionService._review_limit_for_keyword(_Kw(), session_cap=20),
            18,
        )

    def test_parse_reviews_and_failures_lexical(self):
        scraper = JumiaScraper(use_playwright_fallback=False)
        reviews, dist, comments = scraper._parse_reviews_page(REVIEWS_HTML)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].rating_stars, 1)
        self.assertIn('fragile', reviews[0].comment_text.lower())
        self.assertEqual(comments, 2)
        lexical = JumiaNlpAnalysisService.analyze_text_lexical(
            f'{reviews[0].title} — {reviews[0].comment_text}',
            rating_stars=1,
        )
        self.assertEqual(lexical['sentiment'], 'negative')
        self.assertTrue(lexical['failure_tags'])

    def test_filter_listing_by_keyword(self):
        scraper = JumiaScraper(use_playwright_fallback=False)
        cards = scraper._parse_listing_cards(LISTING_HTML)
        filtered = scraper._filter_cards_by_keyword(cards, 'motopompe')
        self.assertEqual(len(filtered), 1)
        self.assertIn('Motopompe', filtered[0]['name'])


class JumiaPersistAndSignalsTests(TestCase):
    def test_persist_creates_snapshot_and_isolation(self):
        extracted = ExtractedJumiaProduct(
            sku='ISO001',
            product_url='https://www.jumia.sn/x.html',
            name='Motopompe test',
            brand='Generic',
            price_xof=Decimal('100000'),
            old_price_xof=Decimal('120000'),
            discount_percent=16.7,
            stock_status=JumiaProduct.StockStatus.OUT_OF_STOCK,
            is_in_stock=False,
            rating_value=4.2,
            rating_count=55,
            search_keyword='motopompe',
            catalog_product_slug='motopompe',
        )
        token = set_collection_context(CollectionRunContext.test())
        try:
            created, updated, revs, snaps = JumiaCollectionService._persist_safe(extracted)
            self.assertEqual(created, 1)
            self.assertEqual(snaps, 1)
            self.assertEqual(TestJumiaProduct.objects.count(), 1)
            self.assertEqual(JumiaProduct.objects.count(), 0)
        finally:
            reset_collection_context(token)

    def test_market_signal_critical_stockout(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestDataPurgeService.purge_all()
            p = TestJumiaProduct.objects.create(
                sku='CRIT1',
                product_url='https://www.jumia.sn/a.html',
                name='Couveuse 500 oeufs',
                catalog_product_slug='couveuse',
                search_keyword='couveuse',
                price_xof=Decimal('150000'),
                rating_value=4.6,
                rating_count=120,
                stock_status=JumiaProduct.StockStatus.OUT_OF_STOCK,
                is_in_stock=False,
            )
            TestJumiaProduct.objects.create(
                sku='CRIT2',
                product_url='https://www.jumia.sn/b.html',
                name='Couveuse auto',
                catalog_product_slug='couveuse',
                search_keyword='couveuse',
                price_xof=Decimal('160000'),
                rating_value=4.1,
                rating_count=40,
                stock_status=JumiaProduct.StockStatus.OUT_OF_STOCK,
                is_in_stock=False,
            )
            TestJumiaReview.objects.create(
                product=p,
                review_hash='abc',
                rating_stars=1,
                title='Cassé',
                comment_text='Produit fragile en panne',
                sentiment='negative',
                failure_tags=['fragile', 'panne'],
                is_analyzed=True,
            )
            stats = JumiaMarketSignalService.refresh_all()
            self.assertGreaterEqual(stats['created'], 1)
            signal = TestProductMarketSignal.objects.get(product_slug='couveuse')
            self.assertEqual(signal.stock_alert, 'critical')
            self.assertGreater(signal.jumia_boost, 0)
            self.assertIsNotNone(signal.avg_price_xof)
            # prod intact
            self.assertEqual(ProductMarketSignal.objects.count(), 0)
        finally:
            reset_collection_context(token)

    def test_apply_nlp_results(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            TestDataPurgeService.purge_all()
            p = TestJumiaProduct.objects.create(
                sku='NLP1',
                product_url='https://www.jumia.sn/c.html',
                name='Pompe solaire',
                catalog_product_slug='pompe_solaire',
                price_xof=Decimal('200000'),
            )
            r = TestJumiaReview.objects.create(
                product=p,
                review_hash='nlp1',
                rating_stars=2,
                title='Retard',
                comment_text='Livraison en retard et notice absente',
            )
            stats = JumiaNlpAnalysisService.apply_analysis_results([{
                'id': r.pk,
                'sentiment': 'negative',
                'intent': 'plainte',
                'aspects': {'livraison': 'neg', 'notice': 'neg'},
                'failure_tags': ['livraison_retard', 'notice_manquante'],
                'confidence': 0.9,
                'method': 'camembert',
            }])
            self.assertEqual(stats['updated'], 1)
            r.refresh_from_db()
            self.assertTrue(r.is_analyzed)
            self.assertEqual(r.sentiment, 'negative')
            self.assertIn('livraison_retard', r.failure_tags)
        finally:
            reset_collection_context(token)
