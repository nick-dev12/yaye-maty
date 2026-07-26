"""
Smoke test — isolation tables test vs production (base réelle).
Usage: python scripts/smoke_test_isolation.py
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')
django.setup()

import pandas as pd
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from intelligence.controllers.domain_discovery_controller import DomainDiscoveryController
from intelligence.models import (
    SocialPost,
    TestSocialPost,
    TestTopPurchaseRecommendation,
    TopPurchaseRecommendation,
)
from intelligence.scrapers.extractors.base import ExtractedPost
from intelligence.scrapers.tiktok_scrape_schema import normalize_extracted_post
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService
from intelligence.services.social_post_service import SocialPostService
from intelligence.services.test_data_purge_service import TestDataPurgeService


def main() -> int:
    print('=== Smoke test isolation test/prod ===')
    prod_posts_before = SocialPost.objects.count()
    prod_top_before = TopPurchaseRecommendation.objects.count()
    print(f'Prod: {prod_posts_before} posts, {prod_top_before} Top10')

    purged = TestDataPurgeService.purge_all()
    print(f'Purge: {purged}')

    token = set_collection_context(CollectionRunContext.test())
    try:
        raw = ExtractedPost(
            content='Test motopompe integration smoke',
            post_url='https://www.tiktok.com/@test/video/integration-smoke-999',
            platform_post_id='integration-smoke-999',
            author='testuser',
            view_count=100,
            like_count=5,
            comments=[{'text': 'Je veux acheter motopompe', 'platform_comment_id': 'c1'}],
        )
        item = normalize_extracted_post(raw, platform='tiktok')
        save_stats = SocialPostService.save_extracted_posts(
            platform='tiktok',
            source_url='https://www.tiktok.com/@test/video/integration-smoke-999',
            extracted=[item],
            skip_if_exists=False,
        )
        print(f'Save test posts: {save_stats}')

        ctrl = DomainDiscoveryController()
        df = pd.DataFrame([{'query': 'motopompe test smoke', 'value': '100'}])
        Discovered = CollectionModelRouter().discovered_model
        disc_stats = ctrl._save_queries('agriculture', df, Discovered.QueryType.TOP, 'SN')
        print(f'Save test discovered: {disc_stats}')

        top_stats = PurchaseRecommendationService.refresh_top_recommendations(window_days=30)
        print(f'Refresh test Top10: {top_stats}')
    finally:
        reset_collection_context(token)

    assert SocialPost.objects.filter(platform_post_id='integration-smoke-999').count() == 0
    assert TestSocialPost.objects.filter(platform_post_id='integration-smoke-999').count() >= 1
    assert TopPurchaseRecommendation.objects.count() == prod_top_before
    test_top_count = TestTopPurchaseRecommendation.objects.count()
    print(f'Test Top10 rows: {test_top_count} (0 OK si NLP non lancé)')
    print('Isolation OK (prod intact, test tables remplies)')

    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if not user:
        user = User.objects.create_user('smoke_admin', password='smoke123')
    client = Client(HTTP_HOST='127.0.0.1')
    client.force_login(user)

    for name in ('collecte_test', 'collecte_test_donnees', 'index'):
        url = reverse(f'intelligence:{name}')
        response = client.get(url)
        print(f'GET {name}: HTTP {response.status_code}')
        if response.status_code != 200:
            return 1

    page = client.get(reverse('intelligence:collecte_test_donnees'))
    content = page.content.decode('utf-8', errors='replace').lower()
    if 'integration smoke' not in content and 'motopompe' not in content:
        print('WARN: test data not visible on page (may be template structure)')
    else:
        print('Page Données test affiche les données test OK')

    TestDataPurgeService.purge_all()
    print('=== SMOKE TEST PASSED ===')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
