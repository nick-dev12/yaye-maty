"""Tests TradeDomainCatalog — domaines DB MarketDomain."""

from django.test import TestCase

from intelligence.models import MarketDomain
from intelligence.services.trade_domain_catalog import TradeDomainCatalog


class TradeDomainCatalogTests(TestCase):
    def setUp(self):
        MarketDomain.objects.create(
            slug='telephonie',
            label='Téléphonie',
            cat_id=13,
            seed_keywords='téléphone,smartphone',
            is_active=True,
        )
        MarketDomain.objects.create(
            slug='inactive-dom',
            label='Inactif',
            cat_id=1,
            is_active=False,
        )

    def test_list_domains_only_active(self):
        domains = TradeDomainCatalog.list_domains()
        slugs = {d['slug'] for d in domains}
        self.assertIn('telephonie', slugs)
        self.assertNotIn('inactive-dom', slugs)

    def test_build_search_query(self):
        query = TradeDomainCatalog.build_search_query('Téléphonie', 'iPhone 14')
        self.assertIn('iPhone 14', query)
        self.assertIn('Sénégal', query)

    def test_build_search_query_keyword_optional(self):
        query = TradeDomainCatalog.build_search_query('Téléphonie', '')
        self.assertIn('Téléphonie', query)
        self.assertIn('Sénégal', query)
        self.assertNotIn('iPhone', query)

    def test_normalize_duration(self):
        self.assertEqual(TradeDomainCatalog.normalize_duration(20), 20)
        self.assertEqual(TradeDomainCatalog.normalize_duration(99), 120)
        self.assertEqual(TradeDomainCatalog.normalize_duration(5), 10)

    def test_normalize_sources(self):
        self.assertEqual(
            TradeDomainCatalog.normalize_sources(['tiktok', 'facebook', 'jumia']),
            ['tiktok', 'jumia'],
        )
