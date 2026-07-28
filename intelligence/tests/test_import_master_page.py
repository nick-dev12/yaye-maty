"""Tests page Import Master — rendu, contexte, recalcul."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from intelligence.models import ImportOpportunity, MarketSearchKeyword
from intelligence.services.import_master_display_service import ImportMasterDisplayService


def _create_opportunity(**overrides) -> ImportOpportunity:
    defaults = {
        'keyword_text': 'iphone 15',
        'product_name': 'iphone 15',
        'product_slug': 'iphone-15',
        'snapshot_date': timezone.localdate(),
        'rank': 1,
        'score': 82,
        'demand_score': 75,
        'trend_score': 60,
        'competition_score': 80,
        'price_score': 65,
        'decision': ImportOpportunity.Decision.BUY,
        'decision_reasons': ['8 commentaires « je veux acheter » cette semaine'],
    }
    defaults.update(overrides)
    return ImportOpportunity.objects.create(**defaults)


class ImportMasterDisplayTests(TestCase):

    def test_build_context_with_opportunities(self):
        _create_opportunity()
        _create_opportunity(
            keyword_text='chargeur',
            product_name='chargeur',
            rank=2,
            score=25,
            decision=ImportOpportunity.Decision.AVOID,
        )

        ctx = ImportMasterDisplayService.build_context()

        self.assertTrue(ctx['im_has_data'])
        self.assertEqual(ctx['im_counts']['buy'], 1)
        self.assertEqual(ctx['im_counts']['avoid'], 1)
        self.assertEqual(ctx['im_counts']['total'], 2)
        first = ctx['im_opportunities'][0]
        self.assertEqual(first['decision_label'], 'Acheter')
        self.assertEqual(first['decision_tone'], 'orange')
        self.assertEqual(len(first['subscores']), 4)

    def test_build_context_empty(self):
        ctx = ImportMasterDisplayService.build_context()
        self.assertFalse(ctx['im_has_data'])
        self.assertIn('Aucune opportunité', ctx['im_summary_line'])

    def test_home_preview_prioritizes_buy(self):
        _create_opportunity(rank=3, score=70)
        _create_opportunity(
            keyword_text='ventilateur',
            product_name='ventilateur',
            rank=1,
            score=55,
            decision=ImportOpportunity.Decision.WATCH,
        )

        preview = ImportMasterDisplayService.get_home_preview(limit=2)
        self.assertEqual(len(preview), 2)
        self.assertEqual(preview[0]['decision'], ImportOpportunity.Decision.BUY)


class ImportMasterPageTests(TestCase):

    def setUp(self):
        user = get_user_model().objects.create_user(
            username='import-master',
            password='test-password',
        )
        self.client.force_login(user)

    def test_page_renders_with_opportunities(self):
        _create_opportunity()
        response = self.client.get(reverse('intelligence:import_master'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import Master')
        self.assertContains(response, 'Opportunités du jour')
        self.assertContains(response, 'Acheter')
        self.assertContains(response, 'Veille concurrentielle')
        self.assertContains(response, 'Comparaison des prix')

    def test_page_renders_empty_state(self):
        response = self.client.get(reverse('intelligence:import_master'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pas encore d'opportunités calculées")

    def test_recalculate_action_creates_opportunities(self):
        MarketSearchKeyword.objects.update(is_active=False)
        MarketSearchKeyword.objects.create(
            keyword='iphone 15',
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
        )
        response = self.client.post(
            reverse('intelligence:import_master'),
            {'action': 'recalculer'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ImportOpportunity.objects.filter(snapshot_date=timezone.localdate()).count(),
            1,
        )

    def test_sidebar_contains_import_master_link(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('intelligence:import_master'))
