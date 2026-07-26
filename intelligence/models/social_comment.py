import hashlib

from django.db import models

from intelligence.models.social_post import SocialPost


class SocialComment(models.Model):
    """Commentaire extrait d'une publication sociale — analyse NLP par commentaire."""

    class Intent(models.TextChoices):
        PURCHASE = 'intention_achat', "Intention d'achat"
        INFO = 'demande_information', "Demande d'information"
        OFF_TOPIC = 'hors_sujet', 'Hors sujet'
        COMPLAINT = 'plainte', 'Plainte'

    class AnalysisMethod(models.TextChoices):
        KEYWORD = 'keyword', 'Filtre mots-clés (FR/Wolof)'
        CAMEMBERT = 'camembert', 'CamemBERT zero-shot'
        PENDING = 'pending', 'En attente'

    post = models.ForeignKey(
        SocialPost,
        on_delete=models.CASCADE,
        related_name='social_comments',
        verbose_name='Publication',
    )
    platform_comment_id = models.CharField('ID commentaire', max_length=100, blank=True, db_index=True)
    text = models.TextField('Texte du commentaire')
    text_hash = models.CharField('Empreinte', max_length=64, db_index=True)
    published_at = models.DateTimeField(
        'Date du commentaire',
        null=True,
        blank=True,
        help_text='commented_at — corrélation intérêt / temps.',
    )
    intent = models.CharField(
        'Intention',
        max_length=32,
        choices=Intent.choices,
        blank=True,
        db_index=True,
    )
    extracted_product = models.CharField(
        'Produit extrait',
        max_length=120,
        blank=True,
        db_index=True,
        help_text='Nom normalisé détecté (ex. motopompe, mini tracteur).',
    )
    extracted_product_slug = models.SlugField(
        'Slug produit',
        max_length=80,
        blank=True,
        db_index=True,
    )
    confidence_score = models.FloatField('Confiance', null=True, blank=True)
    analysis_method = models.CharField(
        'Méthode',
        max_length=16,
        choices=AnalysisMethod.choices,
        default=AnalysisMethod.PENDING,
    )
    is_analyzed = models.BooleanField('Analysé', default=False, db_index=True)
    analyzed_at = models.DateTimeField('Analysé le', null=True, blank=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    class Meta:
        verbose_name = 'Commentaire social'
        verbose_name_plural = 'Commentaires sociaux'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['post', 'text_hash'],
                name='unique_social_comment_hash',
            ),
            models.UniqueConstraint(
                fields=['post', 'platform_comment_id'],
                condition=models.Q(platform_comment_id__gt=''),
                name='unique_social_comment_platform_id',
            ),
        ]

    def __str__(self):
        preview = self.text[:50] + ('…' if len(self.text) > 50 else '')
        return preview

    @property
    def commented_at(self):
        """Alias spec TikTok."""
        return self.published_at

    @staticmethod
    def build_text_hash(text: str) -> str:
        normalized = ' '.join(text.lower().split())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
