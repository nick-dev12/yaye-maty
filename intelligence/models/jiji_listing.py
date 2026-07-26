"""Annonce Jiji.sn — marché local (neuf / occasion, prix souvent négociables)."""

from django.db import models


class JijiListing(models.Model):
    """Fiche annonce Jiji.sn — prix local, état, localisation, profil vendeur."""

    class Condition(models.TextChoices):
        NEW = 'new', 'Neuf'
        USED = 'used', 'Occasion'
        REFURBISHED = 'refurbished', 'Reconditionné'
        UNKNOWN = 'unknown', 'Inconnu'

    listing_id = models.CharField('ID annonce', max_length=80, unique=True, db_index=True)
    listing_url = models.URLField('URL annonce', max_length=500)
    title = models.CharField('Titre', max_length=400)
    category = models.CharField('Catégorie', max_length=160, blank=True)
    price_xof = models.DecimalField(
        'Prix (FCFA)', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    is_negotiable = models.BooleanField('Négociable', default=False, db_index=True)
    currency = models.CharField('Devise', max_length=8, default='XOF')
    condition = models.CharField(
        'État',
        max_length=20,
        choices=Condition.choices,
        default=Condition.UNKNOWN,
        db_index=True,
    )
    location_region = models.CharField('Région', max_length=120, blank=True, db_index=True)
    location_area = models.CharField('Quartier / zone', max_length=120, blank=True, db_index=True)
    views_count = models.PositiveIntegerField('Vues', default=0, db_index=True)
    seller_name = models.CharField('Vendeur', max_length=160, blank=True, db_index=True)
    seller_member_since = models.CharField('Ancienneté vendeur', max_length=80, blank=True)
    seller_is_verified = models.BooleanField('Vendeur vérifié', default=False)
    seller_is_premium = models.BooleanField('Vendeur premium', default=False)
    seller_response_stat = models.CharField('Réactivité vendeur', max_length=120, blank=True)
    seller_ads_count = models.PositiveIntegerField(
        'Annonces vendeur (estim.)', null=True, blank=True,
    )
    search_keyword = models.CharField(
        'Mot-clé source',
        max_length=120,
        blank=True,
        db_index=True,
        help_text='Mot-clé MarketSearchKeyword ayant conduit à cette annonce.',
    )
    catalog_product_slug = models.SlugField(
        'Slug catalogue YAYEMATY',
        max_length=80,
        blank=True,
        db_index=True,
    )
    description = models.TextField('Description', blank=True)
    image_url = models.URLField('Image', max_length=500, blank=True)
    attributes = models.JSONField('Attributs', default=dict, blank=True)
    phone_revealed = models.BooleanField(
        'Contact révélé',
        default=False,
        help_text='True uniquement si JIJI_REVEAL_CONTACTS activé (limite IP Jiji).',
    )
    scraped_at = models.DateTimeField('Scrapé le', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)

    class Meta:
        verbose_name = 'Annonce Jiji'
        verbose_name_plural = 'Annonces Jiji'
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['search_keyword', '-views_count']),
            models.Index(fields=['condition', '-price_xof']),
            models.Index(fields=['catalog_product_slug', '-price_xof']),
            models.Index(fields=['location_region', '-views_count']),
        ]

    def __str__(self):
        return f'{self.title[:60]} ({self.listing_id})'
