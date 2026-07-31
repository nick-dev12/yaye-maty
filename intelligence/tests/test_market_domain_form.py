"""Tests ajout domaine — libellé libre ou catégorie Google Trends."""

from django.test import SimpleTestCase
from unittest.mock import patch

from intelligence.forms.market_domain_forms import MarketDomainForm
from intelligence.services.google_trends_category_service import (
    CUSTOM_CATEGORY_ID,
    GoogleTrendsCategoryService,
)


class GoogleTrendsCategoryServiceTests(SimpleTestCase):
    def test_resolve_for_label_custom_when_no_match(self):
        cat_id, name, matched = GoogleTrendsCategoryService.resolve_for_label('Teste')
        self.assertEqual(cat_id, CUSTOM_CATEGORY_ID)
        self.assertEqual(name, 'Teste')
        self.assertFalse(matched)

    def test_resolve_for_label_google_when_known(self):
        with patch.object(
            GoogleTrendsCategoryService,
            'resolve_category',
            return_value=(43, 'Agriculture et sylviculture'),
        ):
            cat_id, name, matched = GoogleTrendsCategoryService.resolve_for_label(
                'Agriculture et sylviculture',
            )
        self.assertEqual(cat_id, 43)
        self.assertTrue(matched)

    def test_fallback_categories_when_api_empty(self):
        GoogleTrendsCategoryService._get_flat_categories.cache_clear()
        with patch.object(
            GoogleTrendsCategoryService,
            '_flatten_tree',
            side_effect=lambda *_a, **_k: None,
        ):
            with patch('intelligence.services.google_trends_category_service.TrendReq') as mock_req:
                mock_req.return_value.categories.side_effect = RuntimeError('429')
                cats = GoogleTrendsCategoryService._get_flat_categories()
        self.assertGreater(len(cats), 0)


class MarketDomainFormTests(SimpleTestCase):
    def test_custom_domain_label_accepted(self):
        form = MarketDomainForm(data={'label': 'Teste'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.google_category_matched)
        self.assertEqual(form._resolved_cat_id, CUSTOM_CATEGORY_ID)

    def test_empty_label_rejected(self):
        form = MarketDomainForm(data={'label': '   '})
        self.assertFalse(form.is_valid())
