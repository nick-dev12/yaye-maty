from django.contrib import admin

from .models import (
    DiscoveredQuery,
    DiscoveryConfig,
    JijiListing,
    JijiPriceSnapshot,
    JumiaPriceSnapshot,
    JumiaProduct,
    JumiaReview,
    MarketDomain,
    MarketSearchKeyword,
    ProductMarketSignal,
    SocialComment,
    SocialPost,
    SocialScrapeTarget,
    TestDiscoveredQuery,
    TestJijiListing,
    TestJijiPriceSnapshot,
    TestJumiaPriceSnapshot,
    TestJumiaProduct,
    TestJumiaReview,
    TestProductMarketSignal,
    TestSocialComment,
    TestSocialPost,
    TestTopPurchaseRecommendation,
    TopPurchaseRecommendation,
    TrendRecord,
    WolofKeyword,
)


@admin.register(TrendRecord)
class TrendRecordAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'date', 'score', 'region', 'fetched_at')
    list_filter = ('region', 'keyword', 'date')
    search_fields = ('keyword',)
    date_hierarchy = 'date'
    ordering = ('-date', 'keyword')


@admin.register(DiscoveredQuery)
class DiscoveredQueryAdmin(admin.ModelAdmin):
    list_display = ('query', 'domain', 'query_type', 'value_display', 'region', 'discovered_at')
    list_filter = ('domain', 'query_type', 'region')
    search_fields = ('query',)
    ordering = ('-discovered_at', 'domain')


@admin.register(MarketDomain)
class MarketDomainAdmin(admin.ModelAdmin):
    list_display = ('label', 'slug', 'cat_id', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('label', 'slug', 'seed_keywords')
    prepopulated_fields = {'slug': ('label',)}


@admin.register(DiscoveryConfig)
class DiscoveryConfigAdmin(admin.ModelAdmin):
    list_display = ('timeframe', 'region', 'updated_at')
    filter_horizontal = ('selected_domains',)

    def has_add_permission(self, request):
        return not DiscoveryConfig.objects.exists()


@admin.register(SocialScrapeTarget)
class SocialScrapeTargetAdmin(admin.ModelAdmin):
    list_display = ('label', 'platform', 'region', 'url', 'is_active', 'max_posts', 'scrape_comments', 'last_scraped_at')
    list_filter = ('platform', 'region', 'is_active', 'scrape_comments')
    search_fields = ('label', 'url')


@admin.register(WolofKeyword)
class WolofKeywordAdmin(admin.ModelAdmin):
    list_display = ('expression', 'intent', 'note', 'is_active', 'updated_at')
    list_filter = ('intent', 'is_active')
    search_fields = ('expression', 'note')


@admin.register(MarketSearchKeyword)
class MarketSearchKeywordAdmin(admin.ModelAdmin):
    list_display = (
        'display_label', 'platform', 'product_category', 'region',
        'max_videos', 'max_comments', 'is_active', 'last_scraped_at',
    )
    list_filter = ('platform', 'region', 'is_active', 'product_category')
    search_fields = ('keyword', 'label', 'product_category')
    readonly_fields = ('last_scraped_at', 'created_at', 'updated_at')


@admin.register(SocialComment)
class SocialCommentAdmin(admin.ModelAdmin):
    list_display = (
        'text_preview', 'post', 'intent', 'confidence_score',
        'analysis_method', 'published_at', 'is_analyzed',
    )
    list_filter = ('intent', 'analysis_method', 'is_analyzed')
    search_fields = ('text',)
    readonly_fields = ('text_hash', 'created_at', 'analyzed_at')

    @admin.display(description='Texte')
    def text_preview(self, obj):
        return obj.text[:60] + ('…' if len(obj.text) > 60 else '')


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = (
        'platform', 'platform_post_id', 'author', 'content_preview', 'demand_score',
        'view_count', 'like_count', 'save_count', 'comments_scraped_count',
        'analysis_status', 'scraped_at',
    )
    list_filter = ('platform', 'analysis_status', 'sentiment')
    search_fields = ('content', 'author', 'category')
    readonly_fields = ('content_hash', 'scraped_at', 'updated_at', 'demand_score')

    @admin.display(description='Contenu')
    def content_preview(self, obj):
        return obj.content[:80] + ('…' if len(obj.content) > 80 else '')


@admin.register(TopPurchaseRecommendation)
class TopPurchaseRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        'rank', 'product_name', 'score_normalized', 'purchase_intent_count',
        'info_intent_count', 'total_views', 'computed_at',
    )
    ordering = ('rank',)
    search_fields = ('product_name', 'product_slug')


@admin.register(TestDiscoveredQuery)
class TestDiscoveredQueryAdmin(admin.ModelAdmin):
    list_display = ('query', 'domain', 'query_type', 'value_display', 'region', 'discovered_at')
    list_filter = ('domain', 'query_type', 'region')
    search_fields = ('query',)
    ordering = ('-discovered_at', 'domain')


@admin.register(TestSocialComment)
class TestSocialCommentAdmin(admin.ModelAdmin):
    list_display = (
        'text_preview', 'post', 'intent', 'confidence_score',
        'analysis_method', 'published_at', 'is_analyzed',
    )
    list_filter = ('intent', 'analysis_method', 'is_analyzed')
    search_fields = ('text',)
    readonly_fields = ('text_hash', 'created_at', 'analyzed_at')

    @admin.display(description='Texte')
    def text_preview(self, obj):
        return obj.text[:60] + ('…' if len(obj.text) > 60 else '')


