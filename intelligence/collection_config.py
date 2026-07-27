"""
Configuration centralisée — collecte Google Trends & réseaux sociaux planifiée.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone


def get_collection_config() -> dict[str, Any]:
    """Retourne la configuration de planification (settings + défauts)."""
    return getattr(settings, 'COLLECTION_SCHEDULE', _DEFAULT_CONFIG)


def is_collection_schedule_active(*, at: datetime | None = None) -> tuple[bool, str]:
    """
    Vérifie si les tâches planifiées doivent s'exécuter.

    Si CAMPAIGN_DURATION_DAYS > 0 et CAMPAIGN_START est défini, limite à N jours consécutifs.
    Sinon : exécution permanente (tant que ENABLED=True).
    """
    config = get_collection_config()
    if not config.get('ENABLED', True):
        return False, 'Collecte planifiée désactivée (COLLECTION_ENABLED=False).'

    duration = int(config.get('CAMPAIGN_DURATION_DAYS') or 0)
    start_raw = (config.get('CAMPAIGN_START') or '').strip()

    if duration <= 0 or not start_raw:
        return True, 'Collecte permanente active.'

    try:
        start_day = date.fromisoformat(start_raw)
    except ValueError:
        return True, f'Date de campagne invalide ({start_raw!r}) — collecte autorisée.'

    at = at or timezone.localtime()
    current_day = at.date()
    end_day = start_day + timedelta(days=duration - 1)

    if current_day < start_day:
        return False, f'Campagne non démarrée (début {start_day.isoformat()}).'
    if current_day > end_day:
        return False, f'Campagne terminée (fin {end_day.isoformat()}).'

    return True, f'Campagne jour { (current_day - start_day).days + 1 }/{duration}.'


_DEFAULT_CONFIG: dict[str, Any] = {
    'ENABLED': True,
    'CAMPAIGN_START': '',
    'CAMPAIGN_DURATION_DAYS': 3,
    'GOOGLE_SEED_DELAY_MIN': 20.0,
    'GOOGLE_SEED_DELAY_MAX': 55.0,
    'GOOGLE_DOMAIN_DELAY_MIN': 45.0,
    'GOOGLE_DOMAIN_DELAY_MAX': 120.0,
    'SOCIAL_VIDEO_DELAY_MIN': 12.0,
    'SOCIAL_VIDEO_DELAY_MAX': 45.0,
    'SOCIAL_KEYWORD_DELAY_MIN': 30.0,
    'SOCIAL_KEYWORD_DELAY_MAX': 90.0,
    'SOCIAL_TARGET_DELAY_MIN': 25.0,
    'SOCIAL_TARGET_DELAY_MAX': 70.0,
    'MAX_VIDEOS_PER_KEYWORD_SESSION': 15,
    'MAX_POSTS_PER_TARGET_SESSION': 12,
    'MAX_KEYWORDS_PER_SESSION': 0,
    'MAX_TARGETS_PER_SESSION': 0,
    'NLP_COMMENT_LIMIT': 150,
    'NLP_POST_LIMIT': 75,
    # 0 = pas de plafond global : seul max_videos du mot-clé compte
    'JUMIA_MAX_PRODUCTS_PER_KEYWORD': 0,
    'JUMIA_MAX_REVIEWS_PER_PRODUCT': 20,
    'JUMIA_MAX_LISTING_PAGES': 3,
    'JUMIA_DELAY_MIN': 1.5,
    'JUMIA_DELAY_MAX': 3.5,
    'JUMIA_USE_PLAYWRIGHT': True,
    'JUMIA_SKIP_KNOWN_PRODUCTS': True,
    'JUMIA_MAX_LISTING_SCAN_PAGES': 9,
    'JUMIA_HOMEPAGE_RADAR_ENABLED': True,
    'JUMIA_HOMEPAGE_MAX_PRODUCTS_PER_KEYWORD': 3,
    'JIJI_MAX_LISTINGS_PER_KEYWORD': 0,
    'JIJI_DELAY_MIN': 1.5,
    'JIJI_DELAY_MAX': 3.5,
    'JIJI_USE_PLAYWRIGHT': True,
    'JIJI_REVEAL_CONTACTS': False,
    'JIJI_SKIP_KNOWN_LISTINGS': True,
    'JIJI_SEARCH_FIRST': True,
    'JIJI_HOMEPAGE_RADAR_ENABLED': True,
    'JIJI_HOMEPAGE_MAX_LISTINGS_PER_KEYWORD': 3,
}

# Limites allégées pour la session de test manuelle (20 min max)
TEST_MODE_OVERRIDES: dict[str, Any] = {
    'TEST_SESSION_MINUTES': 20,
    'MAX_KEYWORDS_PER_SESSION': 3,
    'MAX_TARGETS_PER_SESSION': 1,
    'MAX_VIDEOS_PER_KEYWORD_SESSION': 5,
    'MAX_POSTS_PER_TARGET_SESSION': 4,
    'NLP_COMMENT_LIMIT': 30,
    'NLP_POST_LIMIT': 15,
    'SOCIAL_VIDEO_DELAY_MIN': 3.0,
    'SOCIAL_VIDEO_DELAY_MAX': 10.0,
    'SOCIAL_KEYWORD_DELAY_MIN': 3.0,
    'SOCIAL_KEYWORD_DELAY_MAX': 10.0,
    'SOCIAL_TARGET_DELAY_MIN': 3.0,
    'SOCIAL_TARGET_DELAY_MAX': 10.0,
    'GOOGLE_SEED_DELAY_MIN': 5.0,
    'GOOGLE_SEED_DELAY_MAX': 15.0,
    'GOOGLE_DOMAIN_DELAY_MIN': 8.0,
    'GOOGLE_DOMAIN_DELAY_MAX': 20.0,
    # Jumia / Jiji test 20 min — plafond session = MAX_VIDEOS_PER_KEYWORD_SESSION (5)
    'JUMIA_MAX_REVIEWS_PER_PRODUCT': 12,
    'JUMIA_MAX_LISTING_PAGES': 3,
    'JUMIA_DELAY_MIN': 1.2,
    'JUMIA_DELAY_MAX': 2.5,
    'JUMIA_USE_PLAYWRIGHT': True,
    'JIJI_DELAY_MIN': 1.2,
    'JIJI_DELAY_MAX': 2.5,
    'JIJI_USE_PLAYWRIGHT': True,
    'JIJI_REVEAL_CONTACTS': False,
}


def get_effective_collection_config(*, test_mode: bool = False) -> dict[str, Any]:
    """Fusionne la config planifiée avec les surcharges mode test."""
    config = dict(get_collection_config())
    if test_mode:
        config.update(TEST_MODE_OVERRIDES)
    return config


def is_nlp_camembert_enabled() -> bool:
    """True si CamemBERT doit tourner sur le VPS (NLP_CLASSIFIER_ENABLED dans .env)."""
    nlp = getattr(settings, 'NLP_CLASSIFIER', {})
    return bool(nlp.get('ENABLED', True))


def get_nlp_batch_limit(*, default: int = 200) -> int:
    """Plafond batch NLP — aligné sur COLLECTION_NLP_* du .env."""
    config = get_collection_config()
    posts = int(config.get('NLP_POST_LIMIT') or 0)
    comments = int(config.get('NLP_COMMENT_LIMIT') or 0)
    cap = max(posts, comments, default)
    return min(cap, 500)
