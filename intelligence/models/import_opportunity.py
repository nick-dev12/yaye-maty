"""Opportunité d'importation quotidienne — module Import Master."""

from django.db import models


class ImportOpportunity(models.Model):
    """
    Snapshot quotidien d'une opportunité d'importation par mot-clé actif.

    Le score global (0-100) agrège 4 sous-scores pondérés :
    demande sociale, tendance Google, concurrence (inversée) et prix.
    La décision Acheter / Surveiller / Éviter est dérivée de règles
    explicites, tracées dans `decision_reasons` pour l'UI.
    """

    class Decision(models.TextChoices):
        BUY = 'buy', 'Acheter'
        WATCH = 'watch', 'Surveiller'
        AVOID = 'avoid', 'Éviter'

    keyword = models.ForeignKey(
        'intelligence.MarketSearchKeyword',
        verbose_name='Mot-clé Paramètres',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='import_opportunities',
    )
    keyword_text = models.CharField(
        'Mot-clé (texte)',
        max_length=200,
        db_index=True,
        help_text='Copie du mot-clé — conservée même si le mot-clé Paramètres est supprimé.',
    )
    product_slug = models.SlugField('Slug produit', max_length=80, blank=True, db_index=True)
    product_name = models.CharField('Nom produit', max_length=200)
    snapshot_date = models.DateField('Date du snapshot', db_index=True)
    rank = models.PositiveSmallIntegerField('Rang du jour', default=0, db_index=True)

    score = models.PositiveSmallIntegerField('Score global (0-100)', default=0, db_index=True)
    demand_score = models.PositiveSmallIntegerField('Score demande (0-100)', default=0)
    trend_score = models.PositiveSmallIntegerField('Score tendance (0-100)', default=0)
    competition_score = models.PositiveSmallIntegerField('Score concurrence (0-100)', default=0)
    price_score = models.PositiveSmallIntegerField('Score prix (0-100)', default=0)

    decision = models.CharField(
        'Décision',
        max_length=8,
        choices=Decision.choices,
        default=Decision.WATCH,
        db_index=True,
    )
    decision_reasons = models.JSONField(
        'Raisons de la décision',
        default=list,
        blank=True,
        help_text='Liste de phrases lisibles justifiant la décision.',
    )

    # Contexte marché (Jumia + Jiji)
    market_price_min_xof = models.DecimalField(
        'Prix min marché', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    market_price_avg_xof = models.DecimalField(
        'Prix moyen marché', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    market_price_max_xof = models.DecimalField(
        'Prix max marché', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    jumia_sellers = models.PositiveIntegerField('Vendeurs Jumia distincts', default=0)
    jiji_listings_count = models.PositiveIntegerField('Annonces Jiji', default=0)
    purchase_intent_count = models.PositiveIntegerField("Intentions d'achat (7 j)", default=0)
    total_views = models.PositiveBigIntegerField('Vues réseaux (7 j)', default=0)
    stock_alert = models.CharField(
        'Alerte stock Jumia',
        max_length=16,
        blank=True,
        default='',
        help_text='watch | critical | vide',
    )
    suggested_price_xof = models.DecimalField(
        'Prix de vente conseillé',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Phase 2 — prix fournisseur Chine (Alibaba)
    supplier_price_xof = models.DecimalField(
        'Prix fournisseur (FCFA)',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Phase 2 — prix Alibaba converti en FCFA.',
    )
    estimated_margin_percent = models.FloatField(
        'Marge estimée %',
        null=True,
        blank=True,
        help_text='Phase 2 — (prix conseillé − coût import) / prix conseillé.',
    )

    computed_at = models.DateTimeField('Calculé le', auto_now=True)

    class Meta:
        verbose_name = "Opportunité d'importation"
        verbose_name_plural = "Opportunités d'importation"
        ordering = ['-snapshot_date', 'rank']
        constraints = [
            models.UniqueConstraint(
                fields=['snapshot_date', 'keyword_text'],
                name='unique_import_opportunity_per_day',
            ),
        ]
        indexes = [
            models.Index(fields=['snapshot_date', 'decision']),
            models.Index(fields=['snapshot_date', '-score']),
        ]

    def __str__(self):
        return (
            f'{self.snapshot_date} · {self.keyword_text} · '
            f'{self.get_decision_display()} ({self.score}/100)'
        )
