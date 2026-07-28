"""Tests planification collecte et anti-doublon."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from intelligence.collection_config import is_collection_schedule_active
from intelligence.services.social_dedup_service import SocialDedupService


class CollectionScheduleActiveTests(SimpleTestCase):
    @patch('intelligence.collection_config.get_collection_config')
    def test_permanent_when_no_campaign(self, mock_config):
        mock_config.return_value = {
            'ENABLED': True,
            'CAMPAIGN_START': '',
            'CAMPAIGN_DURATION_DAYS': 0,
        }
        active, reason = is_collection_schedule_active()
        self.assertTrue(active)
        self.assertIn('permanente', reason)

    @patch('intelligence.collection_config.get_collection_config')
    def test_campaign_window_three_days(self, mock_config):
        start = date.today()
        mock_config.return_value = {
            'ENABLED': True,
            'CAMPAIGN_START': start.isoformat(),
            'CAMPAIGN_DURATION_DAYS': 3,
        }
        active, _ = is_collection_schedule_active(
            at=timezone.make_aware(datetime.combine(start, datetime.min.time()))
        )
        self.assertTrue(active)

        after = start + timedelta(days=4)
        active, reason = is_collection_schedule_active(
            at=timezone.make_aware(datetime.combine(after, datetime.min.time()))
        )
        self.assertFalse(active)
        self.assertIn('terminée', reason)

    @patch.dict(
        'yayematy_project.settings.COLLECTION_SCHEDULE',
        {'ENABLED': False, 'CAMPAIGN_START': '', 'CAMPAIGN_DURATION_DAYS': 0},
        clear=False,
    )
    def test_disabled_stops_scheduled_sessions(self):
        active, reason = is_collection_schedule_active()
        self.assertFalse(active)
        self.assertIn('COLLECTION_ENABLED=False', reason)


class SocialDedupServiceTests(TestCase):
    def test_filter_new_urls_skips_known_tiktok(self):
        from intelligence.models import SocialPost

        SocialPost.objects.create(
            platform='tiktok',
            platform_post_id='7123456789012345678',
            source_url='https://www.tiktok.com/search?q=test',
            content='Publication test',
            content_hash='abc123',
        )
        urls = [
            'https://www.tiktok.com/@user/video/7123456789012345678',
            'https://www.tiktok.com/@user/video/7999999999999999999',
        ]
        fresh = SocialDedupService.filter_new_urls('tiktok', urls)
        self.assertEqual(len(fresh), 1)
        self.assertIn('7999999999999999999', fresh[0])
