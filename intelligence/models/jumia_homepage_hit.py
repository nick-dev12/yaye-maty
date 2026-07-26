from django.db import models


class JumiaHomepageHit(models.Model):
    """Produit repéré sur l'accueil Jumia, matché à un mot-clé Paramètres."""

    product_url = models.URLField('URL produit', max_length=500)
    sku = models.CharField('SKU', max_length=64, blank=True, db_index=True)
    name = models.CharField('Nom', max_length=400)
    price_label = models.CharField('Prix affiché', max_length=64, blank=True)
    discount_percent = models.FloatField('Remise %', null=True, blank=True)
    stock_remaining = models.PositiveIntegerField('Stock restant (accueil)', null=True, blank=True)
    section_label = models.CharField('Section accueil', max_length=160, blank=True, db_index=True)
    matched_keyword = models.CharField('Mot-clé matché', max_length=200, db_index=True)
    keyword = models.ForeignKey(
        'intelligence.MarketSearchKeyword',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jumia_homepage_hits',
        verbose_name='Mot-clé Paramètres',
    )
    enriched = models.BooleanField(
        'Fiche enrichie',
        default=False,
        help_text='True si la fiche produit + avis ont été collectés.',
    )
    scraped_at = models.DateTimeField('Repéré le', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Hit accueil Jumia'
        verbose_name_plural = 'Hits accueil Jumia'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product_url', 'matched_keyword'],
                name='unique_jumia_homepage_hit_kw',
            ),
        ]
        indexes = [
            models.Index(fields=['matched_keyword', '-scraped_at']),
            models.Index(fields=['enriched', '-scraped_at']),
        ]

    def __str__(self):
        return f'{self.name[:50]} ← {self.matched_keyword}'
