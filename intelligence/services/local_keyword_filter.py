"""
Filtre hybride Étape 1 — mots-clés FR + Wolof (marché sénégalais).

Classifie instantanément sans charger CamemBERT (~0 ms).
"""

from __future__ import annotations

import re
import unicodedata

from intelligence.models import WolofKeyword
from intelligence.models.social_comment import SocialComment
from intelligence.services.wolof_dictionary_service import WolofDictionaryService


class LocalKeywordFilter:
    """Classification rapide par dictionnaire local avant CamemBERT."""

    INTENT_LABELS = {
        'intention_achat': SocialComment.Intent.PURCHASE,
        'demande_information': SocialComment.Intent.INFO,
        'plainte': SocialComment.Intent.COMPLAINT,
        'hors_sujet': SocialComment.Intent.OFF_TOPIC,
    }

    # Expressions d'achat — français marché SN
    PURCHASE_FR: tuple[str, ...] = (
        "c'est combien", 'cest combien', 'combien ca coute', 'combien ça coûte',
        'quel est le prix', 'le prix', 'prix svp', 'ou acheter', 'où acheter',
        'en stock', 'avez vous', 'avez-vous', 'disponible', 'commander', 'commande',
        'livraison', 'whatsapp', 'numero', 'numéro', 'contact', 'boutique',
        'je veux acheter', 'je veux commande', 'interesse', 'intéressé',
        'dakar', 'thies', 'thiès', 'touba', 'kaolack', 'saint-louis', 'saint louis',
    )

    # Wolof — chargé depuis le dictionnaire configurable (Paramètres)
    PURCHASE_WOLOF: tuple[str, ...] = ()

    INFO_WOLOF: tuple[str, ...] = ()

    COMPLAINT_WOLOF: tuple[str, ...] = ()

    INFO_FR: tuple[str, ...] = (
        'comment', 'comment ca marche', 'comment ça marche',
        'c est quoi', "c'est quoi", 'expliquer', 'explication',
        'formation', 'conseil', 'astuce', 'tutoriel',
        'quelle marque', 'quel modele', 'quel modèle',
    )

    COMPLAINT_FR: tuple[str, ...] = (
        'arnaque', 'mauvais', 'mauvaise', 'decu', 'déçu', 'deçu',
        'probleme', 'problème', 'panne', 'cher', 'chere', 'chère',
        'pas content', 'nul', 'escroc', 'vol', 'voleur',
    )

    @classmethod
    def classify(cls, text: str) -> dict | None:
        """
        Retourne {intent, confidence, method} ou None si aucun mot-clé détecté.

        confidence élevée (0.92) car match explicite sur expression locale.
        """
        normalized = cls._normalize(text)
        if not normalized or len(normalized) < 3:
            return None

        purchase_wolof = cls._get_wolof_expressions(WolofKeyword.Intent.PURCHASE)
        if cls._match_any(normalized, cls.PURCHASE_FR + purchase_wolof):
            return {
                'intent': SocialComment.Intent.PURCHASE,
                'confidence': 0.92,
                'method': SocialComment.AnalysisMethod.KEYWORD,
            }

        complaint_wolof = cls._get_wolof_expressions(WolofKeyword.Intent.COMPLAINT)
        if cls._match_any(normalized, cls.COMPLAINT_FR + complaint_wolof):
            return {
                'intent': SocialComment.Intent.COMPLAINT,
                'confidence': 0.88,
                'method': SocialComment.AnalysisMethod.KEYWORD,
            }

        info_wolof = cls._get_wolof_expressions(WolofKeyword.Intent.INFO)
        if cls._match_any(normalized, cls.INFO_FR + info_wolof):
            return {
                'intent': SocialComment.Intent.INFO,
                'confidence': 0.85,
                'method': SocialComment.AnalysisMethod.KEYWORD,
            }

        return None

    @classmethod
    def _get_wolof_expressions(cls, intent: str) -> tuple[str, ...]:
        return WolofDictionaryService.get_expressions_by_intent(intent)

    @classmethod
    def classify_post_category(cls, text: str) -> tuple[str, float] | None:
        """Détection rapide de catégorie métier."""
        from intelligence.nlp_taxonomy import CATEGORY_KEYWORDS

        normalized = cls._normalize(text)
        scores: dict[str, int] = {}

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in normalized)
            if score:
                scores[category] = score

        if not scores:
            return None

        best = max(scores, key=scores.get)
        confidence = min(0.95, 0.5 + scores[best] * 0.12)
        return best, confidence

    @staticmethod
    def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in text for pattern in patterns)

    @staticmethod
    def _normalize(text: str) -> str:
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(
            char for char in text
            if not unicodedata.combining(char)
        )
        text = text.lower()
        text = re.sub(r'[^a-z0-9àâäéèêëïîôùûüçñ\s\'-]', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()
