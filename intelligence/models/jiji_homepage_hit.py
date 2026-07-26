from django.db import models


class JijiHomepageHit(models.Model):
    """Annonce repérée sur l'accueil Jiji (Trending), matchée à un mot-clé Paramètres."""

    listing_url = models.URLField('URL annonce', max_length=500)
    listing_id = models.CharField('ID annonce', max_length=80, blank=True, db_index=True)
    title = models.CharField('Titre', max_length=400)
    price_label = models.CharField('Prix affiché', max_length=64, blank=True)
    condition_label = models.CharField('État affiché', max_length=40, blank=True)
    location_label = models.CharField('Localisation', max_length=160, blank=True)
    seller_badge = models.CharField('Badge vendeur', max_length=120, blank=True)
    section_label = models.CharField('Section accueil', max_length=160, blank=True, default='trending')
    matched_keyword = models.CharField('Mot-clé matché', max_length=200, db_index=True)
    keyword = models.ForeignKey(
        'intelligence.MarketSearchKeyword',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jiji_homepage_hits',
        verbose_name='Mot-clé Paramètres',
    )
    enriched = models.BooleanField('Fiche enrichie', default=False)
    scraped_at = models.DateTimeField('Repéré le', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Hit accueil Jiji'
        verbose_name_plural = 'Hits accueil Jiji'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['listing_url', 'matched_keyword'],
                name='unique_jiji_homepage_hit_kw',
            ),
        ]
        indexes = [
            models.Index(fields=['matched_keyword', '-scraped_at']),
            models.Index(fields=['enriched', '-scraped_at']),
        ]

    def __str__(self):
        return f'{self.title[:50]} ← {self.matched_keyword}'
