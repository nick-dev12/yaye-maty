from django.db import models

from intelligence.models.jumia_product import JumiaProduct


class JumiaPriceSnapshot(models.Model):
    """Historique prix / stock / note — un point par collecte significative."""

    product = models.ForeignKey(
        JumiaProduct,
        on_delete=models.CASCADE,
        related_name='price_snapshots',
        verbose_name='Produit',
    )
    price_xof = models.DecimalField(
        'Prix (FCFA)', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    old_price_xof = models.DecimalField(
        'Prix barré (FCFA)', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    discount_percent = models.FloatField('Remise %', null=True, blank=True)
    stock_status = models.CharField('Statut stock', max_length=20, blank=True)
    stock_quantity = models.PositiveIntegerField('Quantité', null=True, blank=True)
    is_in_stock = models.BooleanField('En stock', null=True, blank=True)
    rating_value = models.FloatField('Note', null=True, blank=True)
    rating_count = models.PositiveIntegerField('Nb avis', default=0)
    captured_at = models.DateTimeField('Capturé le', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Snapshot prix Jumia'
        verbose_name_plural = 'Snapshots prix Jumia'
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['product', '-captured_at']),
        ]

    def __str__(self):
        return f'{self.product_id} @ {self.captured_at:%Y-%m-%d} = {self.price_xof}'
