"""Rapport DeepSeek Import Master — comparaison multi-domaines + sourcing."""

from django.db import models


class ImportMasterDomainAnalysis(models.Model):
    """Une analyse comparative domaines + prix Alibaba/AliExpress/Amazon."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        RUNNING = 'running', 'En cours'
        DONE = 'done', 'Terminé'
        FAILED = 'failed', 'Échec'
        STOPPED = 'stopped', 'Arrêtée'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    progress_percent = models.PositiveSmallIntegerField(default=0)
    progress_message = models.CharField(max_length=300, blank=True, default='')
    domains_snapshot = models.JSONField(default=list, blank=True)
    web_context = models.TextField(blank=True, default='')
    analysis_result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Analyse Import Master domaines'
        verbose_name_plural = 'Analyses Import Master domaines'

    def __str__(self) -> str:
        return f'ImportMasterDomainAnalysis #{self.pk} ({self.status})'
