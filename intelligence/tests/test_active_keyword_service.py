"""Tests ActiveKeywordService — source unique des collectes."""

from django.test import TestCase

from intelligence.models import MarketSearchKeyword
from intelligence.services.active_keyword_service import ActiveKeywordService


class ActiveKeywordServiceTests(TestCase):
    def setUp(self):
        self.tiktok = MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.TIKTOK,
            keyword='motopompe social',
            region='SN',
            is_active=True,
        )
        MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.FACEBOOK,
            keyword='tracteur senegal',
            region='SN',
            is_active=True,
        )
        self.marketplace = MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.MARKETPLACE,
            keyword='motopompe jumia',
            region='SN',
            is_active=True,
            max_videos=8,
        )
        MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.TIKTOK,
            keyword='inactif',
            region='SN',
            is_active=False,
        )

    def test_list_for_social_excludes_marketplace(self):
        social = ActiveKeywordService.list_for_social()
        keywords = {kw.keyword for kw in social}
        self.assertIn('motopompe social', keywords)
        self.assertNotIn('motopompe jumia', keywords)
        self.assertNotIn('inactif', keywords)

    def test_list_for_jumia_and_jiji_share_marketplace(self):
        jumia = ActiveKeywordService.list_for_jumia()
        jiji = ActiveKeywordService.list_for_jiji()
        self.assertEqual(len(jumia), 1)
        self.assertEqual(jumia, jiji)
        self.assertEqual(jumia[0].max_videos, 8)
        self.assertEqual(jumia[0].platform, MarketSearchKeyword.Platform.MARKETPLACE)

    def test_dedupe_legacy_platforms(self):
        MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.JUMIA,
            keyword='legacy mot',
            region='SN',
            is_active=True,
            max_videos=5,
        )
        MarketSearchKeyword.objects.create(
            platform=MarketSearchKeyword.Platform.JIJI,
            keyword='legacy mot',
            region='SN',
            is_active=True,
            max_videos=9,
        )
        marketplace = ActiveKeywordService.list_for_marketplace()
        legacy = [kw for kw in marketplace if kw.keyword == 'legacy mot']
        self.assertEqual(len(legacy), 1)

    def test_get_active_or_none(self):
        self.assertIsNone(ActiveKeywordService.get_active_or_none(None))
        self.assertEqual(
            ActiveKeywordService.get_active_or_none(self.tiktok.pk).pk,
            self.tiktok.pk,
        )

    def test_count_by_platform(self):
        self.assertGreaterEqual(ActiveKeywordService.count_social(), 2)
        self.assertGreaterEqual(ActiveKeywordService.count_marketplace(), 1)
        self.assertEqual(ActiveKeywordService.count_jumia(), ActiveKeywordService.count_jiji())
        self.assertIn(self.tiktok, ActiveKeywordService.list_for_social())
