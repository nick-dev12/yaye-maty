"""Filtres publications par mot-clé Paramètres."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from intelligence.models import MarketSearchKeyword, SocialPost
from intelligence.services.intelligence_publications_service import IntelligencePublicationsService


class IntelligencePublicationsKeywordTests(TestCase):
    def setUp(self) -> None:
        self.keyword = MarketSearchKeyword.objects.create(
            keyword='motopompe solaire',
            platform=MarketSearchKeyword.Platform.TIKTOK,
            is_active=True,
        )
        self.other_keyword = MarketSearchKeyword.objects.create(
            keyword='tracteur agricole',
            platform=MarketSearchKeyword.Platform.TIKTOK,
            is_active=True,
        )
        self.search_url = self.keyword.build_search_url()
        SocialPost.objects.create(
            platform=SocialPost.Platform.TIKTOK,
            source_url=self.search_url,
            post_url='https://www.tiktok.com/@user/video/1',
            content='Vidéo motopompe pour irrigation',
            content_hash=SocialPost.build_content_hash('Vidéo motopompe pour irrigation'),
            category='irrigation',
            demand_score=4,
            analysis_status=SocialPost.AnalysisStatus.DONE,
        )
        SocialPost.objects.create(
            platform=SocialPost.Platform.TIKTOK,
            source_url='https://example.com/unknown',
            post_url='https://www.tiktok.com/@user/video/2',
            content='Publication sans mot-clé lié',
            content_hash=SocialPost.build_content_hash('Publication sans mot-clé lié'),
            analysis_status=SocialPost.AnalysisStatus.PENDING,
        )

    def test_keyword_filters_count_posts_per_keyword(self):
        filters = IntelligencePublicationsService.get_keyword_filters()
        by_keyword = {row['keyword']: row['count'] for row in filters if row.get('keyword')}
        self.assertEqual(by_keyword.get('motopompe solaire'), 1)
        other = next(row for row in filters if row['label'] == 'Autres sources')
        self.assertEqual(other['count'], 1)

    def test_get_posts_for_table_filters_by_keyword_id(self):
        rows = IntelligencePublicationsService.get_posts_for_table(keyword_id=self.keyword.pk)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['search_keyword'], 'motopompe solaire')
        self.assertIn('motopompe solaire', rows[0]['topic_summary'])

    def test_intelligence_page_shows_keyword_filters(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username='kw-filter', password='x')
        self.client.force_login(user)
        response = self.client.get(reverse('intelligence:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Filtrer par mot-clé')
        self.assertContains(response, 'motopompe solaire')
        self.assertContains(response, 'Sujet &amp; contexte')
        self.assertNotContains(response, 'intel-widget--timer')
        self.assertNotContains(response, 'Collecte réseaux (7 j)')
        self.assertNotContains(response, 'intel-widget--schedule')
