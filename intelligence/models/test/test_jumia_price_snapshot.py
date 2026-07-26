from django.db import models

from intelligence.models.test.test_jumia_product import TestJumiaProduct


class TestJumiaPriceSnapshot(models.Model):
    """Miroir test de JumiaPriceSnapshot."""

    product = models.ForeignKey(
        TestJumiaProduct,
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
        verbose_name = 'Snapshot prix Jumia (test)'
        verbose_name_plural = 'Snapshots prix Jumia (test)'
        db_table = 'intelligence_test_jumia_price_snapshot'
        ordering = ['-captured_at']

    def __str__(self):
        return f'[TEST] {self.product_id} @ {self.captured_at:%Y-%m-%d} = {self.price_xof}'
