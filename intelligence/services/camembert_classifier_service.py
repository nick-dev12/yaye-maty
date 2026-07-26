"""
Service CamemBERT zero-shot — classification NLP sur le VPS.

Modèle : BaptisteDoyen/camembert-base-xnli (~500 Mo RAM).
Chargé une seule fois par worker Celery (singleton lazy).
"""

from __future__ import annotations

import logging

from django.conf import settings

from intelligence.models.social_comment import SocialComment

logger = logging.getLogger(__name__)

_classifier = None


class CamembertClassifierService:
    """Classification zero-shot en français via CamemBERT."""

    COMMENT_LABELS: tuple[str, ...] = (
        "intention d'achat",
        "demande d'information",
        "plainte",
        "hors sujet",
    )

    CATEGORY_LABELS: tuple[str, ...] = (
        "equipement d'irrigation et pompage",
        "energie solaire pour l'agriculture",
        "tracteurs et machinisme agricole",
        "semences et engrais",
        "elevage et alimentation animale",
        "marche agricole et prix",
        "formation et conseil agricole",
        "autre sujet agricole",
    )

    CATEGORY_SLUG_MAP: dict[str, str] = {
        "equipement d'irrigation et pompage": 'irrigation',
        "energie solaire pour l'agriculture": 'solaire_pompage',
        "tracteurs et machinisme agricole": 'tracteurs_machinisme',
        "semences et engrais": 'semences_engrais',
        "elevage et alimentation animale": 'elevage_alimentation',
        "marche agricole et prix": 'marche_prix',
        "formation et conseil agricole": 'formation_conseil',
        "autre sujet agricole": 'autre',
    }

    INTENT_SLUG_MAP: dict[str, str] = {
        "intention d'achat": SocialComment.Intent.PURCHASE,
        "demande d'information": SocialComment.Intent.INFO,
        "plainte": SocialComment.Intent.COMPLAINT,
        "hors sujet": SocialComment.Intent.OFF_TOPIC,
    }

    SENTIMENT_LABELS: tuple[str, ...] = (
        'sentiment positif',
        'sentiment negatif',
        'sentiment neutre',
    )

    @classmethod
    def classify_comment_intent(cls, text: str) -> dict:
        """Analyse l'intention d'un commentaire."""
        result = cls._run_zero_shot(text, cls.COMMENT_LABELS)
        top_label = result['labels'][0]
        return {
            'intent': cls.INTENT_SLUG_MAP.get(top_label, SocialComment.Intent.OFF_TOPIC),
            'confidence': float(result['scores'][0]),
            'method': SocialComment.AnalysisMethod.CAMEMBERT,
            'raw_label': top_label,
        }

    @classmethod
    def classify_post_category(cls, text: str) -> dict:
        """Analyse la catégorie métier d'une publication."""
        result = cls._run_zero_shot(text[:1500], cls.CATEGORY_LABELS)
        top_label = result['labels'][0]
        return {
            'category': cls.CATEGORY_SLUG_MAP.get(top_label, 'autre'),
            'confidence': float(result['scores'][0]),
            'raw_label': top_label,
        }

    @classmethod
    def classify_sentiment(cls, text: str) -> dict:
        """Analyse le sentiment d'une publication."""
        result = cls._run_zero_shot(text[:1500], cls.SENTIMENT_LABELS)
        top_label = result['labels'][0]
        sentiment = 'neutral'
        if 'positif' in top_label:
            sentiment = 'positive'
        elif 'negatif' in top_label:
            sentiment = 'negative'
        return {'sentiment': sentiment, 'confidence': float(result['scores'][0])}

    @classmethod
    def _run_zero_shot(cls, text: str, labels: tuple[str, ...]) -> dict:
        if not text.strip():
            return {'labels': [labels[-1]], 'scores': [0.0]}

        nlp_settings = getattr(settings, 'NLP_CLASSIFIER', {})
        if not nlp_settings.get('ENABLED', True):
            return {'labels': [labels[-1]], 'scores': [0.0]}

        classifier = cls._get_classifier()
        return classifier(text, labels)

    @classmethod
    def _get_classifier(cls):
        global _classifier
        if _classifier is not None:
            return _classifier

        nlp_settings = getattr(settings, 'NLP_CLASSIFIER', {})
        model_name = nlp_settings.get('MODEL_NAME', 'BaptisteDoyen/camembert-base-xnli')

        logger.info('Chargement CamemBERT : %s', model_name)
        from transformers import pipeline

        _classifier = pipeline(
            'zero-shot-classification',
            model=model_name,
        )
        logger.info('CamemBERT prêt.')
        return _classifier
