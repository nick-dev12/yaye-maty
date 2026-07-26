"""Tests fenêtre temporelle Intelligence — flux actuel vs archives."""

from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from intelligence.services.market_data_window_service import MarketDataWindowService


class MarketDataWindowServiceTests(SimpleTestCase):
    @patch('intelligence.services.market_data_window_service.get_collection_config')
    def test_live_window_uses_campaign_days_when_set(self, mock_config):
        mock_config.return_value = {'CAMPAIGN_DURATION_DAYS': 3}
        self.assertEqual(MarketDataWindowService.get_live_window_days(), 3)

    @patch('intelligence.services.market_data_window_service.get_collection_config')
    def test_live_window_fallback_to_settings_default(self, mock_config):
        mock_config.return_value = {'CAMPAIGN_DURATION_DAYS': 0}
        self.assertEqual(MarketDataWindowService.get_live_window_days(), 3)

    @patch('intelligence.services.market_data_window_service.get_collection_config')
    def test_get_live_since(self, mock_config):
        mock_config.return_value = {'CAMPAIGN_DURATION_DAYS': 3}
        now = timezone.now()
        since = MarketDataWindowService.get_live_since(at=now)
        delta = now - since
        self.assertAlmostEqual(delta.total_seconds(), 3 * 86400, delta=2)
