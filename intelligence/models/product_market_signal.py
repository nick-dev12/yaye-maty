from django.db import models


class ProductMarketSignal(models.Model):
    """Agrégat marché Jumia par produit catalogue (slug YAYEMATY)."""

    class StockAlert(models.TextChoices):
        NONE = '', 'Aucune'
        WATCH = 'watch', 'À surveiller'
        CRITICAL = 'critical', 'Rupture critique'

    product_slug = models.SlugField('Slug produit', max_length=80, unique=True, db_index=True)
    product_label = models.CharField('Libellé', max_length=120, blank=True)
    avg_price_xof = models.DecimalField(
        'Prix moyen marché', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    min_price_xof = models.DecimalField(
        'Prix min', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    max_price_xof = models.DecimalField(
        'Prix max', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    avg_discount_percent = models.FloatField('Remise moyenne %', null=True, blank=True)
    price_sample_size = models.PositiveIntegerField('Échantillon prix', default=0)
    out_of_stock_count = models.PositiveIntegerField('SKUs en rupture', default=0)
    in_stock_count = models.PositiveIntegerField('SKUs en stock', default=0)
    low_stock_count = models.PositiveIntegerField('SKUs stock faible', default=0)
    stockout_rate = models.FloatField('Taux rupture 0-1', default=0)
    stock_alert = models.CharField(
        'Alerte stock',
        max_length=16,
        choices=StockAlert.choices,
        blank=True,
        default='',
        db_index=True,
    )
    avg_rating = models.FloatField('Note moyenne', null=True, blank=True)
    total_ratings = models.PositiveIntegerField('Total avis', default=0)
    review_neg_ratio = models.FloatField('Ratio avis négatifs', default=0)
    top_failure_tags = models.JSONField('Failles top', default=list, blank=True)
    jumia_boost = models.FloatField('Bonus score Top10', default=0)
    evidence_text = models.CharField('Preuve', max_length=400, blank=True)
    computed_at = models.DateTimeField('Calculé le', auto_now=True)

    class Meta:
        verbose_name = 'Signal marché produit'
        verbose_name_plural = 'Signaux marché produits'
        ordering = ['-jumia_boost', 'product_slug']

    def __str__(self):
        return f'{self.product_slug} · {self.avg_price_xof} FCFA · alert={self.stock_alert or "-"}'
