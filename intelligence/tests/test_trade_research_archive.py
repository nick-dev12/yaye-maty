"""Tests Archives — historique recherches Trade (max 40)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from intelligence.models import MarketDomain, MarketResearchSession
from intelligence.services.trade_research_archive_service import TradeResearchArchiveService


class TradeResearchArchiveServiceTests(TestCase):
    """Ne purge pas toute la table (DB partagée avec le dev)."""

    PREFIX = 'archtest-'

    def setUp(self):
        MarketResearchSession.objects.filter(keyword__startswith=self.PREFIX).delete()
        self.domain = MarketDomain.objects.create(
            slug='telephonie-arch',
            label='Téléphonie Arch',
            cat_id=99,
            is_active=True,
        )

    def tearDown(self):
        MarketResearchSession.objects.filter(keyword__startswith=self.PREFIX).delete()

    def _make_session(self, i: int) -> MarketResearchSession:
        return MarketResearchSession.objects.create(
            domain=self.domain,
            domain_slug=self.domain.slug,
            domain_label=self.domain.label,
            keyword=f'{self.PREFIX}{i}',
            search_query=f'{self.PREFIX}{i} test',
            duration_minutes=10,
            sources=['google'],
            status=MarketResearchSession.Status.DONE,
            completed_at=timezone.now(),
            analysis_result={
                'top_investissement': [
                    {'rang': 1, 'produit': f'Prod {i}', 'note': 8.0, 'recommandation': 'Acheter'},
                ],
            },
        )

    def test_prune_keeps_max_deletes_oldest(self):
        for i in range(12):
            self._make_session(i)
        qs = MarketResearchSession.objects.filter(keyword__startswith=self.PREFIX)
        self.assertEqual(qs.count(), 12)

        deleted = TradeResearchArchiveService.prune_to_limit(10, queryset=qs)
        self.assertEqual(deleted, 2)

        remaining = set(
            MarketResearchSession.objects.filter(keyword__startswith=self.PREFIX)
            .values_list('keyword', flat=True)
        )
        self.assertEqual(len(remaining), 10)
        self.assertNotIn(f'{self.PREFIX}0', remaining)
        self.assertIn(f'{self.PREFIX}11', remaining)

    def test_list_sessions_newest_first(self):
        self._make_session(1)
        self._make_session(2)
        sessions = [
            s for s in TradeResearchArchiveService.list_sessions()
            if (s.keyword or '').startswith(self.PREFIX)
        ]
        self.assertEqual(sessions[0].keyword, f'{self.PREFIX}2')


class ArchivesPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='arch_tester',
            password='testpass123',
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.domain = MarketDomain.objects.create(
            slug='mode-arch',
            label='Mode Arch',
            cat_id=18,
            is_active=True,
        )
        MarketResearchSession.objects.create(
            domain=self.domain,
            domain_slug=self.domain.slug,
            domain_label=self.domain.label,
            keyword='robe',
            search_query='robe Mode Arch Sénégal',
            duration_minutes=10,
            status=MarketResearchSession.Status.DONE,
            completed_at=timezone.now(),
            analysis_result={
                'top_investissement': [
                    {'produit': 'Robe wax', 'note': 9.1, 'recommandation': 'Acheter & Stocker'},
                ],
            },
        )

    def test_archives_page_lists_research(self):
        response = self.client.get(reverse('intelligence:archives'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ARCHIVES RECHERCHES')
        self.assertContains(response, 'Mode Arch')
        self.assertContains(response, 'robe')
        self.assertContains(response, 'Robe wax')
        self.assertContains(response, '/intelligence/?session=')
