"""
Service dictionnaire Wolof — chargement pour le filtre NLP.
"""

from __future__ import annotations

from intelligence.models import WolofKeyword
from intelligence.models.social_comment import SocialComment


class WolofDictionaryService:
    """Gère les expressions Wolof configurables en base."""

    _cache: dict[str, tuple[str, ...]] | None = None

    INTENT_TO_SOCIAL = {
        WolofKeyword.Intent.PURCHASE: SocialComment.Intent.PURCHASE,
        WolofKeyword.Intent.INFO: SocialComment.Intent.INFO,
        WolofKeyword.Intent.COMPLAINT: SocialComment.Intent.COMPLAINT,
    }

    @classmethod
    def get_expressions_by_intent(cls, intent: str) -> tuple[str, ...]:
        """Retourne les expressions actives pour une intention."""
        if cls._cache is None:
            cls.refresh_cache()
        return cls._cache.get(intent, ())

    @classmethod
    def get_all_grouped(cls) -> dict[str, list[WolofKeyword]]:
        """Liste groupée pour la page Paramètres."""
        grouped = {key: [] for key in WolofKeyword.Intent.values}
        for keyword in WolofKeyword.objects.all().order_by('expression'):
            grouped[keyword.intent].append(keyword)
        return grouped

    @classmethod
    def get_stats(cls) -> dict[str, int]:
        qs = WolofKeyword.objects.filter(is_active=True)
        return {
            'total': WolofKeyword.objects.count(),
            'active': qs.count(),
            'purchase': qs.filter(intent=WolofKeyword.Intent.PURCHASE).count(),
        }

    @classmethod
    def refresh_cache(cls) -> None:
        """Recharge le cache depuis PostgreSQL."""
        cls._cache = {}
        for intent in WolofKeyword.Intent.values:
            expressions = tuple(
                WolofKeyword.objects.filter(
                    is_active=True,
                    intent=intent,
                ).values_list('expression', flat=True)
            )
            cls._cache[intent] = expressions

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._cache = None
