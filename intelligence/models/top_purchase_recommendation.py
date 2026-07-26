from django.db import models


class TopPurchaseRecommendation(models.Model):
    """Top 10 produits à sourcer — calculé par agrégation NLP + engagement + Trends."""

    rank = models.PositiveSmallIntegerField('Rang', db_index=True)
    product_slug = models.SlugField('Slug produit', max_length=80, db_index=True)
    product_name = models.CharField('Nom produit', max_length=120)
    category = models.CharField('Catégorie métier', max_length=80, blank=True)
    score = models.FloatField('Score demande', db_index=True)
    score_normalized = models.PositiveSmallIntegerField(
        'Score affiché (0-100)',
        default=0,
        help_text='Barre de progression UI.',
    )
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
    stock_alert = models.CharField(
        'Alerte stock Jumia',
        max_length=16,
        blank=True,
        default='',
        help_text='watch | critical | vide',
    )
    jumia_boost = models.FloatField('Bonus Jumia', default=0)
    jumia_evidence = models.CharField('Preuve Jumia', max_length=300, blank=True)
    computed_at = models.DateTimeField('Calculé le', auto_now=True)

    class Meta:
        verbose_name = 'Recommandation achat (Top 10)'
        verbose_name_plural = 'Recommandations achat (Top 10)'
        ordering = ['rank']
        constraints = [
            models.UniqueConstraint(fields=['rank'], name='unique_top_purchase_rank'),
        ]

    def __str__(self):
        return f'#{self.rank} {self.product_name} ({self.score_normalized}/100)'
