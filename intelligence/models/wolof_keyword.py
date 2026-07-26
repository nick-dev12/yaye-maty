"""Mots-clés Wolof configurables pour le filtre NLP hybride."""

from django.db import models


class WolofKeyword(models.Model):
    """Expression Wolof détectée avant CamemBERT (intention d'achat, etc.)."""

    class Intent(models.TextChoices):
        PURCHASE = 'purchase', "Intention d'achat"
        INFO = 'info', "Demande d'information"
        COMPLAINT = 'complaint', 'Plainte'

    expression = models.CharField('Expression', max_length=120)
    intent = models.CharField(
        'Intention',
        max_length=16,
        choices=Intent.choices,
        default=Intent.PURCHASE,
        db_index=True,
    )
    note = models.CharField(
        'Signification (optionnel)',
        max_length=200,
        blank=True,
        help_text='Ex. : combien coûte, je veux acheter',
    )
    is_active = models.BooleanField('Actif', default=True, db_index=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)

    class Meta:
        verbose_name = 'Mot Wolof'
        verbose_name_plural = 'Dictionnaire Wolof'
        ordering = ['intent', 'expression']
        constraints = [
            models.UniqueConstraint(
                fields=['expression', 'intent'],
                name='unique_wolof_keyword_intent',
            ),
        ]

    def __str__(self):
        return self.expression
