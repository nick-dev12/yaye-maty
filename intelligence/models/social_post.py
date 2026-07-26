import hashlib

from django.db import models

from intelligence.scrapers.constants import PLATFORM_FACEBOOK, PLATFORM_TIKTOK


class SocialPost(models.Model):
    """Publication extraite d'un réseau social, en attente d'analyse NLP locale."""

    class Platform(models.TextChoices):
        FACEBOOK = PLATFORM_FACEBOOK, 'Facebook'
        TIKTOK = PLATFORM_TIKTOK, 'TikTok'

    class AnalysisStatus(models.TextChoices):
        PENDING = 'pending', 'En attente'
        PROCESSING = 'processing', 'En cours'
        DONE = 'done', 'Analysé'
        FAILED = 'failed', 'Échec'

    platform = models.CharField('Plateforme', max_length=20, choices=Platform.choices, db_index=True)
    platform_post_id = models.CharField(
        'ID vidéo (video_id)',
        max_length=100,
        blank=True,
        db_index=True,
        help_text='Identifiant unique TikTok — anti-doublons.',
    )
    source_url = models.URLField('URL source', max_length=500)
    post_url = models.URLField('URL publication', max_length=500, blank=True)
    author = models.CharField('Auteur', max_length=120, blank=True)
    content = models.TextField(
        'Description (caption)',
        help_text='Texte principal de la publication — matière pour le NLP.',
    )
    content_hash = models.CharField('Empreinte', max_length=64, db_index=True)
    hashtags = models.JSONField(
        'Hashtags',
        default=list,
        blank=True,
        help_text='Filtrage thématique (#AgricultureSenegal, etc.).',
    )
    view_count = models.PositiveIntegerField(
        'Vues', null=True, blank=True,
        help_text='Portée / visibilité globale.',
    )
    like_count = models.PositiveIntegerField(
        'Likes', null=True, blank=True,
        help_text='Approbation immédiate des utilisateurs.',
    )
    share_count = models.PositiveIntegerField(
        'Partages', null=True, blank=True,
        help_text='Intérêt communautaire.',
    )
    save_count = models.PositiveIntegerField(
        'Favoris (saves)', null=True, blank=True,
        help_text='Intention d\'achat — indicateur e-commerce crucial.',
    )
    comment_count = models.PositiveIntegerField(
        'Commentaires (total plateforme)', null=True, blank=True,
    )
    comments_scraped_count = models.PositiveSmallIntegerField(
        'Commentaires collectés',
        default=0,
        help_text='Nombre de commentaires enregistrés (objectif : 10–20).',
    )
    demand_score = models.PositiveIntegerField('Score demande', default=0, db_index=True)
    purchase_intent_count = models.PositiveSmallIntegerField('Intentions achat', default=0)
    published_at = models.DateTimeField(
        'Publié le',
        null=True,
        blank=True,
        help_text='Date publication vidéo — pondération fraîcheur tendance.',
    )
    comments = models.JSONField(
        'Commentaires (JSON)',
        default=list,
        blank=True,
        help_text='10–20 premiers commentaires : text, commented_at, platform_comment_id.',
    )
    analysis_status = models.CharField(
        'Statut analyse',
        max_length=12,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        db_index=True,
    )
    category = models.CharField('Catégorie NLP', max_length=80, blank=True)
    extracted_product = models.CharField(
        'Produit principal',
        max_length=120,
        blank=True,
        db_index=True,
    )
    extracted_product_slug = models.SlugField(
        'Slug produit',
        max_length=80,
        blank=True,
        db_index=True,
    )
    sentiment = models.CharField('Sentiment', max_length=20, blank=True)
    keywords = models.JSONField('Mots-clés', default=list, blank=True)
    scraped_at = models.DateTimeField('Collecté le', auto_now_add=True)
    analyzed_at = models.DateTimeField('Analysé le', null=True, blank=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)

    class Meta:
        verbose_name = 'Publication sociale'
        verbose_name_plural = 'Publications sociales'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['platform', 'content_hash'],
                name='unique_social_post_hash',
            ),
            models.UniqueConstraint(
                fields=['platform', 'platform_post_id'],
                condition=models.Q(platform_post_id__gt=''),
                name='unique_social_post_platform_id',
            ),
        ]

    def __str__(self):
        preview = self.content[:60] + ('…' if len(self.content) > 60 else '')
        return f'[{self.get_platform_display()}] {preview}'

    @property
    def video_id(self) -> str:
        """Alias spec TikTok — identifiant unique vidéo."""
        return self.platform_post_id

    @property
    def caption(self) -> str:
        """Alias spec TikTok — description de la publication."""
        return self.content

    @staticmethod
    def build_content_hash(content: str) -> str:
        normalized = ' '.join(content.lower().split())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    @staticmethod
    def resolve_platform_post_id(platform: str, post_url: str, explicit_id: str = '') -> str:
        if explicit_id:
            return explicit_id[:100]
        from intelligence.scrapers.post_id_utils import extract_post_id
        return extract_post_id(platform, post_url)[:100]
