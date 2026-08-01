from decimal import Decimal

from django.db import models


class JumiaProduct(models.Model):
    """Fiche produit Jumia.sn — prix, note agrégée, stock, métadonnées marché."""

    class AnalysisStatus(models.TextChoices):
        PENDING = 'pending', 'En attente'
        PROCESSING = 'processing', 'En cours'
        DONE = 'done', 'Terminé'
        FAILED = 'failed', 'Échec'

    class StockStatus(models.TextChoices):
        IN_STOCK = 'in_stock', 'En stock'
        LOW_STOCK = 'low_stock', 'Stock faible'
        OUT_OF_STOCK = 'out_of_stock', 'Rupture'
        UNKNOWN = 'unknown', 'Inconnu'

    sku = models.CharField('SKU', max_length=64, unique=True, db_index=True)
    product_url = models.URLField('URL produit', max_length=500)
    name = models.CharField('Nom', max_length=400)
    brand = models.CharField('Marque', max_length=120, blank=True, db_index=True)
    category = models.CharField('Catégorie', max_length=160, blank=True)
    jumia_category = models.ForeignKey(
        'intelligence.JumiaCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='Catégorie catalogue',
    )
    seller_name = models.CharField('Vendeur', max_length=160, blank=True)
    price_xof = models.DecimalField(
        'Prix (FCFA)', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    old_price_xof = models.DecimalField(
        'Prix barré (FCFA)', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    discount_percent = models.FloatField('Remise %', null=True, blank=True, db_index=True)
    currency = models.CharField('Devise', max_length=8, default='XOF')
    availability = models.CharField('Disponibilité brute', max_length=80, blank=True)
    stock_status = models.CharField(
        'Statut stock',
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.UNKNOWN,
        db_index=True,
    )
    stock_quantity = models.PositiveIntegerField(
        'Quantité restante',
        null=True,
        blank=True,
        help_text='Ex. « Il n\'en reste plus que X ».',
    )
    is_in_stock = models.BooleanField('En stock', null=True, blank=True, db_index=True)
    rating_value = models.FloatField('Note moyenne', null=True, blank=True, db_index=True)
    rating_count = models.PositiveIntegerField('Nombre d\'avis', default=0)
    rating_distribution = models.JSONField(
        'Distribution étoiles',
        default=dict,
        blank=True,
        help_text='Ex. {"5": 25, "4": 5, "3": 5, "2": 6, "1": 10}',
    )
    comments_count = models.PositiveIntegerField('Commentaires écrits', default=0)
    search_keyword = models.CharField(
        'Mot-clé source',
        max_length=120,
        blank=True,
        db_index=True,
        help_text='Mot-clé MarketSearchKeyword ayant conduit à ce produit.',
    )
    catalog_product_slug = models.SlugField(
        'Slug catalogue YAYEMATY',
        max_length=80,
        blank=True,
        db_index=True,
    )
    description = models.TextField('Description', blank=True)
    image_url = models.URLField('Image', max_length=500, blank=True)
    sentiment_summary = models.JSONField('Résumé sentiment', default=dict, blank=True)
    aspect_summary = models.JSONField('Résumé aspects', default=dict, blank=True)
    analysis_status = models.CharField(
        'Statut NLP',
        max_length=16,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        db_index=True,
    )
    nlp_analyzed_at = models.DateTimeField('NLP le', null=True, blank=True)
    stock_checked_at = models.DateTimeField('Stock vérifié le', null=True, blank=True)
    scraped_at = models.DateTimeField('Scrapé le', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)

    class Meta:
        verbose_name = 'Produit Jumia'
        verbose_name_plural = 'Produits Jumia'
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['search_keyword', '-rating_value']),
            models.Index(fields=['stock_status', '-rating_count']),
            models.Index(fields=['catalog_product_slug', '-price_xof']),
        ]

    def __str__(self):
        return f'{self.name[:60]} ({self.sku})'

    @staticmethod
    def compute_discount_percent(price, old_price) -> float | None:
        """Calcule la remise % à partir du prix actuel et du prix barré."""
        try:
            price_d = Decimal(str(price)) if price is not None else None
            old_d = Decimal(str(old_price)) if old_price is not None else None
        except Exception:
            return None
        if not price_d or not old_d or old_d <= 0 or price_d >= old_d:
            return None
        return round(float((old_d - price_d) / old_d * 100), 1)
