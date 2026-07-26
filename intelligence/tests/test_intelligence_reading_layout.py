"""Lecture marché simplifiée sur /intelligence/."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from intelligence.services.dashboard_data_service import DashboardDataService


class IntelligenceReadingLayoutTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username='intel-reading',
            password='test-password',
        )
        self.client.force_login(self.user)

    def test_pack_market_overview_from_empty_display_contexts(self):
        overview = DashboardDataService.pack_market_overview(
            {'has_jumia': False, 'jumia_stats': {}, 'jumia_opportunities': [], 'jumia_products': []},
            {'has_jiji': False, 'jiji_stats': {}, 'jiji_arbitrage': [], 'jiji_heatmap': [], 'jiji_listings': []},
        )
        self.assertFalse(overview['has_jumia'])
        self.assertFalse(overview['has_jiji'])
        self.assertEqual(overview['jumia']['products'], 0)
        self.assertEqual(overview['arbitrage_title'], 'Neuf Jiji moins cher que Jumia')

    def test_intelligence_page_shows_reading_and_top10_hub(self):
        response = self.client.get(reverse('intelligence:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Où en est la veille')
        self.assertContains(response, 'Que se passe-t-il sur le marché')
        self.assertContains(response, '3 actions du jour')
        self.assertContains(response, 'top10-hub')
        self.assertContains(response, 'Comment lire les Top 10')
        self.assertContains(response, 'Mode analyste')
