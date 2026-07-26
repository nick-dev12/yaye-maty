"""Miroir test — snapshots prix Jiji."""

from django.db import models


class TestJijiPriceSnapshot(models.Model):
    listing = models.ForeignKey(
        'intelligence.TestJijiListing',
        on_delete=models.CASCADE,
        related_name='price_snapshots',
        verbose_name='Annonce',
    )
    price_xof = models.DecimalField(
        'Prix (FCFA)', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    is_negotiable = models.BooleanField('Négociable', default=False)
    condition = models.CharField('État', max_length=20, blank=True)
    views_count = models.PositiveIntegerField('Vues', default=0)
    captured_at = models.DateTimeField('Capturé le', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Snapshot prix Jiji (test)'
        verbose_name_plural = 'Snapshots prix Jiji (test)'
        db_table = 'intelligence_test_jiji_price_snapshot'
        ordering = ['-captured_at']

    def __str__(self):
        return f'[TEST] snapshot {self.listing_id}'
