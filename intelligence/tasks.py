"""
Tâches Celery — NLP hybride (filtre Wolof/FR + CamemBERT) sur le VPS.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='intelligence.lancer_collecte_manuelle', time_limit=3600)
def lancer_collecte_manuelle(
    self,
    job: str = 'full',
    keyword_id: int | None = None,
    test_mode: bool = False,
) -> dict:
    """
    Collecte manuelle avec progression temps réel (tableau de bord).

    job : google | social | nlp | full | keyword | jumia | jiji
    test_mode : limites réduites + fenêtre max 20 min + tables test isolées
    """
    import time

    from intelligence.collection_config import get_effective_collection_config
    from intelligence.services.collection_abort import reset_abort_hook, set_abort_hook
    from intelligence.services.collection_cancel_service import CollectionCancelService
    from intelligence.services.collection_run_context import (
        CollectionRunContext,
        reset_collection_context,
        set_collection_context,
    )
    from intelligence.services.manual_collection_service import ManualCollectionService

    task_id = self.request.id
    CollectionCancelService.clear(task_id)
    job = (job or ManualCollectionService.JOB_FULL).strip().lower()
    config = get_effective_collection_config(test_mode=test_mode)
    session_seconds = int(config.get('TEST_SESSION_MINUTES', 20)) * 60 if test_mode else 0
    started_at = time.monotonic()

    ctx_token = None
    if test_mode:
        ctx_token = set_collection_context(CollectionRunContext.test())

    def progress(pourcentage: int, message: str, phase: str = 'collecte') -> None:
        self.update_state(
            state='PROGRESS',
            meta={
                'pourcentage': pourcentage,
                'message': message,
                'phase': phase,
                'can_stop': (
                    (phase == 'collecte' and job != ManualCollectionService.JOB_NLP)
                    or (phase == 'nlp' and job == ManualCollectionService.JOB_NLP)
                ),
                'test_mode': test_mode,
            },
        )

    def should_cancel() -> bool:
        if CollectionCancelService.is_cancelled(task_id):
            return True
        if test_mode and session_seconds and (time.monotonic() - started_at) >= session_seconds:
            return True
        return False

    intro = 'Initialisation du test (20 min max)…' if test_mode else 'Initialisation de la collecte…'
    progress(5, intro, phase='collecte')

    # Rend annulables les pauses anti-bot au fond des scrapers (Playwright, HTTP).
    abort_token = set_abort_hook(should_cancel)

    try:
        result = ManualCollectionService.run_job(
            job,
            keyword_id=keyword_id,
            progress=progress,
            should_cancel=should_cancel,
            auto_nlp_after=True,
            test_mode=test_mode,
        )
    except ValueError as exc:
        progress(0, str(exc), phase='collecte')
        raise
    finally:
        reset_abort_hook(abort_token)
        CollectionCancelService.clear(task_id)
        if ctx_token is not None:
            reset_collection_context(ctx_token)

    return {
        'pourcentage': 100,
        'message': result.get('message', 'Terminé avec succès.'),
        'nouvelles_donnees': result.get('nouvelles_donnees', 0),
        'phase': 'done',
        'test_mode': test_mode,
        'details': result,
    }


@shared_task(name='intelligence.ping_celery')
def ping_celery() -> dict:
    """Tâche de santé — utilisée par check_infrastructure."""
    return {'status': 'ok', 'service': 'yayematy-celery'}


@shared_task(name='intelligence.sync_social_comments')
def sync_social_comments(limit: int = 200) -> dict:
    """Synchronise les commentaires JSON vers SocialComment."""
    from intelligence.services.nlp_analysis_service import NlpAnalysisService

    stats = NlpAnalysisService.sync_comments_from_posts(limit=limit)
    logger.info('Sync commentaires : %s', stats)
    return stats


@shared_task(name='intelligence.analyze_comments_intent')
def analyze_comments_intent(limit: int = 100) -> dict:
    """Analyse hybride des intentions de commentaires."""
    from intelligence.services.nlp_analysis_service import NlpAnalysisService

    stats = NlpAnalysisService.analyze_pending_comments(limit=limit)
    logger.info('Analyse commentaires : %s', stats)
    return stats


@shared_task(name='intelligence.analyze_social_posts')
def analyze_social_posts(limit: int = 50) -> dict:
    """Analyse catégorie + sentiment des publications."""
    from intelligence.services.nlp_analysis_service import NlpAnalysisService

    stats = NlpAnalysisService.analyze_pending_posts(limit=limit)
    logger.info('Analyse publications : %s', stats)
    return stats


@shared_task(name='intelligence.scraper_google_trends')
def scraper_google_trends() -> dict:
    """Session Google Trends planifiée (Celery Beat — ex. 03h00)."""
    from intelligence.services.collection_schedule_service import CollectionScheduleService

    return CollectionScheduleService.run_google_discovery_session()


@shared_task(name='intelligence.scraper_reseaux_sociaux')
def scraper_reseaux_sociaux() -> dict:
    """Session scraping réseaux planifiée (Celery Beat — ex. 08h15, 14h15, 20h15)."""
    from intelligence.services.collection_schedule_service import CollectionScheduleService

    return CollectionScheduleService.run_social_collection_session()


@shared_task(name='intelligence.scraper_jumia', time_limit=3600)
def scraper_jumia() -> dict:
    """Session Jumia planifiée (Celery Beat — campagne 3 jours, ex. 07h30/13h30/19h30)."""
    from intelligence.services.collection_schedule_service import CollectionScheduleService

    return CollectionScheduleService.run_jumia_collection_session()


@shared_task(name='intelligence.scraper_jiji', time_limit=3600)
def scraper_jiji() -> dict:
    """Session Jiji planifiée (Celery Beat — campagne 3 jours, ex. 06h45/12h45/18h45)."""
    from intelligence.services.collection_schedule_service import CollectionScheduleService

    return CollectionScheduleService.run_jiji_collection_session()


@shared_task(name='intelligence.analyser_donnees_non_traitees')
def analyser_donnees_non_traitees() -> dict:
    """Pipeline NLP planifié après les sessions de scraping (ex. 09h, 15h, 21h)."""
    from intelligence.services.collection_schedule_service import CollectionScheduleService

    return CollectionScheduleService.run_nlp_analysis_session()


@shared_task(name='intelligence.analyze_pending_social_nlp')
def analyze_pending_social_nlp(
    comment_limit: int = 100,
    post_limit: int = 50,
) -> dict:
    """
    Pipeline complet NLP — déclenchement manuel ou legacy.

    En production, préférer analyser_donnees_non_traitees (Celery Beat).
    """
    from intelligence.services.nlp_analysis_service import NlpAnalysisService

    result = NlpAnalysisService.run_full_pipeline(
        comment_limit=comment_limit,
        post_limit=post_limit,
    )
    logger.info('Pipeline NLP complet : %s', result)
    return result


@shared_task(name='intelligence.scrape_market_search_keywords')
def scrape_market_search_keywords(keyword_id: int | None = None) -> dict:
    """
    Scrape Top-Down — déclenchement manuel (sans limites session planifiée).

    Pour la routine automatique, utiliser scraper_reseaux_sociaux.
    """
    from intelligence.services.active_keyword_service import ActiveKeywordService
    from intelligence.services.search_top_down_service import SearchTopDownService

    service = SearchTopDownService()

    if keyword_id:
        keyword = ActiveKeywordService.get_active_or_none(keyword_id)
        if not keyword:
            return {'success': False, 'message': f'Mot-clé {keyword_id} introuvable ou inactif.'}
        results = [service.run_keyword(keyword)]
    else:
        results = service.run_active_keywords()

    summary = {
        'keywords': len(results),
        'success': sum(1 for item in results if item.success),
        'created': sum(item.created for item in results),
        'updated': sum(item.updated for item in results),
        'urls_harvested': sum(item.urls_harvested for item in results),
        'skipped_urls': sum(item.skipped_urls for item in results),
        'details': [
            {
                'keyword': item.keyword,
                'success': item.success,
                'urls_harvested': item.urls_harvested,
                'skipped_urls': item.skipped_urls,
                'created': item.created,
                'updated': item.updated,
                'message': item.message,
            }
            for item in results
        ],
    }
    logger.info('Scrape Top-Down terminé : %s', summary)
    return summary


@shared_task(name='intelligence.enrich_social_comments_batch')
def enrich_social_comments_batch(
    *,
    limit: int = 10,
    max_comments: int = 20,
    refresh_metrics: bool = True,
    analyze: bool = False,
) -> dict:
    """
    Enrichit commentaires + métriques sur un lot de posts TikTok sans commentaires.
    """
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    args = ['--limit', str(limit), '--max-comments', str(max_comments)]
    if refresh_metrics:
        args.append('--refresh-metrics')
    if analyze:
        args.append('--analyze')

    call_command('enrich_social_comments', *args, stdout=out)
    output = out.getvalue()
    logger.info('Enrichissement batch terminé : %s', output[-500:])
    return {'success': True, 'limit': limit, 'output_tail': output[-800:]}


@shared_task(name='intelligence.scrape_social_posts_bottom_up')
def scrape_social_posts_bottom_up(
    *,
    keyword_id: int | None = None,
    max_posts: int | None = None,
    platform: str | None = None,
) -> dict:
    """Recherche réseaux par mot-clé Paramètres (Facebook principalement)."""
    from intelligence.services.active_keyword_service import ActiveKeywordService
    from intelligence.services.social_extraction_service import SocialExtractionService

    service = SocialExtractionService()

    if keyword_id:
        keyword = ActiveKeywordService.get_active_or_none(keyword_id)
        if not keyword:
            return {'success': False, 'message': f'Mot-clé {keyword_id} introuvable ou inactif.'}
        results = [
            service.run_keyword_search(keyword, max_posts=max_posts, skip_existing=True)
        ]
    else:
        results = service.run_active_keyword_searches(platform=platform, max_posts=max_posts)

    summary = {
        'keywords': len(results),
        'success': sum(1 for item in results if item.success),
        'created': sum(item.created for item in results),
        'updated': sum(item.updated for item in results),
        'details': [
            {
                'label': item.label,
                'success': item.success,
                'extracted': item.extracted,
                'created': item.created,
                'updated': item.updated,
                'message': item.message,
            }
            for item in results
        ],
    }
    logger.info('Scrape recherche mot-clé terminé : %s', summary)
    return summary


@shared_task(name='intelligence.generate_top_purchase_recommendations')
def generate_top_purchase_recommendations(window_days: int = 7) -> dict:
    """
    Synthèse nocturne — Top 10 produits à sourcer.

    Agrège intentions NLP, vues TikTok et signaux Google Trends.
    """
    from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService

    backfill = PurchaseRecommendationService.backfill_extracted_products(limit=1000)
    result = PurchaseRecommendationService.refresh_top_recommendations(window_days=window_days)
    result['backfill'] = backfill
    logger.info('Top 10 achats recalculé : %s', result)
    return result


@shared_task(name='intelligence.generate_import_opportunities', time_limit=1800)
def generate_import_opportunities(window_days: int = 7) -> dict:
    """
    Synthèse quotidienne Import Master — opportunités Acheter / Surveiller / Éviter.

    Score par mot-clé actif : demande sociale + tendance Google +
    concurrence Jumia/Jiji + positionnement prix.
    """
    from intelligence.services.import_scoring_service import ImportScoringService

    result = ImportScoringService.refresh_opportunities(window_days=window_days)
    logger.info('Import Master recalculé : %s', result)
    return result


@shared_task(bind=True, name='intelligence.run_import_master_domain_analysis', time_limit=900, soft_time_limit=840)
def run_import_master_domain_analysis(self, analysis_id: int) -> dict:
    """Import Master — comparaison multi-domaines DeepSeek + prix sourcing."""
    from intelligence.models import ImportMasterDomainAnalysis
    from intelligence.services.collection_cancel_service import CollectionCancelService
    from intelligence.services.import_master_deepseek_service import ImportMasterDeepSeekService

    analysis = ImportMasterDomainAnalysis.objects.filter(pk=analysis_id).first()
    if not analysis:
        return {'success': False, 'error': 'Analyse introuvable'}

    # Déjà arrêtée avant démarrage worker
    if analysis.status == ImportMasterDomainAnalysis.Status.STOPPED:
        return {'success': False, 'error': 'stopped', 'analysis_id': analysis_id}

    task_id = self.request.id or ''
    CollectionCancelService.clear(task_id)
    analysis.status = ImportMasterDomainAnalysis.Status.RUNNING
    analysis.celery_task_id = task_id
    analysis.progress_message = 'Démarrage analyse…'
    analysis.save(update_fields=['status', 'celery_task_id', 'progress_message'])

    def progress(pct: int, msg: str) -> None:
        if CollectionCancelService.is_cancelled(task_id):
            raise RuntimeError('Analyse annulée par l’utilisateur.')
        self.update_state(
            state='PROGRESS',
            meta={'pourcentage': pct, 'message': msg, 'analysis_id': analysis_id},
        )

    def should_cancel() -> bool:
        return CollectionCancelService.is_cancelled(task_id)

    try:
        result = ImportMasterDeepSeekService.run_analysis(
            progress=progress,
            analysis_id=analysis_id,
            should_cancel=should_cancel,
        )
        # Si stoppé pendant l’exécution
        refreshed = ImportMasterDomainAnalysis.objects.filter(pk=analysis_id).first()
        if refreshed and refreshed.status == ImportMasterDomainAnalysis.Status.STOPPED:
            return {'success': False, 'error': 'stopped', 'analysis_id': analysis_id}
        return {
            'success': True,
            'analysis_id': analysis_id,
            'domains_count': result.get('domains_count', 0),
        }
    except Exception as exc:
        from django.utils import timezone

        msg = str(exc)
        stopped = 'annul' in msg.lower() or should_cancel()
        ImportMasterDomainAnalysis.objects.filter(pk=analysis_id).exclude(
            status=ImportMasterDomainAnalysis.Status.STOPPED,
        ).update(
            status=(
                ImportMasterDomainAnalysis.Status.STOPPED
                if stopped
                else ImportMasterDomainAnalysis.Status.FAILED
            ),
            error_message=msg[:2000],
            progress_percent=0,
            progress_message=msg[:300],
            completed_at=timezone.now(),
        )
        if not stopped:
            logger.exception('Import Master domain analysis failed')
        return {
            'success': False,
            'error': msg,
            'analysis_id': analysis_id,
            'stopped': stopped,
        }
    finally:
        CollectionCancelService.clear(task_id)


@shared_task(bind=True, name='intelligence.run_market_research_session', time_limit=18600, soft_time_limit=18000)
def run_market_research_session(self, session_id: int) -> dict:
    """Trade Intelligence — collecte bornée par durée + analyse DeepSeek."""
    from intelligence.models import MarketResearchSession
    from intelligence.services.collection_abort import reset_abort_hook, set_abort_hook
    from intelligence.services.collection_cancel_service import CollectionCancelService
    from intelligence.services.market_research_orchestrator import MarketResearchOrchestrator

    task_id = self.request.id or ''
    CollectionCancelService.clear(task_id)

    def progress(pourcentage: int, message: str, phase: str = 'collecte') -> None:
        if not task_id:
            return
        try:
            self.update_state(
                state='PROGRESS',
                meta={
                    'pourcentage': pourcentage,
                    'message': message,
                    'phase': phase,
                    'session_id': session_id,
                },
            )
        except Exception:
            pass

    def should_cancel() -> bool:
        return CollectionCancelService.is_cancelled(task_id)

    abort_token = set_abort_hook(should_cancel)
    result: dict = {'success': False, 'error': 'Session interrompue.'}

    try:
        session = MarketResearchSession.objects.filter(pk=session_id).only('duration_minutes').first()
        if session and task_id and session.celery_task_id != task_id:
            session.celery_task_id = task_id
            session.save(update_fields=['celery_task_id'])

        result = MarketResearchOrchestrator.run_session(
            session_id,
            progress=progress,
            should_cancel=should_cancel,
        )
    finally:
        reset_abort_hook(abort_token)
        CollectionCancelService.clear(task_id)

    return {
        'pourcentage': 100 if result.get('success') else 0,
        'message': result.get('error') or 'Analyse terminée.',
        'phase': 'done' if result.get('success') else 'failed',
        'session_id': session_id,
        'details': result,
    }
