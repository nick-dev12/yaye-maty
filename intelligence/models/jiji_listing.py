"""Annonce Jiji.sn — marché local (neuf / occasion, prix souvent négociables)."""

from django.db import models

from intelligence.models.social_comment import SocialComment


class JijiListing(models.Model):
    """Fiche annonce Jiji.sn — prix local, état, localisation, profil vendeur."""

    class AnalysisStatus(models.TextChoices):
        PENDING = 'pending', 'En attente'
        PROCESSING = 'processing', 'En cours'
        DONE = 'done', 'Terminé'
        FAILED = 'failed', 'Échec'
        SKIPPED = 'skipped', 'Hors périmètre agricole'

    class Sentiment(models.TextChoices):
        POSITIVE = 'positive', 'Positif'
        NEUTRAL = 'neutral', 'Neutre'
        NEGATIVE = 'negative', 'Négatif'

    Intent = SocialComment.Intent
    AnalysisMethod = SocialComment.AnalysisMethod

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
    analysis_status = models.CharField(
        'Statut NLP',
        max_length=16,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        db_index=True,
    )
    is_analyzed = models.BooleanField('Analysé', default=False, db_index=True)
    analyzed_at = models.DateTimeField('Analysé le', null=True, blank=True)
    nlp_analyzed_at = models.DateTimeField('NLP le', null=True, blank=True)
    sentiment = models.CharField(
        'Sentiment annonce',
        max_length=16,
        choices=Sentiment.choices,
        blank=True,
        db_index=True,
    )
    intent = models.CharField(
        'Intention détectée',
        max_length=32,
        choices=Intent.choices,
        blank=True,
        db_index=True,
    )
    extracted_product = models.CharField('Produit extrait', max_length=120, blank=True, db_index=True)
    nlp_category = models.CharField('Catégorie NLP', max_length=64, blank=True, db_index=True)
    keywords_detected = models.JSONField('Mots-clés détectés', default=list, blank=True)
    relevance_score = models.FloatField('Pertinence agricole', null=True, blank=True, db_index=True)
    is_agricultural = models.BooleanField(
        'Pertinent agricole',
        default=True,
        db_index=True,
        help_text='False si l\'annonce est hors périmètre équipement agricole.',
    )
    aspects = models.JSONField('Aspects détectés', default=dict, blank=True)
    analysis_method = models.CharField(
        'Méthode analyse',
        max_length=16,
        choices=AnalysisMethod.choices,
        default=AnalysisMethod.PENDING,
    )
    confidence_score = models.FloatField('Confiance NLP', null=True, blank=True)
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
            models.Index(fields=['is_analyzed', '-relevance_score']),
            models.Index(fields=['is_agricultural', '-views_count']),
        ]

    def __str__(self):
        return f'{self.title[:60]} ({self.listing_id})'

    @property
    def text(self) -> str:
        """Texte combiné titre + description pour le pipeline NLP."""
        parts = [p for p in (self.title, self.description, self.search_keyword) if p]
        return ' — '.join(parts)
