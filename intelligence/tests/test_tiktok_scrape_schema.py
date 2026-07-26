"""Tests structure enregistrement TikTok."""

from django.test import SimpleTestCase

from intelligence.scrapers.extractors.base import ExtractedPost
from intelligence.scrapers.extractors.tiktok_comment_extractor import parse_comment_api_payload
from intelligence.scrapers.tiktok_scrape_schema import (
    MAX_COMMENTS_PER_VIDEO,
    MIN_COMMENTS_PER_VIDEO,
    clamp_max_comments,
    normalize_comments,
    normalize_extracted_post,
    validate_tiktok_record,
)


class TikTokScrapeSchemaTests(SimpleTestCase):
    def test_clamp_max_comments(self):
        self.assertEqual(clamp_max_comments(None), 20)
        self.assertEqual(clamp_max_comments(5), MIN_COMMENTS_PER_VIDEO)
        self.assertEqual(clamp_max_comments(50), MAX_COMMENTS_PER_VIDEO)
        self.assertEqual(clamp_max_comments(15), 15)

    def test_normalize_comments_caps_at_twenty(self):
        raw = [{'text': f'Commentaire numéro {i}', 'platform_comment_id': str(i)} for i in range(30)]
        result = normalize_comments(raw, video_id='123')
        self.assertEqual(len(result), MAX_COMMENTS_PER_VIDEO)
        self.assertIn('commented_at', result[0])

    def test_normalize_extracted_post_tiktok(self):
        item = ExtractedPost(
            content='Pompe irrigation #AgricultureSenegal',
            post_url='https://www.tiktok.com/@user/video/7123456789012345678',
            view_count=1000,
            like_count=50,
            share_count=10,
            save_count=25,
            comments=[{'text': 'C\'est combien?', 'commented_at': '2026-01-01T12:00:00+00:00'}],
        )
        normalized = normalize_extracted_post(item, platform='tiktok')
        self.assertEqual(normalized.platform_post_id, '7123456789012345678')
        self.assertIn('agriculturesenegal', normalized.hashtags)

    def test_validate_tiktok_record_requires_video_id(self):
        item = ExtractedPost(content='Test caption longue enough', platform_post_id='')
        errors = validate_tiktok_record(item)
        self.assertTrue(any('video_id' in err for err in errors))

    def test_parse_comment_api_includes_commented_at(self):
        payload = {
            'comments': [
                {'cid': '111', 'text': 'Où est votre boutique?', 'create_time': 1_700_000_000},
            ],
        }
        comments = parse_comment_api_payload(payload, post_id='999')
        self.assertEqual(comments[0]['commented_at'], comments[0]['published_at'])
