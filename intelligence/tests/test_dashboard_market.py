"""Contexte du tableau de bord — KPI + marché Jumia/Jiji."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from intelligence.services.dashboard_data_service import DashboardDataService


class DashboardMarketContextTests(TestCase):
    """Le home doit exposer une lecture marché simplifiée."""

    def test_build_context_exposes_four_decision_blocks(self):
        ctx = DashboardDataService.build_context()

        self.assertIn('decision_kpis', ctx)
        self.assertEqual(len(ctx['decision_kpis']), 4)
        self.assertEqual(
            [kpi['id'] for kpi in ctx['decision_kpis']],
            ['posts', 'intents', 'jumia', 'jiji'],
        )

        market = ctx['market_overview']
        self.assertIn('jumia', market)
        self.assertIn('jiji', market)
        self.assertIn('arbitrage', market)
        self.assertIn('has_jumia', market)
        self.assertIn('has_jiji', market)
        self.assertEqual(market['arbitrage_title'], 'Neuf Jiji moins cher que Jumia')

        self.assertIn('title', ctx['social_demand'])
        self.assertIn('themes', ctx['social_demand'])
        self.assertIn('market_report', ctx)
        self.assertIn('preview_cards', ctx['market_report'])
        self.assertTrue(ctx['summary_line'])

    def test_dashboard_page_renders(self):
        user = get_user_model().objects.create_user(
            username='dash-market',
            password='test-password',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Où en est la veille')
        self.assertContains(response, 'Les 3 signaux forts du moment')
        self.assertContains(response, 'Marché en bref')
        self.assertContains(response, 'Prix &amp; stock Jumia')
        self.assertContains(response, 'Occasions Jiji')
        self.assertContains(response, 'Intelligence marché')
        self.assertNotContains(response, 'Lancer une collecte')
        self.assertNotContains(response, 'Que faire ensuite')
