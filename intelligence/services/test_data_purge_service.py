"""
Purge des tables test — à chaque nouveau lancement de session test.
"""

from __future__ import annotations

from django.db import transaction

from intelligence.models import (
    TestDiscoveredQuery,
    TestJijiHomepageHit,
    TestJijiListing,
    TestJijiPriceSnapshot,
    TestJumiaHomepageHit,
    TestJumiaPriceSnapshot,
    TestJumiaProduct,
    TestJumiaReview,
    TestProductMarketSignal,
    TestSocialComment,
    TestSocialPost,
    TestTopPurchaseRecommendation,
)


class TestDataPurgeService:
    """Vide toutes les tables de données test (sans archive)."""

    @classmethod
    @transaction.atomic
    def purge_all(cls) -> dict[str, int]:
        counts = {
            'comments': TestSocialComment.objects.count(),
            'posts': TestSocialPost.objects.count(),
            'discovered': TestDiscoveredQuery.objects.count(),
            'recommendations': TestTopPurchaseRecommendation.objects.count(),
            'jumia_reviews': TestJumiaReview.objects.count(),
            'jumia_snapshots': TestJumiaPriceSnapshot.objects.count(),
            'jumia_homepage_hits': TestJumiaHomepageHit.objects.count(),
            'jumia_products': TestJumiaProduct.objects.count(),
            'jiji_homepage_hits': TestJijiHomepageHit.objects.count(),
            'jiji_snapshots': TestJijiPriceSnapshot.objects.count(),
            'jiji_listings': TestJijiListing.objects.count(),
            'market_signals': TestProductMarketSignal.objects.count(),
        }
        TestSocialComment.objects.all().delete()
        TestSocialPost.objects.all().delete()
        TestDiscoveredQuery.objects.all().delete()
        TestTopPurchaseRecommendation.objects.all().delete()
        TestJumiaReview.objects.all().delete()
        TestJumiaPriceSnapshot.objects.all().delete()
        TestJumiaHomepageHit.objects.all().delete()
        TestJumiaProduct.objects.all().delete()
        TestJijiHomepageHit.objects.all().delete()
        TestJijiPriceSnapshot.objects.all().delete()
        TestJijiListing.objects.all().delete()
        TestProductMarketSignal.objects.all().delete()
        return counts
