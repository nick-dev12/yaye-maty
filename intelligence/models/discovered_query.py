from django.db import models


class DiscoveredQuery(models.Model):
    """Requête découverte via l'exploration par domaine Google Trends."""

    class QueryType(models.TextChoices):
        TOP = 'top', 'Top recherches'
        RISING = 'rising', 'En forte hausse'

    class Domain(models.TextChoices):
        AGRICULTURE = 'agriculture', 'Agriculture & Forêt'
        ELEVAGE = 'elevage', 'Élevage (Animaux de ferme)'

    domain = models.CharField('Domaine', max_length=50, choices=Domain.choices, db_index=True)
    query = models.CharField('Requête', max_length=255, db_index=True)
    query_type = models.CharField('Type', max_length=10, choices=QueryType.choices)
    value_display = models.CharField('Valeur Google', max_length=50)
    region = models.CharField('Région', max_length=5, default='SN')
    discovered_at = models.DateTimeField('Découvert le', auto_now=True)

    class Meta:
        verbose_name = 'Requête découverte'
        verbose_name_plural = 'Requêtes découvertes'
        ordering = ['-discovered_at', 'domain', 'query_type']
        constraints = [
            models.UniqueConstraint(
                fields=['domain', 'query', 'query_type', 'region'],
                name='unique_discovered_query',
            ),
        ]

    def __str__(self):
        return f'[{self.get_domain_display()}] {self.query} ({self.get_query_type_display()})'
