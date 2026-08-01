from django.db import models


class JumiaCategory(models.Model):
    """Catégorie catalogue Jumia.sn — arborescence pour le crawl et l'analyse TI."""

    slug = models.SlugField('Slug', max_length=120, unique=True, db_index=True)
    name = models.CharField('Nom', max_length=200)
    path = models.CharField(
        'Chemin URL',
        max_length=200,
        unique=True,
        help_text='Ex. /telephones-tablettes/',
    )
    url = models.URLField('URL complète', max_length=500, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Catégorie parente',
    )
    is_active = models.BooleanField('Active', default=True, db_index=True)
    products_count = models.PositiveIntegerField('Nb produits', default=0)
    last_crawled_at = models.DateTimeField('Dernier crawl', null=True, blank=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)

    class Meta:
        verbose_name = 'Catégorie Jumia'
        verbose_name_plural = 'Catégories Jumia'
        ordering = ['path']

    def __str__(self):
        return self.name or self.slug
