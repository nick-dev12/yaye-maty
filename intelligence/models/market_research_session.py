"""Session de recherche marché Trade Intelligence — collecte + analyse DeepSeek."""

from django.db import models


class MarketResearchSession(models.Model):
    """Une analyse Domaine + Mot-clé lancée depuis /intelligence/."""

    DURATION_CHOICES = (
        (10, '10 mn'),
        (20, '20 mn'),
        (30, '30 mn'),
        (60, '1 H'),
        (120, '2 H'),
        (180, '3 H'),
        (240, '4 H'),
        (300, '5 H'),
    )

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        COLLECTING = 'collecting', 'Collecte en cours'
        ANALYZING = 'analyzing', 'Analyse IA'
        DONE = 'done', 'Terminé'
        FAILED = 'failed', 'Échec'
        STOPPED = 'stopped', 'Arrêté (analyse)'

    domain = models.ForeignKey(
        'intelligence.MarketDomain',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='research_sessions',
        verbose_name='Domaine',
    )
    domain_slug = models.SlugField('Domaine (slug)', max_length=80)
    domain_label = models.CharField('Domaine', max_length=120)
    # Compat / affichage : rempli avec le mot-clé (plus de catégories UI)
    category_slug = models.SlugField('Catégorie (slug)', max_length=80, blank=True)
    category_label = models.CharField('Catégorie', max_length=120, blank=True)
    keyword = models.CharField('Mot-clé', max_length=200, blank=True, db_index=True)
    search_query = models.CharField('Requête de recherche', max_length=300, db_index=True)
    duration_minutes = models.PositiveIntegerField(
        'Durée max (minutes)',
        default=20,
        choices=DURATION_CHOICES,
    )
    # Sources collectées : google, jumia, jiji, tiktok (JSON list)
    sources = models.JSONField('Sources', default=list, blank=True)

    status = models.CharField(
        'Statut',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    celery_task_id = models.CharField('Tâche Celery', max_length=64, blank=True, db_index=True)
    progress_message = models.CharField('Message progression', max_length=300, blank=True)
    progress_percent = models.PositiveSmallIntegerField('Progression %', default=0)

    collect_payload = models.JSONField('Données collectées', default=dict, blank=True)
    deepseek_web_context = models.TextField('Contexte web DeepSeek', blank=True)
    analysis_result = models.JSONField('Résultat analyse', default=dict, blank=True)
    error_message = models.TextField('Erreur', blank=True)

    started_at = models.DateTimeField('Démarré le', null=True, blank=True)
    completed_at = models.DateTimeField('Terminé le', null=True, blank=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    class Meta:
        verbose_name = 'Session recherche marché'
        verbose_name_plural = 'Sessions recherche marché'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.domain_label} / {self.keyword or self.category_label} ({self.get_status_display()})'
