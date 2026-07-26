from django.db import models

from intelligence.models.jumia_product import JumiaProduct


class TestJumiaProduct(models.Model):
    """Miroir test de JumiaProduct — isolation session test."""

    AnalysisStatus = JumiaProduct.AnalysisStatus
    StockStatus = JumiaProduct.StockStatus
    compute_discount_percent = staticmethod(JumiaProduct.compute_discount_percent)

    sku = models.CharField('SKU', max_length=64, unique=True, db_index=True)
    product_url = models.URLField('URL produit', max_length=500)
    name = models.CharField('Nom', max_length=400)
    brand = models.CharField('Marque', max_length=120, blank=True, db_index=True)
    category = models.CharField('Catégorie', max_length=160, blank=True)
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
    stock_quantity = models.PositiveIntegerField('Quantité restante', null=True, blank=True)
    is_in_stock = models.BooleanField('En stock', null=True, blank=True, db_index=True)
    rating_value = models.FloatField('Note moyenne', null=True, blank=True, db_index=True)
    rating_count = models.PositiveIntegerField('Nombre d\'avis', default=0)
    rating_distribution = models.JSONField('Distribution étoiles', default=dict, blank=True)
    comments_count = models.PositiveIntegerField('Commentaires écrits', default=0)
    search_keyword = models.CharField('Mot-clé source', max_length=120, blank=True, db_index=True)
    catalog_product_slug = models.SlugField('Slug catalogue', max_length=80, blank=True, db_index=True)
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
        verbose_name = 'Produit Jumia (test)'
        verbose_name_plural = 'Produits Jumia (test)'
        db_table = 'intelligence_test_jumia_product'
        ordering = ['-scraped_at']

    def __str__(self):
        return f'[TEST] {self.name[:60]} ({self.sku})'
