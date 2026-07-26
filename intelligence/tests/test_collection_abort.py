"""
Vérifie que l'arrêt demandé depuis le tableau de bord est honoré rapidement
par tous les types de collecte (Google Trends, réseaux, Jumia, Jiji, pipeline).
"""

from __future__ import annotations

import time

from django.test import SimpleTestCase

from intelligence.scrapers.human_behavior import random_sleep
from intelligence.services.collection_abort import (
    CANCEL_POLL_SECONDS,
    CollectionAborted,
    abort_requested,
    interruptible_sleep,
    reset_abort_hook,
    set_abort_hook,
)

MAX_REACTION_SECONDS = 1.5


class CollectionAbortHookTests(SimpleTestCase):
    """Le hook global doit interrompre les pauses anti-bot des scrapers."""

    def tearDown(self) -> None:
        # Sécurité : aucun hook ne doit fuiter entre les tests.
        token = set_abort_hook(None)
        reset_abort_hook(token)

    def test_sans_hook_aucune_annulation(self):
        self.assertFalse(abort_requested())
        interruptible_sleep(0.05)

    def test_pause_longue_interrompue_rapidement(self):
        token = set_abort_hook(lambda: True)
        try:
            started = time.monotonic()
            with self.assertRaises(CollectionAborted):
                interruptible_sleep(120)
            self.assertLess(time.monotonic() - started, MAX_REACTION_SECONDS)
        finally:
            reset_abort_hook(token)

    def test_annulation_pendant_la_pause(self):
        """Arrêt demandé après le démarrage de la pause (cas réel de l'UI)."""
        deadline = time.monotonic() + 0.5
        token = set_abort_hook(lambda: time.monotonic() >= deadline)
        try:
            started = time.monotonic()
            with self.assertRaises(CollectionAborted):
                interruptible_sleep(60)
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.4)
            self.assertLess(elapsed, 0.5 + MAX_REACTION_SECONDS)
        finally:
            reset_abort_hook(token)

    def test_random_sleep_des_scrapers_est_annulable(self):
        """random_sleep est partagé par TikTok, Facebook, Jumia et Jiji."""
        token = set_abort_hook(lambda: True)
        try:
            started = time.monotonic()
            with self.assertRaises(CollectionAborted):
                random_sleep(30.0, 90.0)
            self.assertLess(time.monotonic() - started, MAX_REACTION_SECONDS)
        finally:
            reset_abort_hook(token)

    def test_hook_defaillant_ne_casse_pas_la_collecte(self):
        """Une panne Redis ne doit pas interrompre une collecte en cours."""
        def broken_hook() -> bool:
            raise RuntimeError('Redis indisponible')

        token = set_abort_hook(broken_hook)
        try:
            self.assertFalse(abort_requested())
            interruptible_sleep(CANCEL_POLL_SECONDS)
        finally:
            reset_abort_hook(token)

    def test_abort_est_une_base_exception(self):
        """Les `except Exception` défensifs des scrapers ne doivent pas l'avaler."""
        self.assertTrue(issubclass(CollectionAborted, BaseException))
        self.assertFalse(issubclass(CollectionAborted, Exception))


class ManualCollectionAbortTests(SimpleTestCase):
    """L'arrêt profond est converti en résultat partiel, pas en échec brut."""

    def test_run_job_convertit_abort_en_resultat_partiel(self):
        from intelligence.services import manual_collection_service as mod
        from intelligence.services.manual_collection_service import ManualCollectionService

        original = ManualCollectionService.run_jumia
        mod.ManualCollectionService.run_jumia = classmethod(
            lambda cls, **kwargs: (_ for _ in ()).throw(CollectionAborted())
        )
        try:
            result = ManualCollectionService.run_job(
                ManualCollectionService.JOB_JUMIA,
                auto_nlp_after=False,
                test_mode=True,
            )
        finally:
            mod.ManualCollectionService.run_jumia = original

        self.assertTrue(result['cancelled'])
        self.assertEqual(result['job'], ManualCollectionService.JOB_JUMIA)
        self.assertIn('interrompue', result['message'].lower())


class GoogleTrendsAbortTests(SimpleTestCase):
    """La découverte Google Trends doit s'arrêter pendant ses pauses longues."""

    def test_pause_entre_seeds_annulable(self):
        from intelligence.controllers.domain_discovery_controller import (
            DomainDiscoveryCancelled,
            DomainDiscoveryController,
        )

        controller = DomainDiscoveryController(should_cancel=lambda: True)
        started = time.monotonic()
        with self.assertRaises(DomainDiscoveryCancelled):
            controller._interruptible_sleep(120)
        self.assertLess(time.monotonic() - started, MAX_REACTION_SECONDS)
