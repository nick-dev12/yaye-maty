"""
Façade prod/test — sélectionne les modèles Django selon le contexte de collecte.
"""

from __future__ import annotations

from intelligence.models import (
    DiscoveredQuery,
    JijiHomepageHit,
    JijiListing,
    JijiPriceSnapshot,
    JumiaHomepageHit,
    JumiaPriceSnapshot,
    JumiaProduct,
    JumiaReview,
    ProductMarketSignal,
    SocialComment,
    SocialPost,
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
    TopPurchaseRecommendation,
)
from intelligence.services.collection_run_context import CollectionRunContext, get_collection_context


class CollectionModelRouter:
    """Route les requêtes ORM vers les tables production ou test."""

    def __init__(self, ctx: CollectionRunContext | None = None):
        self.ctx = ctx or get_collection_context()

    @property
    def is_test(self) -> bool:
        return self.ctx.is_test

    @property
    def post_model(self):
        return TestSocialPost if self.is_test else SocialPost

    @property
    def comment_model(self):
        return TestSocialComment if self.is_test else SocialComment

    @property
    def discovered_model(self):
        return TestDiscoveredQuery if self.is_test else DiscoveredQuery

    @property
    def recommendation_model(self):
        return TestTopPurchaseRecommendation if self.is_test else TopPurchaseRecommendation

    @property
    def jumia_product_model(self):
        return TestJumiaProduct if self.is_test else JumiaProduct

    @property
    def jumia_review_model(self):
        return TestJumiaReview if self.is_test else JumiaReview

    @property
    def jumia_snapshot_model(self):
        return TestJumiaPriceSnapshot if self.is_test else JumiaPriceSnapshot

    @property
    def jumia_homepage_hit_model(self):
        return TestJumiaHomepageHit if self.is_test else JumiaHomepageHit

    @property
    def market_signal_model(self):
        return TestProductMarketSignal if self.is_test else ProductMarketSignal

    @property
    def jiji_listing_model(self):
        return TestJijiListing if self.is_test else JijiListing

    @property
    def jiji_snapshot_model(self):
        return TestJijiPriceSnapshot if self.is_test else JijiPriceSnapshot

    @property
    def jiji_homepage_hit_model(self):
        return TestJijiHomepageHit if self.is_test else JijiHomepageHit

    def posts_qs(self):
        return self.post_model.objects.all()

    def comments_qs(self):
        return self.comment_model.objects.all()

    def discovered_qs(self):
        return self.discovered_model.objects.all()

    def recommendations_qs(self):
        return self.recommendation_model.objects.all()

    def jumia_products_qs(self):
        return self.jumia_product_model.objects.all()

    def jumia_reviews_qs(self):
        return self.jumia_review_model.objects.all()

    def jumia_snapshots_qs(self):
        return self.jumia_snapshot_model.objects.all()

    def jumia_homepage_hits_qs(self):
        return self.jumia_homepage_hit_model.objects.all()

    def market_signals_qs(self):
        return self.market_signal_model.objects.all()

    def jiji_listings_qs(self):
        return self.jiji_listing_model.objects.all()

    def jiji_snapshots_qs(self):
        return self.jiji_snapshot_model.objects.all()

    def jiji_homepage_hits_qs(self):
        return self.jiji_homepage_hit_model.objects.all()
