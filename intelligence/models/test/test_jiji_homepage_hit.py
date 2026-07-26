from django.db import models


class TestJijiHomepageHit(models.Model):
    """Miroir test — hits accueil Jiji."""

    listing_url = models.URLField(max_length=500)
    listing_id = models.CharField(max_length=80, blank=True, db_index=True)
    title = models.CharField(max_length=400)
    price_label = models.CharField(max_length=64, blank=True)
    condition_label = models.CharField(max_length=40, blank=True)
    location_label = models.CharField(max_length=160, blank=True)
    seller_badge = models.CharField(max_length=120, blank=True)
    section_label = models.CharField(max_length=160, blank=True, default='trending')
    matched_keyword = models.CharField(max_length=200, db_index=True)
    keyword_id = models.PositiveIntegerField(null=True, blank=True)
    enriched = models.BooleanField(default=False)
    scraped_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Hit accueil Jiji (test)'
        verbose_name_plural = 'Hits accueil Jiji (test)'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['listing_url', 'matched_keyword'],
                name='unique_test_jiji_homepage_hit_kw',
            ),
        ]
