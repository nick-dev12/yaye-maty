import hashlib

from django.db import models

from intelligence.models.social_comment import SocialComment
from intelligence.models.test.test_social_post import TestSocialPost


class TestSocialComment(models.Model):
    """Commentaire social session test — table isolée."""

    Intent = SocialComment.Intent
    AnalysisMethod = SocialComment.AnalysisMethod

    post = models.ForeignKey(
        TestSocialPost,
        on_delete=models.CASCADE,
        related_name='social_comments',
        verbose_name='Publication test',
    )
    platform_comment_id = models.CharField('ID commentaire', max_length=100, blank=True, db_index=True)
    text = models.TextField('Texte du commentaire')
    text_hash = models.CharField('Empreinte', max_length=64, db_index=True)
    published_at = models.DateTimeField('Date du commentaire', null=True, blank=True)
    intent = models.CharField('Intention', max_length=32, choices=Intent.choices, blank=True, db_index=True)
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
    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    class Meta:
        db_table = 'intelligence_test_socialcomment'
        verbose_name = 'Commentaire test'
        verbose_name_plural = 'Commentaires test'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['post', 'text_hash'],
                name='unique_test_social_comment_hash',
            ),
            models.UniqueConstraint(
                fields=['post', 'platform_comment_id'],
                condition=models.Q(platform_comment_id__gt=''),
                name='unique_test_social_comment_platform_id',
            ),
        ]

    def __str__(self):
        preview = self.text[:50] + ('…' if len(self.text) > 50 else '')
        return preview

    build_text_hash = staticmethod(SocialComment.build_text_hash)
