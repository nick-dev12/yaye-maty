"""Contrats API de la page Collecte manuelle."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from intelligence.services.collection_task_session_service import SESSION_KEY_TEST
from intelligence.services.test_data_window_service import TestDataWindowService


class CollectionControlStatusApiTests(TestCase):
    """Le navigateur doit distinguer fin normale et résultat partiel."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username='collection-api-test',
            password='test-password',
        )
        self.client.force_login(self.user)

    def test_success_cancelled_exposes_partial_and_closes_test_window(self):
        task_id = '11111111-1111-1111-1111-111111111111'
        session = self.client.session
        session[SESSION_KEY_TEST] = {
            'task_id': task_id,
            'test_mode': True,
            'job': 'social',
            'queued_at': '2026-07-25T20:00:00+00:00',
        }
        session[TestDataWindowService.SESSION_KEY] = {
            'started_at': '2026-07-25T20:00:00+00:00',
            'ended_at': None,
            'job': 'social',
        }
        session.save()

        result = Mock(
            state='SUCCESS',
            result={
                'pourcentage': 100,
                'message': 'Collecte interrompue puis analysée.',
                'nouvelles_donnees': 7,
                'phase': 'done',
                'details': {'cancelled': True, 'nouvelles_donnees': 7},
            },
        )
        with patch(
            'intelligence.controllers.collection_control_controller.AsyncResult',
            return_value=result,
        ):
            response = self.client.get(
                reverse('intelligence:collecte_api_statut', kwargs={'task_id': task_id})
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['cancelled'])
        self.assertTrue(payload['partial'])
        self.assertEqual(payload['resultats'], 7)

        session = self.client.session
        self.assertNotIn(SESSION_KEY_TEST, session)
        self.assertIsNotNone(
            session[TestDataWindowService.SESSION_KEY]['ended_at']
        )

    def test_pending_busy_worker_is_not_mistaken_for_orphan(self):
        task_id = '22222222-2222-2222-2222-222222222222'
        result = Mock(state='PENDING')

        with (
            patch(
                'intelligence.controllers.collection_control_controller.AsyncResult',
                return_value=result,
            ),
            patch(
                'intelligence.services.collection_task_session_service.'
                'CollectionTaskSessionService.is_pending_stale',
                return_value=True,
            ),
            patch(
                'intelligence.services.celery_health_service.celery_workers_online',
                return_value=(True, 'Worker actif'),
            ),
            patch(
                'intelligence.services.collection_task_session_service.'
                'CollectionTaskSessionService.liberate_task'
            ) as liberate,
        ):
            response = self.client.get(
                reverse('intelligence:collecte_api_statut', kwargs={'task_id': task_id})
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['etat'], 'PENDING')
        liberate.assert_not_called()

    def test_reset_active_requests_cancel_but_keeps_session_for_finalization(self):
        task_id = '33333333-3333-3333-3333-333333333333'
        session = self.client.session
        session[SESSION_KEY_TEST] = {
            'task_id': task_id,
            'test_mode': True,
            'job': 'jumia',
            'queued_at': '2026-07-25T20:00:00+00:00',
        }
        session.save()

        with (
            patch(
                'intelligence.controllers.collection_control_controller.AsyncResult',
                return_value=Mock(state='PROGRESS'),
            ),
            patch(
                'intelligence.controllers.collection_control_controller.'
                'CollectionCancelService.request_cancel'
            ) as request_cancel,
            patch(
                'intelligence.controllers.collection_control_controller.'
                'CollectionTaskSessionService.liberate_task'
            ) as liberate,
            patch(
                'intelligence.services.celery_health_service.celery_workers_online',
                return_value=(True, 'Worker actif'),
            ),
        ):
            response = self.client.post(
                reverse('intelligence:collecte_api_reset_session'),
                data=json.dumps({'test_mode': True, 'task_id': task_id}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['cancelling'])
        self.assertFalse(response.json()['session_released'])
        request_cancel.assert_called_once_with(task_id)
        liberate.assert_not_called()
        self.assertIn(SESSION_KEY_TEST, self.client.session)

