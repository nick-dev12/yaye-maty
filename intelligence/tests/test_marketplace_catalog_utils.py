"""Tests utilitaires catalogue marketplace."""

from django.test import TestCase

from intelligence.services.marketplace_catalog_utils import resolve_catalog_slug


class MarketplaceCatalogUtilsTests(TestCase):
    def test_product_category_takes_priority(self):
        slug = resolve_catalog_slug(
            'Article générique',
            'motopompe',
            product_category='motopompe',
        )
        self.assertEqual(slug, 'motopompe')

    def test_keyword_heuristic_when_no_category(self):
        slug = resolve_catalog_slug('Mini tracteur agricole', 'tracteur')
        self.assertEqual(slug, 'mini_tracteur')
