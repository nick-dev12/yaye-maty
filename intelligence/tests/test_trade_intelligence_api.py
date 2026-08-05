"""Tests API Trade Intelligence — domaine + mot-clé + durée."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from intelligence.models import MarketDomain, MarketResearchSession
from intelligence.services.market_research_orchestrator import MarketResearchOrchestrator


class TradeIntelligenceApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='trade_tester',
            password='testpass123',
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.domain = MarketDomain.objects.create(
            slug='telephonie',
            label='Téléphonie',
            cat_id=13,
            is_active=True,
        )

    def test_index_page_loads(self):
        response = self.client.get(reverse('intelligence:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SENEGAL TRADE INTELLIGENCE')
        self.assertContains(response, 'TOP 15 PRODUITS')
        self.assertContains(response, 'DOMAINES')
        self.assertContains(response, 'ti-domain-modal')
        self.assertContains(response, 'DURÉE')
        self.assertNotContains(response, 'CATÉGORIE')

    @patch('intelligence.controllers.trade_intelligence_controller.run_market_research_session')
    def test_api_lancer_keyword_optional(self, mock_task):
        mock_task.delay.return_value.id = 'task-no-kw'
        response = self.client.post(
            reverse('intelligence:trade_api_lancer'),
            data=json.dumps({'domain_slug': 'telephonie', 'keyword': '', 'duration_minutes': 10}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_api_lancer_requires_domain(self):
        response = self.client.post(
            reverse('intelligence:trade_api_lancer'),
            data=json.dumps({'domain_slug': '', 'keyword': 'iphone'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @patch('intelligence.controllers.trade_intelligence_controller.run_market_research_session')
    def test_api_lancer_batch_domains(self, mock_task):
        MarketDomain.objects.create(
            slug='mode',
            label='Mode',
            cat_id=14,
            is_active=True,
        )
        mock_task.delay.side_effect = [
            type('T', (), {'id': 'task-1'})(),
            type('T', (), {'id': 'task-2'})(),
        ]
        response = self.client.post(
            reverse('intelligence:trade_api_lancer'),
            data=json.dumps({
                'domain_slugs': ['telephonie', 'mode'],
                'duration_minutes': 10,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['batch'])
        self.assertEqual(data['count'], 2)
        self.assertEqual(len(data['sessions']), 2)
        self.assertEqual(mock_task.delay.call_count, 2)

    def test_create_session(self):
        session = MarketResearchOrchestrator.create_session(
            'telephonie',
            'iPhone 14',
            duration_minutes=30,
            sources=['jumia', 'tiktok'],
        )
        self.assertEqual(session.domain_slug, 'telephonie')
        self.assertEqual(session.keyword, 'iPhone 14')
        self.assertEqual(session.duration_minutes, 30)
        self.assertEqual(session.sources, ['jumia', 'tiktok'])
        self.assertIn('iPhone 14', session.search_query)
        self.assertEqual(session.status, MarketResearchSession.Status.PENDING)

    @patch('intelligence.controllers.trade_intelligence_controller.run_market_research_session')
    def test_api_lancer_success(self, mock_task):
        mock_task.delay.return_value.id = 'fake-task-id'
        response = self.client.post(
            reverse('intelligence:trade_api_lancer'),
            data=json.dumps({
                'domain_slug': 'telephonie',
                'keyword': 'Samsung A15',
                'duration_minutes': 10,
                'sources': ['google'],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['task_id'], 'fake-task-id')

    def test_api_arreter(self):
        response = self.client.post(
            reverse('intelligence:trade_api_arreter'),
            data=json.dumps({'task_id': 'abc-123'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_parametres_redirects(self):
        response = self.client.get(reverse('settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/intelligence/', response.url)

    def test_collecte_redirects(self):
        response = self.client.get(reverse('intelligence:collecte'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/intelligence/', response.url)

    def test_session_test_page_loads(self):
        response = self.client.get(reverse('intelligence:collecte_test'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tester Google Trends')
        self.assertContains(response, 'Tester Jumia')
        self.assertContains(response, 'Tester Jiji')
        self.assertContains(response, 'Tester TikTok')
        self.assertNotContains(response, 'Tester Facebook')
        self.assertNotContains(response, 'MOT-CLÉ')
        self.assertContains(response, 'DURÉE')
