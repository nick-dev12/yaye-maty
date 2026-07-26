"""
Contexte affiché dans la section « Session de test » (collecte manuelle).
"""

from __future__ import annotations

from django.conf import settings

from intelligence.collection_config import (
    TEST_MODE_OVERRIDES,
    get_collection_config,
    get_effective_collection_config,
    is_collection_schedule_active,
)
from intelligence.models import DiscoveryConfig, MarketDomain
from intelligence.services.active_keyword_service import ActiveKeywordService


class CollectionTestContextService:
    """Prépare les données de diagnostic pour les tests immédiats (20 min)."""

    SESSION_MINUTES = int(TEST_MODE_OVERRIDES.get('TEST_SESSION_MINUTES', 20))

    @classmethod
    def build(cls) -> dict:
        prod = get_collection_config()
        test = get_effective_collection_config(test_mode=True)
        campaign_ok, campaign_msg = is_collection_schedule_active()
        discovery = DiscoveryConfig.get_config()
        selected_domains = list(discovery.selected_domains.filter(is_active=True).order_by('label'))
        keywords = ActiveKeywordService.list_for_session()
        social_keywords = ActiveKeywordService.list_for_social()
        scraper = getattr(settings, 'SOCIAL_SCRAPER', {})
        nlp = getattr(settings, 'NLP_CLASSIFIER', {})

        test_keywords = social_keywords[: int(test.get('MAX_KEYWORDS_PER_SESSION') or 2)]

        return {
            'session_minutes': cls.SESSION_MINUTES,
            'campaign_ok': campaign_ok,
            'campaign_message': campaign_msg,
            'production_config': prod,
            'test_config': test,
            'test_overrides': TEST_MODE_OVERRIDES,
            'config_groups': cls._config_groups(prod, test),
            'beat_schedule': cls._beat_schedule(),
            'infrastructure': cls._infrastructure(),
            'scraper': {
                'headless': scraper.get('HEADLESS', False),
                'proxy': scraper.get('PROXY_SERVER') or '—',
                'locale': scraper.get('LOCALE', 'fr-FR'),
                'timezone': scraper.get('TIMEZONE', 'Africa/Dakar'),
            },
            'nlp': {
                'enabled': nlp.get('ENABLED', True),
                'model': nlp.get('MODEL_NAME', '—'),
                'threshold': nlp.get('CONFIDENCE_THRESHOLD', 0.55),
                'comment_limit_prod': prod.get('NLP_COMMENT_LIMIT'),
                'post_limit_prod': prod.get('NLP_POST_LIMIT'),
                'comment_limit_test': test.get('NLP_COMMENT_LIMIT'),
                'post_limit_test': test.get('NLP_POST_LIMIT'),
            },
            'discovery': {
                'timeframe': discovery.get_timeframe_display(),
                'region': discovery.region,
                'selected_count': len(selected_domains),
                'domains': selected_domains,
                'selected_domain_ids': {d.pk for d in selected_domains},
            },
            'domains_all': list(MarketDomain.objects.filter(is_active=True).order_by('label')),
            'keywords': keywords,
            'social_keywords': social_keywords,
            'test_plan': {
                'keywords': test_keywords,
                'keyword_count': len(test_keywords),
            },
        }

    @classmethod
    def _config_groups(cls, prod: dict, test: dict) -> list[dict]:
        def fmt_bool(value) -> str:
            if isinstance(value, bool):
                return 'Oui' if value else 'Non'
            if value in ('', None):
                return '—'
            return str(value)

        def row(label: str, key: str) -> dict:
            p = prod.get(key, '—')
            t = test.get(key, p)
            return {
                'label': label,
                'production': fmt_bool(p),
                'test': fmt_bool(t),
                'changed': t != p,
            }

        def row_range(label: str, min_key: str, max_key: str) -> dict:
            p = f"{prod.get(min_key, '—')} – {prod.get(max_key, '—')} s"
            t = f"{test.get(min_key, '—')} – {test.get(max_key, '—')} s"
            return {
                'label': label,
                'production': p,
                'test': t,
                'changed': p != t,
            }

        return [
            {
                'title': 'Limites par session',
                'rows': [
                    row('Mots-clés réseaux max', 'MAX_KEYWORDS_PER_SESSION'),
                    row('Vidéos / mot-clé (session)', 'MAX_VIDEOS_PER_KEYWORD_SESSION'),
                    row('Posts / mot-clé Facebook', 'MAX_POSTS_PER_TARGET_SESSION'),
                    row('Avis Jumia / produit (plafond)', 'JUMIA_MAX_REVIEWS_PER_PRODUCT'),
                    row('Pages listing Jumia', 'JUMIA_MAX_LISTING_PAGES'),
                    row('Commentaires NLP', 'NLP_COMMENT_LIMIT'),
                    row('Publications NLP', 'NLP_POST_LIMIT'),
                ],
            },
            {
                'title': 'Délais anti-ban (secondes)',
                'rows': [
                    row_range('Google — graine', 'GOOGLE_SEED_DELAY_MIN', 'GOOGLE_SEED_DELAY_MAX'),
                    row_range('Google — domaine', 'GOOGLE_DOMAIN_DELAY_MIN', 'GOOGLE_DOMAIN_DELAY_MAX'),
                    row_range('Réseaux — vidéo', 'SOCIAL_VIDEO_DELAY_MIN', 'SOCIAL_VIDEO_DELAY_MAX'),
                    row_range('Réseaux — mot-clé', 'SOCIAL_KEYWORD_DELAY_MIN', 'SOCIAL_KEYWORD_DELAY_MAX'),
                ],
            },
            {
                'title': 'Campagne planifiée',
                'rows': [
                    row('Collecte activée', 'ENABLED'),
                    row('Début campagne', 'CAMPAIGN_START'),
                    row('Durée (jours)', 'CAMPAIGN_DURATION_DAYS'),
                ],
            },
        ]

    @staticmethod
    def _beat_schedule() -> list[dict]:
        schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
        rows = []
        for name, entry in schedule.items():
            task = entry.get('task', '—')
            sched = entry.get('schedule')
            label = str(sched) if sched is not None else '—'
            rows.append({'name': name, 'task': task, 'schedule': label})
        return rows

    @staticmethod
    def _infrastructure() -> dict:
        return {
            'broker': getattr(settings, 'CELERY_BROKER_URL', '—'),
            'worker_pool': getattr(settings, 'CELERY_WORKER_POOL', 'prefork'),
            'worker_concurrency': getattr(settings, 'CELERY_WORKER_CONCURRENCY', 4),
        }
