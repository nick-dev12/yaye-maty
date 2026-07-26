from django.db import models

from intelligence.models.discovered_query import DiscoveredQuery


class TestDiscoveredQuery(models.Model):
    """Requête Google Trends collectée en session test — table isolée."""

    QueryType = DiscoveredQuery.QueryType
    Domain = DiscoveredQuery.Domain

    domain = models.CharField('Domaine', max_length=50, choices=Domain.choices, db_index=True)
    query = models.CharField('Requête', max_length=255, db_index=True)
    query_type = models.CharField('Type', max_length=10, choices=QueryType.choices)
    value_display = models.CharField('Valeur Google', max_length=50)
    region = models.CharField('Région', max_length=5, default='SN')
    discovered_at = models.DateTimeField('Découvert le', auto_now=True)

    class Meta:
        db_table = 'intelligence_test_discoveredquery'
        verbose_name = 'Requête test'
        verbose_name_plural = 'Requêtes test'
        ordering = ['-discovered_at', 'domain', 'query_type']
        constraints = [
            models.UniqueConstraint(
                fields=['domain', 'query', 'query_type', 'region'],
                name='unique_test_discovered_query',
            ),
        ]

    def __str__(self):
        return f'[TEST {self.get_domain_display()}] {self.query} ({self.get_query_type_display()})'
