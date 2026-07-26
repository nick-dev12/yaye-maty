"""Tests utilitaires scraping — IDs et hashtags."""

from django.test import SimpleTestCase

from intelligence.scrapers.engagement_utils import extract_hashtags
from intelligence.scrapers.extractors.tiktok_comment_extractor import parse_comment_api_payload
from intelligence.scrapers.post_id_utils import extract_post_id


class ScrapingUtilsTests(SimpleTestCase):
    def test_extract_tiktok_post_id(self):
        url = 'https://www.tiktok.com/@agri_sn/video/7123456789012345678'
        self.assertEqual(extract_post_id('tiktok', url), '7123456789012345678')

    def test_extract_hashtags(self):
        text = 'Arrivage motopompes #AgricultureSenegal #ElevageSN à Dakar'
        tags = extract_hashtags(text)
        self.assertIn('agriculturesenegal', tags)
        self.assertIn('elevagesn', tags)

    def test_parse_tiktok_comment_api_payload(self):
        payload = {
            'comments': [
                {'cid': '111', 'text': 'Ñaata la? Ban prix bi?', 'create_time': 1_700_000_000},
                {'cid': '222', 'text': 'Super produit', 'create_time': 1_700_000_100},
            ],
        }
        comments = parse_comment_api_payload(payload, post_id='999')
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]['platform_comment_id'], '111')
        self.assertIn('Ñaata', comments[0]['text'])
        self.assertTrue(comments[0]['published_at'])
        self.assertEqual(comments[0]['commented_at'], comments[0]['published_at'])
