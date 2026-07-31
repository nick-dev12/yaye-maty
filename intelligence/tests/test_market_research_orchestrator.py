"""Tests orchestrateur Trade — boucle durée + stop→analyse."""

from unittest.mock import patch

from django.test import TestCase

from intelligence.models import MarketDomain, MarketResearchSession
from intelligence.services.market_research_orchestrator import MarketResearchOrchestrator
from intelligence.services.trade_research_collection_service import TradeResearchCollectionService


class TradeResearchAggregateTests(TestCase):
    def test_aggregate_payload_empty(self):
        payload = TradeResearchCollectionService.aggregate_payload(
            'Apple téléphone Sénégal',
            collect_results={},
        )
        self.assertEqual(payload['search_query'], 'Apple téléphone Sénégal')
        self.assertIn('jumia', payload)
        self.assertIn('jiji', payload)
        self.assertIn('social', payload)


class MarketResearchOrchestratorTests(TestCase):
    def setUp(self):
        self.domain = MarketDomain.objects.create(
            slug='mode',
            label='Mode',
            cat_id=18,
            is_active=True,
        )

    def test_create_rejects_invalid_domain(self):
        with self.assertRaises(ValueError):
            MarketResearchOrchestrator.create_session('inconnu', 'robe')

    @patch('intelligence.services.market_research_orchestrator.LANE_PAUSE_SECONDS', 0.01)
    @patch('intelligence.services.market_research_orchestrator.ROUND_PAUSE_SECONDS', 0.01)
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_trends')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_jumia')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_jiji')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_tiktok')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.aggregate_payload')
    @patch('intelligence.services.market_research_orchestrator.DeepSeekAnalysisService.is_enabled', return_value=False)
    def test_run_session_loops_source_until_stop(
        self, _enabled, mock_agg, mock_tt, mock_jiji, mock_jumia, mock_trends,
    ):
        mock_trends.return_value = {'success': True, 'series': []}
        mock_agg.return_value = {'search_query': 'test', 'jumia': {'products': []}}
        calls = {'n': 0}

        def trends_side(*_a, **_k):
            calls['n'] += 1
            return {'success': True, 'series': []}

        mock_trends.side_effect = trends_side

        def should_cancel():
            return calls['n'] >= 3

        session = MarketResearchOrchestrator.create_session(
            'mode', '', duration_minutes=10, sources=['google'],
        )
        result = MarketResearchOrchestrator.run_session(
            session.pk, should_cancel=should_cancel,
        )
        session.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(session.status, MarketResearchSession.Status.DONE)
        self.assertGreaterEqual(calls['n'], 3)
        mock_jumia.assert_not_called()
        mock_jiji.assert_not_called()
        mock_tt.assert_not_called()

    @patch('intelligence.services.market_research_orchestrator.LANE_PAUSE_SECONDS', 0.01)
    @patch('intelligence.services.market_research_orchestrator.ROUND_PAUSE_SECONDS', 0.01)
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_trends')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_jumia')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_jiji')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_tiktok')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.aggregate_payload')
    @patch('intelligence.services.market_research_orchestrator.DeepSeekAnalysisService.is_enabled', return_value=False)
    def test_run_session_parallel_lanes(
        self, _enabled, mock_agg, mock_tt, mock_jiji, mock_jumia, mock_trends,
    ):
        mock_trends.return_value = {'success': True, 'series': []}
        mock_jumia.return_value = {'success': True, 'products': []}
        mock_jiji.return_value = {'success': True, 'listings': []}
        mock_tt.return_value = {'success': True, 'posts': []}
        mock_agg.return_value = {'search_query': 'test', 'jumia': {'products': []}}
        seen = {'n': 0}

        def should_cancel():
            seen['n'] += 1
            return seen['n'] >= 40

        session = MarketResearchOrchestrator.create_session(
            'mode', '',
            duration_minutes=10,
            sources=['google', 'jumia', 'jiji', 'tiktok'],
        )
        result = MarketResearchOrchestrator.run_session(
            session.pk, should_cancel=should_cancel,
        )
        session.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(session.status, MarketResearchSession.Status.DONE)
        self.assertTrue(mock_trends.called)
        self.assertTrue(mock_jumia.called or mock_jiji.called)
        self.assertTrue(mock_tt.called)

    def test_build_lanes_bounded(self):
        lanes = MarketResearchOrchestrator._build_lanes(
            ['google', 'jumia', 'jiji', 'tiktok']
        )
        self.assertEqual(
            lanes, ['trends', 'marketplaces', 'tiktok', 'deepseek_web'],
        )
        # Jumia+Jiji = une seule lane marketplaces
        self.assertEqual(lanes.count('marketplaces'), 1)

    @patch('intelligence.services.market_research_orchestrator.LANE_PAUSE_SECONDS', 0.01)
    @patch('intelligence.services.market_research_orchestrator.ROUND_PAUSE_SECONDS', 0.01)
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.collect_trends')
    @patch('intelligence.services.market_research_orchestrator.TradeResearchCollectionService.aggregate_payload')
    @patch('intelligence.services.market_research_orchestrator.DeepSeekAnalysisService.is_enabled', return_value=False)
    def test_stop_still_analyzes(self, _enabled, mock_agg, mock_trends):
        mock_trends.return_value = {'success': True, 'series': []}
        mock_agg.return_value = {'search_query': 'x', 'jumia': {'products': [{'name': 'Prod'}]}}

        cancel_flag = {'v': False}

        def should_cancel():
            return cancel_flag['v']

        def progress(pct, msg, phase='collecte'):
            cancel_flag['v'] = True

        session = MarketResearchOrchestrator.create_session(
            'mode', '', duration_minutes=10, sources=['google', 'jumia'],
        )
        result = MarketResearchOrchestrator.run_session(
            session.pk, progress=progress, should_cancel=should_cancel,
        )
        session.refresh_from_db()
        self.assertTrue(result['success'])
        self.assertEqual(session.status, MarketResearchSession.Status.DONE)
        self.assertTrue(result.get('stop_reason'))
