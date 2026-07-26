from django.db import models


class TestTopPurchaseRecommendation(models.Model):
    """Top 10 session test — table isolée."""

    rank = models.PositiveSmallIntegerField('Rang', db_index=True)
    product_slug = models.SlugField('Slug produit', max_length=80, db_index=True)
    product_name = models.CharField('Nom produit', max_length=120)
    category = models.CharField('Catégorie métier', max_length=80, blank=True)
    score = models.FloatField('Score demande', db_index=True)
    score_normalized = models.PositiveSmallIntegerField('Score affiché (0-100)', default=0)
    purchase_intent_count = models.PositiveIntegerField("Intentions d'achat", default=0)
    info_intent_count = models.PositiveIntegerField("Demandes d'info", default=0)
    total_views = models.PositiveBigIntegerField('Vues cumulées', default=0)
    trends_boost = models.FloatField('Bonus Google Trends', default=0)
    related_posts = models.PositiveIntegerField('Publications liées', default=0)
    evidence_text = models.CharField('Preuve (résumé)', max_length=500, blank=True)
    avg_market_price_xof = models.DecimalField(
        'Prix moyen marché Jumia',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    stock_alert = models.CharField('Alerte stock Jumia', max_length=16, blank=True, default='')
    jumia_boost = models.FloatField('Bonus Jumia', default=0)
    jumia_evidence = models.CharField('Preuve Jumia', max_length=300, blank=True)
    computed_at = models.DateTimeField('Calculé le', auto_now=True)

    class Meta:
        db_table = 'intelligence_test_toppurchaserecommendation'
        verbose_name = 'Recommandation test (Top 10)'
        verbose_name_plural = 'Recommandations test (Top 10)'
        ordering = ['rank']
        constraints = [
            models.UniqueConstraint(fields=['rank'], name='unique_test_top_purchase_rank'),
        ]

    def __str__(self):
        return f'[TEST #{self.rank}] {self.product_name} ({self.score_normalized}/100)'
