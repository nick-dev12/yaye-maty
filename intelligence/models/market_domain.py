from django.db import models
from django.utils.text import slugify


class MarketDomain(models.Model):
    """Domaine Google Trends configurable (catégorie + mots-clés de départ)."""

    slug = models.SlugField('Identifiant', max_length=80, unique=True)
    label = models.CharField('Nom du domaine', max_length=120)
    cat_id = models.PositiveIntegerField('Catégorie Google Trends (ID)')
    seed_keywords = models.TextField(
        'Mots-clés de départ',
        help_text='Séparez les mots-clés par des virgules.',
    )
    is_active = models.BooleanField('Actif', default=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    class Meta:
        verbose_name = 'Domaine de marché'
        verbose_name_plural = 'Domaines de marché'
        ordering = ['label']

    def __str__(self):
        return f'{self.label} (cat. {self.cat_id})'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self) -> str:
        base = slugify(self.label) or 'domaine'
        slug = base
        counter = 1
        while MarketDomain.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug

    def get_seed_list(self) -> list[str]:
        return [s.strip() for s in self.seed_keywords.split(',') if s.strip()]

    @property
    def short_label(self) -> str:
        return self.label.split('(')[0].strip()

    @property
    def seed_count(self) -> int:
        return len(self.get_seed_list())


class DiscoveryConfig(models.Model):
    """Configuration globale de la découverte (singleton)."""

    TIMEFRAME_CHOICES = [
        ('today 1-m', 'Dernier mois'),
        ('today 3-m', '3 derniers mois'),
        ('today 12-m', '12 derniers mois'),
    ]

    timeframe = models.CharField(
        'Période',
        max_length=20,
        choices=TIMEFRAME_CHOICES,
        default='today 3-m',
    )
    region = models.CharField('Région', max_length=5, default='SN')
    selected_domains = models.ManyToManyField(
        MarketDomain,
        blank=True,
        verbose_name='Domaines sélectionnés',
        related_name='discovery_configs',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuration de découverte'
        verbose_name_plural = 'Configuration de découverte'

    def __str__(self):
        return 'Configuration découverte'

    @classmethod
    def get_config(cls) -> 'DiscoveryConfig':
        config, _ = cls.objects.get_or_create(pk=1)
        return config
