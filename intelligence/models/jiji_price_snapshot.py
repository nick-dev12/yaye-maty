"""Snapshot historique prix / vues Jiji."""

from django.db import models


class JijiPriceSnapshot(models.Model):
    """Point historique prix / vues / négociabilité pour une annonce Jiji."""

    listing = models.ForeignKey(
        'intelligence.JijiListing',
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
        verbose_name = 'Snapshot prix Jiji'
        verbose_name_plural = 'Snapshots prix Jiji'
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['listing', '-captured_at']),
        ]

    def __str__(self):
        return f'{self.listing_id} @ {self.captured_at:%Y-%m-%d %H:%M}'
