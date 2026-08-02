"""Tests page Import Master — rapport domaines DeepSeek."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from intelligence.models import ImportMasterDomainAnalysis
from intelligence.services.import_master_display_service import ImportMasterDisplayService


class ImportMasterDisplayTests(TestCase):

    def setUp(self):
        ImportMasterDomainAnalysis.objects.all().delete()

    def test_build_context_empty(self):
        ctx = ImportMasterDisplayService.build_context()
        self.assertFalse(ctx['im_domain_has_result'])
        self.assertFalse(ctx['im_domain_running'])

    def test_build_context_with_domain_result(self):
        ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.DONE,
            completed_at=timezone.now(),
            analysis_result={
                'resume': 'Synthèse test',
                'produits_import': [
                    {
                        'rang': 1,
                        'produit': 'iPhone 13',
                        'domaine': 'Tech',
                        'note': 8.5,
                        'recommandation': 'Bon, je vous le recommande',
                        'prix_alibaba_usd': '18–22 USD',
                        'prix_aliexpress_usd': 'Non pertinent',
                        'prix_amazon_usd': 'Non pertinent',
                        'prix_made_in_china_usd': '20–25 USD',
                        'prix_sn_xof': '22 000 – 25 000 XOF',
                    },
                ],
                'classement_domaines': [
                    {'rang': 1, 'domaine': 'Tech', 'note_globale': 8.0},
                ],
            },
        )
        ctx = ImportMasterDisplayService.build_context()
        self.assertTrue(ctx['im_domain_has_result'])
        self.assertEqual(ctx['im_reco_counts']['buy'], 1)
        product = ctx['im_domain_result']['produits_import'][0]
        self.assertEqual(product['prix_alibaba_usd'], '$18 – $22')
        self.assertTrue(product['show_alibaba'])
        self.assertFalse(product['show_aliexpress'])
        self.assertFalse(product['show_amazon'])

    def test_home_preview_from_domain_result(self):
        ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.DONE,
            completed_at=timezone.now(),
            analysis_result={
                'meilleures_opportunites': [
                    {
                        'rang': 1,
                        'produit': 'Produit A',
                        'domaine': 'Tech',
                        'note': 9.0,
                        'recommandation': 'Bon, je vous le recommande',
                    },
                    {
                        'rang': 2,
                        'produit': 'Produit B',
                        'domaine': 'Mode',
                        'note': 5.0,
                        'recommandation': "Peut faire l'affaire mais moyen",
                    },
                ],
            },
        )
        preview = ImportMasterDisplayService.get_home_preview(limit=2)
        self.assertEqual(len(preview), 2)
        self.assertEqual(preview[0]['product_name'], 'Produit A')
        self.assertEqual(preview[0]['decision_tone'], 'orange')


class ImportMasterPageTests(TestCase):

    def setUp(self):
        ImportMasterDomainAnalysis.objects.all().delete()
        user = get_user_model().objects.create_user(
            username='import-master',
            password='test-password',
        )
        self.client.force_login(user)

    def test_page_renders_empty_state(self):
        response = self.client.get(reverse('intelligence:import_master'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import Master')
        self.assertContains(response, 'Aucun rapport disponible')
        self.assertContains(response, 'im-domain-modal')

    def test_page_renders_with_domain_result(self):
        ImportMasterDomainAnalysis.objects.create(
            status=ImportMasterDomainAnalysis.Status.DONE,
            completed_at=timezone.now(),
            analysis_result={
                'resume': 'Marché favorable',
                'produits_import': [
                    {
                        'rang': 1,
                        'produit': 'Couveuse 48',
                        'domaine': 'Élevage',
                        'note': 8.2,
                        'recommandation': 'Bon, je vous le recommande',
                        'prix_sn_xof': '85 000 – 95 000 XOF',
                        'prix_alibaba_usd': '$45 – $55',
                    },
                ],
                'classement_domaines': [],
            },
        )
        response = self.client.get(reverse('intelligence:import_master'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Top 10 produits à importer')
        self.assertContains(response, 'Couveuse 48')
        self.assertNotContains(response, 'WEB SN')
        self.assertNotContains(response, 'im-fiabilite')

    def test_sidebar_contains_import_master_link(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('intelligence:import_master'))
