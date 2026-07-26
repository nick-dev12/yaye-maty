from django.db import models

from intelligence.scrapers.constants import PLATFORM_FACEBOOK, PLATFORM_TIKTOK


class SocialScrapeTarget(models.Model):
    """Cible de scraping (groupe Facebook, hashtag TikTok, etc.)."""

    class Platform(models.TextChoices):
        FACEBOOK = PLATFORM_FACEBOOK, 'Facebook'
        TIKTOK = PLATFORM_TIKTOK, 'TikTok'

    label = models.CharField('Libellé', max_length=120)
    platform = models.CharField('Plateforme', max_length=20, choices=Platform.choices, db_index=True)
    url = models.URLField('URL cible', max_length=500)
    region = models.CharField('Région cible', max_length=8, default='SN', db_index=True)
    is_active = models.BooleanField('Actif', default=True)
    max_posts = models.PositiveSmallIntegerField('Max publications', default=20)
    scrape_comments = models.BooleanField('Extraire commentaires', default=True)
    max_comments = models.PositiveSmallIntegerField(
        'Commentaires / vidéo',
        default=20,
        help_text='Objectif : 10 à 20 commentaires pour l\'analyse NLP.',
    )
    last_scraped_at = models.DateTimeField('Dernier scrape', null=True, blank=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    class Meta:
        verbose_name = 'Cible réseau social'
        verbose_name_plural = 'Cibles réseaux sociaux'
        ordering = ['platform', 'label']

    def __str__(self):
        return f'{self.label} ({self.get_platform_display()})'
