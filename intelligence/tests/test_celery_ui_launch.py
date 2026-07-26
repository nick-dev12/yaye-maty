"""Lancement Celery depuis l'interface — dev local."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(CELERY_UI_LAUNCH=True)
class CeleryUiLaunchApiTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username='celery-ui',
            password='test-password',
        )
        self.client.force_login(self.user)

    def test_collecte_page_shows_celery_panel_when_enabled(self):
        response = self.client.get(reverse('intelligence:collecte'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Services Celery (local)')
        self.assertContains(response, 'Démarrer worker')

    @patch('intelligence.services.celery_ui_launch_service.celery_workers_online', return_value=(False, 'offline'))
    @patch('intelligence.services.celery_ui_launch_service.subprocess.Popen')
    @patch('intelligence.services.celery_ui_launch_service.CeleryUiLaunchService._ensure_redis')
    def test_start_worker_api(self, _redis, popen_mock, _ping):
        process = MagicMock()
        process.pid = 4242
        popen_mock.return_value = process

        response = self.client.post(
            reverse('intelligence:collecte_api_celery_start'),
            data='{"component":"worker"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertIn('4242', payload['message'])

    @override_settings(CELERY_UI_LAUNCH=False)
    def test_api_disabled_when_setting_off(self):
        response = self.client.get(reverse('intelligence:collecte_api_celery_status'))
        self.assertEqual(response.status_code, 403)
