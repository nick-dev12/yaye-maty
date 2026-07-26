"""Tests extraction JSON embarqué TikTok."""

from django.test import SimpleTestCase

from intelligence.scrapers.extractors.tiktok_page_json import (
    _extract_item_struct,
    _extract_stats_dict,
    _walk_for_video_data,
    parse_relative_french_date,
)


class TikTokPageJsonTests(SimpleTestCase):
    def test_extract_stats_dict(self):
        stats = _extract_stats_dict({
            'stats': {
                'diggCount': 1500,
                'shareCount': '42',
                'collectCount': 88,
                'commentCount': 19,
                'playCount': 12000,
            },
            'createTime': 1_700_000_000,
        })
        self.assertEqual(stats['like_count'], 1500)
        self.assertEqual(stats['share_count'], 42)
        self.assertEqual(stats['save_count'], 88)
        self.assertEqual(stats['comment_count'], 19)
        self.assertEqual(stats['view_count'], 12000)

    def test_extract_item_struct_with_author(self):
        data = _extract_item_struct({
            'desc': 'Mini tracteur disponible au Sénégal #agriculture',
            'createTime': 1_700_000_000,
            'author': {'uniqueId': 'ferme_dakar'},
            'stats': {'diggCount': 10, 'playCount': 100, 'shareCount': 1, 'collectCount': 2, 'commentCount': 3},
        })
        self.assertEqual(data['author'], 'ferme_dakar')
        self.assertIn('Mini tracteur', data['content'])
        self.assertTrue(data['published_at'])

    def test_walk_for_video_data_by_post_id(self):
        payload = {
            'ItemModule': {
                '7123456789012345678': {
                    'desc': 'Pompe solaire test',
                    'createTime': 1_700_000_000,
                    'stats': {
                        'diggCount': 5,
                        'playCount': 50,
                        'shareCount': 1,
                        'collectCount': 2,
                        'commentCount': 4,
                    },
                },
            },
        }
        found = _walk_for_video_data(payload, post_id='7123456789012345678')
        self.assertEqual(found['like_count'], 5)
        self.assertEqual(found['view_count'], 50)

    def test_parse_relative_french_date(self):
        iso = parse_relative_french_date('2024-3-15')
        self.assertIn('2024-03-15', iso)
