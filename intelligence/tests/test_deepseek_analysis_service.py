"""Tests DeepSeekAnalysisService — validation JSON sans appel réseau."""

from django.test import SimpleTestCase, override_settings

from intelligence.services.deepseek_analysis_service import DeepSeekAnalysisService


@override_settings(
    DEEPSEEK={
        'API_KEY': 'test-key',
        'MODEL': 'deepseek-v4-flash',
        'BASE_URL': 'https://api.deepseek.com',
        'ANTHROPIC_BASE_URL': 'https://api.deepseek.com/anthropic',
        'ENABLED': True,
        'MAX_TOKENS': 8192,
        'TIMEOUT_SECONDS': 30,
        'WEB_ALLOWED_DOMAINS': [
            'jumia.sn', 'jiji.sn', 'alibaba.com', 'aliexpress.com',
            'amazon.com', 'tiktok.com',
        ],
        'WEB_BLOCKED_DOMAINS': [],
        'WEB_MAX_USES': 5,
        'WEB_COUNTRY': 'SN',
        'WEB_CITY': 'Dakar',
        'WEB_TIMEZONE': 'Africa/Dakar',
    }
)
class DeepSeekAnalysisServiceTests(SimpleTestCase):
    def test_validate_result_normalizes_items(self):
        raw = {
            'top_investissement': [
                {
                    'rang': 1,
                    'produit': 'iPhone 14',
                    'note': 9.5,
                    'recommandation': 'Acheter & Stocker',
                    'synthese': 'Forte demande.',
                    'sources': ['jumia'],
                }
            ],
        }
        result = DeepSeekAnalysisService.validate_result(raw)
        self.assertEqual(len(result['top_investissement']), 1)
        self.assertEqual(result['top_investissement'][0]['note'], 9.5)
        self.assertIn('plus_recherche', result)

    def test_validate_clamps_note(self):
        raw = {'top_investissement': [{'produit': 'X', 'note': 15}]}
        result = DeepSeekAnalysisService.validate_result(raw)
        self.assertEqual(result['top_investissement'][0]['note'], 10.0)

    def test_ensure_top_always_fifteen(self):
        raw = {
            'top_investissement': [
                {'produit': 'Samsung A13', 'note': 9.0},
                {'produit': 'Tecno Spark 9', 'note': 3.2},
            ],
            'plus_recherche': [{'produit': 'Infinix Hot 11', 'note': 2.1}],
        }
        payload = {
            'jumia': {'products': [
                {'name': f'Phone Jumia {i}'} for i in range(1, 8)
            ]},
            'jiji': {'listings': [{'title': 'Xiaomi Redmi Note 11'}]},
        }
        result = DeepSeekAnalysisService.ensure_top10(
            DeepSeekAnalysisService.validate_result(raw),
            payload=payload,
            domain_label='Telephone et tablette',
            category_label='smartphone',
        )
        for key in ('top_investissement', 'plus_recherche', 'plus_aime', 'vitesse_vente'):
            self.assertEqual(len(result[key]), 15, key)
            self.assertEqual(result[key][0]['rang'], 1)
            self.assertEqual(result[key][-1]['rang'], 15)
        self.assertLessEqual(result['top_investissement'][1]['note'], 10.0)

    def test_fallback_result_always_fifteen(self):
        payload = {
            'jumia': {'products': [{'name': f'Produit {i}'} for i in range(1, 6)]},
            'jiji': {'listings': [{'title': f'Annonce {i}'} for i in range(1, 4)]},
        }
        result = DeepSeekAnalysisService.fallback_result(
            payload,
            domain_label='Téléphonie',
            category_label='Samsung',
        )
        self.assertTrue(result.get('fallback'))
        self.assertEqual(len(result['top_investissement']), 15)

    def test_recommendation_aligned_to_note(self):
        raw = {
            'top_investissement': [
                {
                    'produit': 'iPhone 14',
                    'note': 9.2,
                    'recommandation': 'À éviter',  # incohérent → corrigé BON
                    'synthese': 'x' * 50,
                },
                {
                    'produit': 'Tecno Spark',
                    'note': 6.1,
                    'recommandation': 'Acheter & Stocker',  # incohérent → corrigé MOYEN
                },
                {
                    'produit': 'Ancien modèle',
                    'note': 3.0,
                    'recommandation': 'Investir maintenant',  # incohérent → corrigé FAIBLE
                },
                {
                    'produit': 'Samsung A54',
                    'note': 8.0,
                    'recommandation': 'Bon, je vous le recommande',
                    'synthese': '',  # vide → synthèse auto
                },
            ],
        }
        result = DeepSeekAnalysisService.validate_result(raw)
        items = result['top_investissement']
        self.assertEqual(items[0]['recommandation'], 'Bon, je vous le recommande')
        self.assertEqual(items[1]['recommandation'], "Peut faire l'affaire mais moyen")
        self.assertEqual(items[2]['recommandation'], 'À éviter')
        self.assertEqual(items[3]['recommandation'], 'Bon, je vous le recommande')
        self.assertTrue(items[3]['synthese'])
        self.assertLessEqual(len(items[0]['synthese']), 320)

    def test_ensure_fills_synth_for_ranks_11_15(self):
        raw = {
            'top_investissement': [
                {
                    'produit': f'Prod {i}',
                    'note': max(1.0, 10 - i * 0.5),
                    'recommandation': '',
                    'synthese': '' if i >= 11 else f'Analyse rang {i}.',
                }
                for i in range(1, 16)
            ],
        }
        result = DeepSeekAnalysisService.ensure_top10(
            DeepSeekAnalysisService.validate_result(raw),
            payload={},
            domain_label='Téléphonie',
            category_label='',
        )
        for item in result['top_investissement']:
            self.assertTrue(item['synthese'].strip(), item['rang'])
            self.assertIn(item['recommandation'], (
                'Bon, je vous le recommande',
                "Peut faire l'affaire mais moyen",
                'À éviter',
            ))

    def test_is_enabled(self):
        self.assertTrue(DeepSeekAnalysisService.is_enabled())

    def test_chat_extra_body_disables_v4_thinking(self):
        body = DeepSeekAnalysisService._chat_extra_body({'MODEL': 'deepseek-v4-flash'})
        self.assertEqual(body, {'thinking': {'type': 'disabled'}})

    def test_parse_json_response_strips_markdown(self):
        raw = '```json\n{"ok": true}\n```'
        self.assertEqual(DeepSeekAnalysisService._parse_json_response(raw), {'ok': True})

    def test_parse_json_response_empty_raises(self):
        with self.assertRaises(ValueError):
            DeepSeekAnalysisService._parse_json_response('')

    def test_normalize_web_domain(self):
        self.assertEqual(
            DeepSeekAnalysisService.normalize_web_domain('https://www.Jumia.sn/catalog/'),
            'jumia.sn',
        )
        self.assertEqual(
            DeepSeekAnalysisService.normalize_web_domain('alibaba.com'),
            'alibaba.com',
        )
        self.assertEqual(DeepSeekAnalysisService.normalize_web_domain('not a domain'), '')

    def test_build_web_search_tool_allowed_domains(self):
        tool = DeepSeekAnalysisService.build_web_search_tool()
        self.assertEqual(tool['type'], 'web_search_20250305')
        self.assertEqual(tool['name'], 'web_search')
        self.assertEqual(tool['max_uses'], 5)
        self.assertIn('jumia.sn', tool['allowed_domains'])
        self.assertIn('alibaba.com', tool['allowed_domains'])
        self.assertNotIn('blocked_domains', tool)
        self.assertEqual(tool['user_location']['country'], 'SN')
        self.assertEqual(tool['user_location']['city'], 'Dakar')

    def test_build_web_search_tool_blocked_when_no_allowed(self):
        tool = DeepSeekAnalysisService.build_web_search_tool({
            'WEB_ALLOWED_DOMAINS': [],
            'WEB_BLOCKED_DOMAINS': ['spam.example', 'https://www.bad.com/x'],
            'WEB_MAX_USES': 3,
            'WEB_COUNTRY': 'SN',
            'WEB_CITY': 'Dakar',
            'WEB_TIMEZONE': 'Africa/Dakar',
        })
        self.assertEqual(tool['blocked_domains'], ['spam.example', 'bad.com'])
        self.assertNotIn('allowed_domains', tool)
        self.assertEqual(tool['max_uses'], 3)

    def test_format_web_watch_status_references_uses_and_sites(self):
        status = DeepSeekAnalysisService.format_web_watch_status(
            3, focus='prix Jumia.sn et Jiji.sn',
        )
        self.assertIn('Veille web tour 3', status)
        self.assertIn('5 recherches', status)
        self.assertIn('jumia.sn', status)
        self.assertEqual(
            DeepSeekAnalysisService.format_web_watch_status(1, enabled=False),
            'Veille web off',
        )

    def test_web_watch_meta(self):
        meta = DeepSeekAnalysisService.web_watch_meta()
        self.assertEqual(meta['max_uses'], 5)
        self.assertIn('jiji.sn', meta['allowed_domains'])
        self.assertEqual(meta['country'], 'SN')
