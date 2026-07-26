"""Invalidation cache dictionnaire Wolof."""

from django.db.models.signals import post_delete, post_save

from intelligence.models import WolofKeyword
from intelligence.services.wolof_dictionary_service import WolofDictionaryService


def _invalidate_wolof_cache(**kwargs):
    WolofDictionaryService.invalidate_cache()


post_save.connect(_invalidate_wolof_cache, sender=WolofKeyword)
post_delete.connect(_invalidate_wolof_cache, sender=WolofKeyword)
