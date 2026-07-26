from django.db import models


class TestJumiaHomepageHit(models.Model):
    """Miroir test — hits accueil Jumia."""

    product_url = models.URLField(max_length=500)
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    name = models.CharField(max_length=400)
    price_label = models.CharField(max_length=64, blank=True)
    discount_percent = models.FloatField(null=True, blank=True)
    stock_remaining = models.PositiveIntegerField(null=True, blank=True)
    section_label = models.CharField(max_length=160, blank=True, db_index=True)
    matched_keyword = models.CharField(max_length=200, db_index=True)
    keyword_id = models.PositiveIntegerField(null=True, blank=True)
    enriched = models.BooleanField(default=False)
    scraped_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Hit accueil Jumia (test)'
        verbose_name_plural = 'Hits accueil Jumia (test)'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product_url', 'matched_keyword'],
                name='unique_test_jumia_homepage_hit_kw',
            ),
        ]