@admin.register(TestSocialPost)
class TestSocialPostAdmin(admin.ModelAdmin):
    list_display = (
        'platform', 'platform_post_id', 'author', 'content_preview', 'demand_score',
        'view_count', 'like_count', 'save_count', 'comments_scraped_count',
        'analysis_status', 'scraped_at',
    )
    list_filter = ('platform', 'analysis_status', 'sentiment')
    search_fields = ('content', 'author', 'category')
    readonly_fields = ('content_hash', 'scraped_at', 'updated_at', 'demand_score')

    @admin.display(description='Contenu')
    def content_preview(self, obj):
        return obj.content[:80] + ('…' if len(obj.content) > 80 else '')


@admin.register(TestTopPurchaseRecommendation)
class TestTopPurchaseRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        'rank', 'product_name', 'score_normalized', 'purchase_intent_count',
        'info_intent_count', 'total_views', 'computed_at',
    )
    ordering = ('rank',)
    search_fields = ('product_name', 'product_slug')


@admin.register(JumiaProduct)
class JumiaProductAdmin(admin.ModelAdmin):
    list_display = (
        'sku', 'name_preview', 'brand', 'search_keyword', 'price_xof',
        'discount_percent', 'stock_status', 'rating_value', 'rating_count', 'scraped_at',
    )
    list_filter = ('search_keyword', 'stock_status', 'category', 'brand')
    search_fields = ('name', 'sku', 'seller_name', 'brand')
    readonly_fields = ('scraped_at', 'updated_at', 'stock_checked_at', 'nlp_analyzed_at')

    @admin.display(description='Nom')
    def name_preview(self, obj):
        return obj.name[:70] + ('…' if len(obj.name) > 70 else '')


@admin.register(JumiaReview)
class JumiaReviewAdmin(admin.ModelAdmin):
    list_display = (
        'rating_stars', 'title', 'sentiment', 'author', 'verified_purchase',
        'product', 'is_analyzed', 'review_date',
    )
    list_filter = ('rating_stars', 'sentiment', 'verified_purchase', 'is_analyzed', 'intent')
    search_fields = ('title', 'comment_text', 'author')


@admin.register(JumiaPriceSnapshot)
class JumiaPriceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'price_xof', 'discount_percent', 'stock_status',
        'rating_value', 'captured_at',
    )
    list_filter = ('stock_status',)
    date_hierarchy = 'captured_at'


@admin.register(ProductMarketSignal)
class ProductMarketSignalAdmin(admin.ModelAdmin):
    list_display = (
        'product_slug', 'avg_price_xof', 'stock_alert', 'stockout_rate',
        'avg_rating', 'jumia_boost', 'computed_at',
    )
    list_filter = ('stock_alert',)
    search_fields = ('product_slug', 'product_label')


@admin.register(TestJumiaProduct)
class TestJumiaProductAdmin(admin.ModelAdmin):
    list_display = (
        'sku', 'name_preview', 'brand', 'search_keyword', 'price_xof',
        'stock_status', 'rating_value', 'scraped_at',
    )
    list_filter = ('search_keyword', 'stock_status')
    search_fields = ('name', 'sku', 'brand')

    @admin.display(description='Nom')
    def name_preview(self, obj):
        return obj.name[:70] + ('…' if len(obj.name) > 70 else '')


@admin.register(TestJumiaReview)
class TestJumiaReviewAdmin(admin.ModelAdmin):
    list_display = (
        'rating_stars', 'title', 'sentiment', 'author', 'verified_purchase',
        'product', 'is_analyzed', 'review_date',
    )
    list_filter = ('rating_stars', 'sentiment', 'verified_purchase', 'is_analyzed')
    search_fields = ('title', 'comment_text', 'author')


@admin.register(TestJumiaPriceSnapshot)
class TestJumiaPriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('product', 'price_xof', 'stock_status', 'captured_at')


@admin.register(TestProductMarketSignal)
class TestProductMarketSignalAdmin(admin.ModelAdmin):
    list_display = (
        'product_slug', 'avg_price_xof', 'stock_alert', 'jumia_boost', 'computed_at',
    )


@admin.register(JijiListing)
class JijiListingAdmin(admin.ModelAdmin):
    list_display = (
        'listing_id', 'title_preview', 'price_xof', 'condition', 'is_negotiable',
        'location_region', 'views_count', 'seller_name', 'search_keyword', 'scraped_at',
    )
    list_filter = ('condition', 'is_negotiable', 'search_keyword', 'location_region')
    search_fields = ('title', 'listing_id', 'seller_name', 'location_area')

    @admin.display(description='Titre')
    def title_preview(self, obj):
        return obj.title[:70] + ('…' if len(obj.title) > 70 else '')


@admin.register(JijiPriceSnapshot)
class JijiPriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('listing', 'price_xof', 'is_negotiable', 'views_count', 'captured_at')
    date_hierarchy = 'captured_at'


@admin.register(TestJijiListing)
class TestJijiListingAdmin(admin.ModelAdmin):
    list_display = (
        'listing_id', 'title', 'price_xof', 'condition', 'location_region',
        'views_count', 'search_keyword', 'scraped_at',
    )
    list_filter = ('condition', 'search_keyword')


@admin.register(TestJijiPriceSnapshot)
class TestJijiPriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('listing', 'price_xof', 'views_count', 'captured_at')
