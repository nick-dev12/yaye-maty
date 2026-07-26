import hashlib

from django.db import models

from intelligence.models.social_post import SocialPost


class TestSocialPost(models.Model):
    """Publication sociale collectée en session test — table isolée."""

    Platform = SocialPost.Platform
    AnalysisStatus = SocialPost.AnalysisStatus

    platform = models.CharField('Plateforme', max_length=20, choices=Platform.choices, db_index=True)
    platform_post_id = models.CharField('ID vidéo (video_id)', max_length=100, blank=True, db_index=True)
    source_url = models.URLField('URL source', max_length=500)
    post_url = models.URLField('URL publication', max_length=500, blank=True)
    author = models.CharField('Auteur', max_length=120, blank=True)
    content = models.TextField('Description (caption)')
    content_hash = models.CharField('Empreinte', max_length=64, db_index=True)
    hashtags = models.JSONField('Hashtags', default=list, blank=True)
    view_count = models.PositiveIntegerField('Vues', null=True, blank=True)
    like_count = models.PositiveIntegerField('Likes', null=True, blank=True)
    share_count = models.PositiveIntegerField('Partages', null=True, blank=True)
    save_count = models.PositiveIntegerField('Favoris (saves)', null=True, blank=True)
    comment_count = models.PositiveIntegerField('Commentaires (total plateforme)', null=True, blank=True)
    comments_scraped_count = models.PositiveSmallIntegerField('Commentaires collectés', default=0)
    demand_score = models.PositiveIntegerField('Score demande', default=0, db_index=True)
    purchase_intent_count = models.PositiveSmallIntegerField('Intentions achat', default=0)
    published_at = models.DateTimeField('Publié le', null=True, blank=True)
    comments = models.JSONField('Commentaires (JSON)', default=list, blank=True)
    analysis_status = models.CharField(
        'Statut analyse',
        max_length=12,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
        db_index=True,
    )
    category = models.CharField('Catégorie NLP', max_length=80, blank=True)
    extracted_product = models.CharField('Produit principal', max_length=120, blank=True, db_index=True)
    extracted_product_slug = models.SlugField('Slug produit', max_length=80, blank=True, db_index=True)
    sentiment = models.CharField('Sentiment', max_length=20, blank=True)
    keywords = models.JSONField('Mots-clés', default=list, blank=True)
    scraped_at = models.DateTimeField('Collecté le', auto_now_add=True)
    analyzed_at = models.DateTimeField('Analysé le', null=True, blank=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)

    class Meta:
        db_table = 'intelligence_test_socialpost'
        verbose_name = 'Publication test'
        verbose_name_plural = 'Publications test'
        ordering = ['-scraped_at']
        constraints = [
            models.UniqueConstraint(
                fields=['platform', 'content_hash'],
                name='unique_test_social_post_hash',
            ),
            models.UniqueConstraint(
                fields=['platform', 'platform_post_id'],
                condition=models.Q(platform_post_id__gt=''),
                name='unique_test_social_post_platform_id',
            ),
        ]

    def __str__(self):
        preview = self.content[:60] + ('…' if len(self.content) > 60 else '')
        return f'[TEST {self.get_platform_display()}] {preview}'

    build_content_hash = staticmethod(SocialPost.build_content_hash)
    resolve_platform_post_id = staticmethod(SocialPost.resolve_platform_post_id)
