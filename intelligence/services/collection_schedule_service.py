"""
Orchestration planifiée — Google Trends (macro) et réseaux sociaux (micro).

Sessions courtes, intervalles aléatoires, anti-doublon, puis NLP en tâche séparée (Celery Beat).
"""

from __future__ import annotations

import logging
import random

from intelligence.collection_config import get_collection_config, is_collection_schedule_active
from intelligence.models import MarketSearchKeyword
from intelligence.scrapers.human_behavior import random_sleep
from intelligence.services.active_keyword_service import ActiveKeywordService
from intelligence.services.discovery_config_service import DiscoveryConfigService
from intelligence.services.search_top_down_service import SearchTopDownService
from intelligence.services.social_extraction_service import SocialExtractionService

logger = logging.getLogger(__name__)


class CollectionScheduleService:
    """Sessions de collecte déclenchées par Celery Beat."""

    @classmethod
    def run_google_discovery_session(cls) -> dict:
        """
        Google Trends — 1 session/jour recommandée (ex. 03h00).

        Découvre de nouvelles requêtes ; les doublons sont ignorés en base (contrainte unique).
        """
        active, reason = is_collection_schedule_active()
        if not active:
            logger.info('Session Google Trends ignorée : %s', reason)
            return {'success': False, 'skipped': True, 'reason': reason}

        try:
            stats = DiscoveryConfigService.run_discovery()
        except RuntimeError as exc:
            logger.warning('Session Google Trends : %s', exc)
            return {'success': False, 'message': str(exc)}

        summary = {
            'success': True,
            'skipped': False,
            'reason': reason,
            'stats': stats,
        }
        logger.info('Session Google Trends terminée : %s', summary)
        return summary

    @classmethod
    def run_social_collection_session(cls, *, headless: bool | None = None) -> dict:
        """
        Réseaux sociaux — 2 à 3 sessions/jour (ex. 08h15, 14h15, 20h15).

        Uniquement mots-clés actifs Paramètres (TikTok Top-Down, Facebook recherche).
        """
        active, reason = is_collection_schedule_active()
        if not active:
            logger.info('Session réseaux ignorée : %s', reason)
            return {'success': False, 'skipped': True, 'reason': reason}

        config = get_collection_config()
        top_down = SearchTopDownService()
        keyword_search = SocialExtractionService()

        max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
        keywords = ActiveKeywordService.list_for_social(
            limit=max_kw if max_kw > 0 else 0,
        )

        created_total = 0
        for keyword in keywords:
            if keyword.platform == MarketSearchKeyword.Platform.TIKTOK:
                result = top_down.run_keyword(keyword, headless=headless, scheduled=True)
                created_total += result.created
            else:
                fb = keyword_search.run_keyword_search(
                    keyword,
                    headless=headless,
                    max_posts=int(config.get('MAX_POSTS_PER_TARGET_SESSION') or 12),
                    skip_existing=True,
                )
                created_total += fb.created
            random_sleep(
                config['SOCIAL_KEYWORD_DELAY_MIN'],
                config['SOCIAL_KEYWORD_DELAY_MAX'],
            )

        summary = {
            'success': True,
            'skipped': False,
            'reason': reason,
            'keywords_processed': len(keywords),
            'top_down': {
                'keywords': len(keywords),
                'created': created_total,
            },
            'bottom_up': {
                'targets': 0,
                'created': 0,
            },
        }
        logger.info('Session réseaux terminée : %s', summary)
        return summary

    @classmethod
    def run_nlp_analysis_session(cls) -> dict:
        """Pipeline NLP — après les sessions de scraping (ex. 09h, 15h, 21h)."""
        active, reason = is_collection_schedule_active()
        if not active:
            logger.info('Session NLP ignorée : %s', reason)
            return {'success': False, 'skipped': True, 'reason': reason}

        config = get_collection_config()
        from intelligence.services.nlp_analysis_service import NlpAnalysisService

        result = NlpAnalysisService.run_full_pipeline(
            comment_limit=int(config.get('NLP_COMMENT_LIMIT') or 150),
            post_limit=int(config.get('NLP_POST_LIMIT') or 75),
        )
        result['success'] = True
        result['skipped'] = False
        result['reason'] = reason
        logger.info('Session NLP terminée : %s', result)
        return result

    @classmethod
    def run_jumia_collection_session(cls) -> dict:
        """
        Jumia — sessions planifiées pendant la campagne (ex. 07h30, 13h30, 19h30).

        Collecte prix/stock/avis via mots-clés Paramètres, analyse lexicale légère
        des avis (sans CamemBERT — réservé machine locale), puis signaux marché.
        """
        active, reason = is_collection_schedule_active()
        if not active:
            logger.info('Session Jumia ignorée : %s', reason)
            return {'success': False, 'skipped': True, 'reason': reason}

        from intelligence.collection_config import get_nlp_batch_limit
        from intelligence.services.jumia_collection_service import JumiaCollectionService
        from intelligence.services.jumia_market_signal_service import JumiaMarketSignalService
        from intelligence.services.jumia_nlp_analysis_service import JumiaNlpAnalysisService

        collect = JumiaCollectionService.run(test_mode=False)
        nlp = JumiaNlpAnalysisService.analyze_pending_locally(
            limit=get_nlp_batch_limit(default=200),
        )
        try:
            JumiaMarketSignalService.refresh_all()
        except Exception:
            logger.exception('Refresh signaux Jumia après session planifiée')

        summary = {
            'success': bool(collect.get('success')),
            'skipped': False,
            'reason': reason,
            'collect': collect,
            'nlp': nlp,
            'products_created': collect.get('products_created', 0),
            'reviews_created': collect.get('reviews_created', 0),
            'nouvelles_donnees': collect.get('nouvelles_donnees', 0),
        }
        logger.info('Session Jumia terminée : %s', {
            'success': summary['success'],
            'products': summary['products_created'],
            'reviews': summary['reviews_created'],
            'nlp': nlp,
            'reason': reason,
        })
        return summary

    @classmethod
    def run_jiji_collection_session(cls) -> dict:
        """
        Jiji — sessions planifiées pendant la campagne (ex. 06h45, 12h45, 18h45).

        Collecte annonces locales (neuf/occasion) via mots-clés Paramètres,
        puis recalcule arbitrage Jumia vs Jiji + top vendeurs.
        """
        active, reason = is_collection_schedule_active()
        if not active:
            logger.info('Session Jiji ignorée : %s', reason)
            return {'success': False, 'skipped': True, 'reason': reason}

        from intelligence.collection_config import get_nlp_batch_limit
        from intelligence.services.jiji_collection_service import JijiCollectionService
        from intelligence.services.jiji_market_signal_service import JijiMarketSignalService
        from intelligence.services.jiji_nlp_analysis_service import JijiNlpAnalysisService

        collect = JijiCollectionService.run(test_mode=False)
        nlp = JijiNlpAnalysisService.analyze_pending_locally(
            limit=get_nlp_batch_limit(default=200),
        )
        try:
            hints = JijiMarketSignalService.refresh_arbitrage_hints()
        except Exception:
            logger.exception('Refresh signaux Jiji après session planifiée')
            hints = {}

        summary = {
            'success': bool(collect.get('success')),
            'skipped': False,
            'reason': reason,
            'collect': collect,
            'nlp': nlp,
            'hints': hints,
            'listings_created': collect.get('listings_created', 0),
            'nouvelles_donnees': collect.get('nouvelles_donnees', 0),
        }
        logger.info('Session Jiji terminée : %s', {
            'success': summary['success'],
            'listings': summary['listings_created'],
            'reason': reason,
        })
        return summary
