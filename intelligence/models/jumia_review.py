import hashlib

from django.db import models

from intelligence.models.jumia_product import JumiaProduct
from intelligence.models.social_comment import SocialComment


class JumiaReview(models.Model):
    """Avis client Jumia — texte + étoiles pour analyse hybride NLP."""

    class Sentiment(models.TextChoices):
        POSITIVE = 'positive', 'Positif'
        NEGATIVE = 'negative', 'Négatif'
        NEUTRAL = 'neutral', 'Neutre'

    Intent = SocialComment.Intent
    AnalysisMethod = SocialComment.AnalysisMethod

    product = models.ForeignKey(
        JumiaProduct,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Produit',
    )
    review_hash = models.CharField('Empreinte', max_length=64, db_index=True)
    rating_stars = models.PositiveSmallIntegerField(
        'Étoiles',
        null=True,
        blank=True,
        db_index=True,
        help_text='Note individuelle 1–5.',
    )
    title = models.CharField('Titre', max_length=200, blank=True)
    comment_text = models.TextField('Commentaire', blank=True)
    author = models.CharField('Auteur', max_length=120, blank=True)
    review_date = models.DateField('Date avis', null=True, blank=True, db_index=True)
    verified_purchase = models.BooleanField('Achat vérifié', default=False)
    intent = models.CharField(
        'Intention',
        max_length=32,
        choices=Intent.choices,
        blank=True,
        db_index=True,
    )
    sentiment = models.CharField(
        'Sentiment',
        max_length=16,
        choices=Sentiment.choices,
        blank=True,
        db_index=True,
    )
    aspects = models.JSONField(
        'Aspects détectés',
        default=dict,
        blank=True,
        help_text='Ex. {"qualite": "neg", "livraison": "neg", "prix": "pos"}',
    )
    failure_tags = models.JSONField(
        'Tags de failles',
        default=list,
        blank=True,
        help_text='Ex. ["fragile", "panne", "livraison_retard"]',
    )
    aspect_confidence = models.FloatField('Confiance aspects', null=True, blank=True)
    extracted_product = models.CharField('Produit extrait', max_length=120, blank=True, db_index=True)
    extracted_product_slug = models.SlugField('Slug produit', max_length=80, blank=True, db_index=True)
    confidence_score = models.FloatField('Confiance', null=True, blank=True)
    analysis_method = models.CharField(
        'Méthode',
        max_length=16,
        choices=AnalysisMethod.choices,
        default=AnalysisMethod.PENDING,
    )
    is_analyzed = models.BooleanField('Analysé', default=False, db_index=True)
    analyzed_at = models.DateTimeField('Analysé le', null=True, blank=True)
    scraped_at = models.DateTimeField('Scrapé le', auto_now_add=True)

    class Meta:
        verbose_name = 'Avis Jumia'
        verbose_name_plural = 'Avis Jumia'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'review_hash'],
                name='unique_jumia_review_hash',
            ),
        ]

    def __str__(self):
        preview = (self.comment_text or self.title or '')[:50]
        return f'{self.rating_stars}★ {preview}'

    @property
    def text(self) -> str:
        """Texte combiné pour le pipeline NLP."""
        parts = [p for p in (self.title, self.comment_text) if p]
        return ' — '.join(parts)

    @staticmethod
    def build_review_hash(*, title: str, comment_text: str, author: str, rating_stars: int | None) -> str:
        raw = f'{rating_stars or 0}|{author}|{title}|{comment_text}'.lower()
        normalized = ' '.join(raw.split())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
