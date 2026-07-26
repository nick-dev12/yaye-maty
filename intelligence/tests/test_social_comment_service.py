"""Tests synchronisation commentaires sociaux."""

from django.test import TestCase

from intelligence.models import SocialComment, SocialPost
from intelligence.services.social_comment_service import SocialCommentService


class SocialCommentServiceTests(TestCase):
    def setUp(self):
        self.post = SocialPost.objects.create(
            platform='tiktok',
            platform_post_id='1234567890',
            content_hash=SocialPost.build_content_hash('test post'),
            content='test post',
            post_url='https://www.tiktok.com/@user/video/1234567890',
        )

    def test_sync_deduplicates_by_text_hash(self):
        text = 'Ñaata la? Ban prix bi?'
        text_hash = SocialComment.build_text_hash(text)
        SocialComment.objects.create(
            post=self.post,
            text=text,
            text_hash=text_hash,
            platform_comment_id='old-id-1',
        )

        self.post.comments = [
            {'text': text, 'platform_comment_id': 'new-id-2', 'published_at': ''},
        ]
        stats = SocialCommentService.sync_post_comments(self.post)

        self.assertEqual(stats['created'], 0)
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(SocialComment.objects.filter(post=self.post).count(), 1)
        comment = SocialComment.objects.get(post=self.post, text_hash=text_hash)
        self.assertEqual(comment.platform_comment_id, 'new-id-2')

    def test_sync_creates_multiple_distinct_comments(self):
        self.post.comments = [
            {'text': 'Je veux acheter', 'platform_comment_id': 'c1', 'published_at': ''},
            {'text': 'Quel est le prix?', 'platform_comment_id': 'c2', 'published_at': ''},
        ]
        stats = SocialCommentService.sync_post_comments(self.post)

        self.assertEqual(stats['created'], 2)
        self.assertEqual(SocialComment.objects.filter(post=self.post).count(), 2)
