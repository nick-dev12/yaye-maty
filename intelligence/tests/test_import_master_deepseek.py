"""Tests Import Master — DeepSeek normalize, stop, expire stuck."""

from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from intelligence.models import ImportMasterDomainAnalysis, MarketResearchSession
from intelligence.services.import_master_deepseek_service import ImportMasterDeepSeekService
from intelligence.services.import_master_display_service import ImportMasterDisplayService


class ImportMasterDeepSeekNormalizeTests(TestCase):
    def test_normalize_builds_ranking_from_snapshots(self):
        snapshots = [
            {
                'domaine': 'Téléphonie',
                'top_produits': [
                    {'produit': 'iPhone 13', 'note': 9.0, 'synthese': 'Forte demande.'},
                    {'produit': 'A54', 'note': 7.0},
                ],
            },
            {
                'domaine': 'Mode',
                'top_produits': [{'produit': 'Robe wax', 'note': 6.0}],
            },
        ]
        result = ImportMasterDeepSeekService.normalize_result({}, snapshots)
        self.assertGreaterEqual(len(result['classement_domaines']), 2)
        self.assertEqual(result['classement_domaines'][0]['recommandation'], 'Bon, je vous le recommande')
        self.assertTrue(result['produits_import'])
        self.assertEqual(result['produits_import'][0]['produit'], 'iPhone 13')
        self.assertLessEqual(len(result['produits_import']), 10)

    def test_normalize_reco_alignment(self):
        data = {
            'classement_domaines': [
                {'domaine': 'A', 'note_globale': 8.0, 'recommandation': 'À éviter'},
                {'domaine': 'B', 'note_globale': 3.0, 'recommandation': 'Bon, je vous le recommande'},
            ],
            'produits_import': [
                {'produit': 'X', 'domaine': 'A', 'note': 6.0, 'recommandation': 'À éviter'},
            ],
            'meilleures_opportunites': [
                {'titre': 'Opp', 'produit': 'X', 'note': 9.0, 'recommandation': 'Surveiller'},
            ],
        }
        result = ImportMasterDeepSeekService.normalize_result(data, [])
        self.assertEqual(result['classement_domaines'][0]['recommandation'], 'Bon, je vous le recommande')
        self.assertEqual(result['classement_domaines'][1]['recommandation'], 'À éviter')
        self.assertEqual(result['produits_import'][0]['recommandation'], "Peut faire l'affaire mais moyen")
        self.assertEqual(result['meilleures_opportunites'][0]['recommandation'], 'Bon, je vous le recommande')

    def test_normalize_sn_price_range_and_top10(self):
        products = []
        for i in range(15):
            products.append({
                'produit': f'Produit {i}',
                'domaine': 'Agri' if i % 2 == 0 else 'Mode',
                'note': 9.5 - i * 0.2,
                'prix_sn_min_xof': 25000,
                'prix_sn_max_xof': 22000,  # inversé → swap
                'prix_landed_xof': 15000,
                'marge_pct': 95,  # absurde → recalcul
                'sources_prix': ['jumia.sn', 'alibaba.com'],
            })
        result = ImportMasterDeepSeekService.normalize_result(
            {'produits_import': products, 'classement_domaines': [
                {'domaine': 'Agri', 'note_globale': 8.0},
                {'domaine': 'Mode', 'note_globale': 7.0},
            ]},
            [],
        )
        self.assertEqual(len(result['produits_import']), 10)
        self.assertEqual(result['produits_import'][0]['rang'], 1)
        top = result['produits_import'][0]
        self.assertEqual(top['prix_sn_min_xof'], 22000)
        self.assertEqual(top['prix_sn_max_xof'], 25000)
        self.assertIn('22 000', top['prix_sn_xof'])
        self.assertIn('25 000', top['prix_sn_xof'])
        self.assertLessEqual(float(top['marge_pct']), 80)
        self.assertIn(top['fiabilite_prix'], ('web', 'estime', 'faible'))
        self.assertEqual(top['fiabilite_prix'], 'web')

    def test_snapshots_for_ai_prompt_strips_bdd(self):
        snapshots = [{
            'domaine': 'Test',
            'prix_locaux_bdd': [{'produit': 'X', 'min_xof': 1000}],
            'top_produits': [{
                'produit': 'Widget',
                'note': 8.0,
                'prix_locaux_bdd': {'min_xof': 500},
            }],
            'sessions': [{
                'top_produits': [{
                    'produit': 'Widget',
                    'prix_locaux_bdd': {'min_xof': 500},
                }],
            }],
        }]
        clean = ImportMasterDeepSeekService._snapshots_for_ai_prompt(snapshots)
        self.assertNotIn('prix_locaux_bdd', clean[0])
        self.assertNotIn('prix_locaux_bdd', clean[0]['top_produits'][0])
        self.assertNotIn('prix_locaux_bdd', clean[0]['sessions'][0]['top_produits'][0])

    def test_parse_range_from_text(self):
        lo, hi = ImportMasterDeepSeekService._parse_range_from_text('95–120k XOF')
        self.assertEqual(lo, 95000)
        self.assertEqual(hi, 120000)
        lo2, hi2 = ImportMasterDeepSeekService._parse_range_from_text('22 000 - 25 000')
        self.assertEqual(lo2, 22000)
        self.assertEqual(hi2, 25000)

    def test_format_sn_range(self):
        text = ImportMasterDeepSeekService._format_sn_range(22000, 25000)
        self.assertEqual(text, '22 000 – 25 000 XOF')

    def test_sanitize_public_comment_strips_site_names(self):
        text = ImportMasterDeepSeekService._sanitize_public_comment(
            'forte demande et bons signaux Jumia/Jiji — candidate à stocker.',
        )
        self.assertNotIn('Jumia', text)
        self.assertNotIn('Jiji', text)
        self.assertIn('marché local', text.lower())

    def test_opportunities_capped_at_five(self):
        products = [
            {'produit': f'P{i}', 'domaine': 'Tech', 'note': 9 - i * 0.1}
            for i in range(8)
        ]
        result = ImportMasterDeepSeekService.normalize_result(
            {
                'produits_import': products,
                'meilleures_opportunites': [
                    {'produit': f'P{i}', 'note': 9 - i * 0.1, 'commentaire': 'ok Jumia'}
                    for i in range(8)
                ],
            },
            [],
        )
        self.assertEqual(len(result['meilleures_opportunites']), 5)
        for opp in result['meilleures_opportunites']:
            self.assertNotIn('Jumia', opp.get('commentaire') or '')

    def test_coerce_usd_display_uses_dollar_not_usd_suffix(self):
        self.assertEqual(
            ImportMasterDeepSeekService._coerce_usd_display('18–22 USD'),
            '$18 – $22',
        )
        self.assertEqual(
            ImportMasterDeepSeekService._resolve_platform_price('Non pertinent'),
            '',
        )
        self.assertEqual(
            ImportMasterDeepSeekService._coerce_usd_display('', lo=20, hi=25),
            '$20 – $25',
        )

    def test_polish_hides_missing_platform_prices(self):
        result = ImportMasterDeepSeekService.polish_result_for_display({
            'produits_import': [{
                'prix_alibaba_usd': '18–22 USD',
                'prix_alibaba_usd_min': 18,
                'prix_alibaba_usd_max': 22,
                'prix_aliexpress_usd': 'Non pertinent',
                'prix_amazon_usd': 'Non pertinent',
                'prix_made_in_china_usd': '20–25 USD',
            }],
        })
        p = result['produits_import'][0]
        self.assertEqual(p['prix_alibaba_usd'], '$18 – $22')
        self.assertTrue(p['show_alibaba'])
        self.assertEqual(p['prix_aliexpress_usd'], '')
        self.assertFalse(p['show_aliexpress'])
        self.assertEqual(p['prix_amazon_usd'], '')
        self.assertFalse(p['show_amazon'])
        self.assertNotIn('prix_made_in_china_usd', p)

    def test_normalize_does_not_invent_platform_prices(self):
        result = ImportMasterDeepSeekService.normalize_result(
            {
                'produits_import': [{
                    'produit': 'Widget',
                    'domaine': 'Tech',
                    'note': 8.0,
                    'prix_alibaba_usd': '18–22 USD',
                    'prix_aliexpress_usd': 'Non pertinent',
                    'prix_amazon_usd': '',
                }],
            },
            [],
        )
        p = result['produits_import'][0]
        self.assertTrue(p['show_alibaba'])
        self.assertFalse(p['show_aliexpress'])
        self.assertFalse(p['show_amazon'])
        self.assertEqual(p['prix_aliexpress_usd'], '')

    def test_import_web_preferred_includes_made_in_china_only_for_im(self):
        domains = ImportMasterDeepSeekService.IMPORT_WEB_PREFERRED_DOMAINS
        self.assertIn('made-in-china.com', domains)
        self.assertIn('jumia.sn', domains)
        self.assertIn('jemba.sn', domains)
        self.assertIn('alibaba.com', domains)
        self.assertIn('1688.com', domains)
        self.assertIn('dhgate.com', domains)
        self.assertIn('globalsources.com', domains)
        # Sourcing giants absents de la veille Trade Intelligence (.env / settings)
        from django.conf import settings
        ti_domains = list(
            (getattr(settings, 'DEEPSEEK', {}) or {}).get('WEB_ALLOWED_DOMAINS') or []
        )
        for forbidden in (
            'made-in-china.com', 'alibaba.com', 'aliexpress.com', 'amazon.com',
            '1688.com', 'dhgate.com', 'globalsources.com',
        ):
            self.assertNotIn(forbidden, ti_domains)
        # Sites SN locaux présents côté TI
        for sn in ('jemba.sn', 'dakarcenter.com', 'occasiondakar.com', 'taftaf.sn'):
            self.assertIn(sn, ti_domains)


class ImportMasterStopAndExpireTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='imtester', password='pass12345',
        )
        self.client = Client()
        self.client.login(username='imtester', password='pass12345')

    def test_expire_stuck_pending(self):
        old = ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.PENDING,
            progress_message='File…',
        )
        ImportMasterDomainAnalysis.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(minutes=20),
        )
        n = ImportMasterDisplayService.expire_stuck_analyses(max_age_minutes=15)
        self.assertEqual(n, 1)
        old.refresh_from_db()
        self.assertEqual(old.status, ImportMasterDomainAnalysis.Status.FAILED)

    def test_stop_analysis_endpoint(self):
        analysis = ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.RUNNING,
            celery_task_id='fake-task-id',
            progress_percent=10,
            progress_message='En cours…',
        )
        with patch(
            'intelligence.services.collection_cancel_service.CollectionCancelService.request_cancel'
        ), patch('yayematy_project.celery.app.control.revoke'):
            resp = self.client.post(
                reverse('intelligence:import_master'),
                {'action': 'arreter_analyse'},
            )
        self.assertEqual(resp.status_code, 302)
        analysis.refresh_from_db()
        self.assertEqual(analysis.status, ImportMasterDomainAnalysis.Status.STOPPED)

    def test_page_shows_stop_button_when_running(self):
        ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.RUNNING,
            progress_message='En cours…',
        )
        resp = self.client.get(reverse('intelligence:import_master'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Arrêter l’analyse')
        self.assertContains(resp, 'arreter_analyse')

    def test_page_launch_available_when_stopped(self):
        ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.STOPPED,
            progress_message='Arrêtée',
        )
        resp = self.client.get(reverse('intelligence:import_master'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Lancer l’analyse comparative')
        self.assertContains(resp, 'im-domain-modal')
        self.assertNotContains(resp, 'Arrêter l’analyse')

    def test_launch_requires_domain_selection(self):
        resp = self.client.post(
            reverse('intelligence:import_master'),
            {'action': 'analyser_domaines'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            ImportMasterDomainAnalysis.objects.filter(
                status=ImportMasterDomainAnalysis.Status.PENDING,
            ).exists()
        )


class ImportMasterCollectSnapshotsTests(TestCase):
    def test_collect_returns_list(self):
        snaps = ImportMasterDeepSeekService.collect_domain_snapshots()
        self.assertIsInstance(snaps, list)
        for snap in snaps:
            self.assertIn('domaine', snap)
            self.assertIn('top_produits', snap)
            self.assertIn('sessions', snap)

    def test_collect_limits_one_session_per_domain(self):
        slug = 'test-im-tech-isolated'
        MarketResearchSession.objects.filter(domain_slug=slug).delete()
        analysis = {
            'top_investissement': [
                {'rang': 1, 'produit': 'Produit A', 'note': 8.0, 'synthese': 'OK'},
            ],
        }
        for i in range(3):
            MarketResearchSession.objects.create(
                domain_slug=slug,
                domain_label='Tech Test IM',
                search_query='tech SN',
                status=MarketResearchSession.Status.DONE,
                analysis_result=analysis,
                completed_at=timezone.now() - timedelta(hours=i),
            )
        snaps = [
            s for s in ImportMasterDeepSeekService.collect_domain_snapshots(
                sessions_per_domain=1,
            )
            if s['domain_slug'] == slug
        ]
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]['sessions_count'], 1)
        self.assertEqual(len(snaps[0]['sessions']), 1)
        MarketResearchSession.objects.filter(domain_slug=slug).delete()