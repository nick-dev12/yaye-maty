from .test_discovered_query import TestDiscoveredQuery
from .test_jiji_homepage_hit import TestJijiHomepageHit
from .test_jiji_listing import TestJijiListing
from .test_jiji_price_snapshot import TestJijiPriceSnapshot
from .test_jumia_homepage_hit import TestJumiaHomepageHit
from .test_jumia_price_snapshot import TestJumiaPriceSnapshot
from .test_jumia_product import TestJumiaProduct
from .test_jumia_review import TestJumiaReview
from .test_product_market_signal import TestProductMarketSignal
from .test_social_comment import TestSocialComment
from .test_social_post import TestSocialPost
from .test_top_purchase_recommendation import TestTopPurchaseRecommendation

__all__ = [
    'TestDiscoveredQuery',
    'TestSocialComment',
    'TestSocialPost',
    'TestTopPurchaseRecommendation',
    'TestJumiaProduct',
    'TestJumiaReview',
    'TestJumiaPriceSnapshot',
    'TestJumiaHomepageHit',
    'TestProductMarketSignal',
    'TestJijiHomepageHit',
    'TestJijiListing',
    'TestJijiPriceSnapshot',
]
