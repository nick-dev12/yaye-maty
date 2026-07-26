from django.db import models


class TrendRecord(models.Model):
    """Historique des scores Google Trends pour un mot-clé agricole."""

    class Source(models.TextChoices):
        GOOGLE_TRENDS = 'google_trends', 'Google Trends'

    keyword = models.CharField('Mot-clé', max_length=100, db_index=True)
    date = models.DateField('Date')
    score = models.PositiveSmallIntegerField(
        'Score d\'intérêt',
        help_text='Score relatif de 0 à 100 fourni par Google Trends',
    )
    region = models.CharField('Région', max_length=5, default='SN')
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.GOOGLE_TRENDS,
    )
    fetched_at = models.DateTimeField('Collecté le', auto_now=True)

    class Meta:
        verbose_name = 'Tendance de recherche'
        verbose_name_plural = 'Tendances de recherche'
        ordering = ['-date', 'keyword']
        constraints = [
            models.UniqueConstraint(
                fields=['keyword', 'date', 'region', 'source'],
                name='unique_trend_record',
            ),
        ]

    def __str__(self):
        return f'{self.keyword} — {self.date} ({self.score})'
