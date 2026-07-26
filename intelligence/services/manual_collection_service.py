"""
Collecte manuelle — déclenchée depuis le tableau de bord avec suivi de progression.
"""

from __future__ import annotations

import logging
from typing import Callable

from intelligence.collection_config import get_collection_config, get_effective_collection_config
from intelligence.models import MarketSearchKeyword
from intelligence.scrapers.human_behavior import random_sleep
from intelligence.services.active_keyword_service import ActiveKeywordService
from intelligence.services.collection_abort import CollectionAborted
from intelligence.services.discovery_config_service import DiscoveryConfigService
from intelligence.services.search_top_down_service import SearchTopDownService
from intelligence.services.social_extraction_service import SocialExtractionService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
ShouldCancelCallback = Callable[[], bool]


class CollectionCancelled(Exception):
    """Collecte interrompue par l'utilisateur — données partielles conservées."""

    def __init__(self, partial: dict | None = None):
        self.partial = partial or {}


class ManualCollectionService:
    """Orchestre les jobs de collecte manuelle (sans contrainte de campagne planifiée)."""

    JOB_GOOGLE = 'google'
    JOB_SOCIAL = 'social'
    JOB_NLP = 'nlp'
    JOB_FULL = 'full'
    JOB_KEYWORD = 'keyword'
    JOB_JUMIA = 'jumia'
    JOB_JIJI = 'jiji'

    JOBS_AUTO_NLP = frozenset({JOB_SOCIAL, JOB_KEYWORD, JOB_GOOGLE})

    @classmethod
    def _should_chain_nlp(cls, job: str, *, test_mode: bool, auto_nlp_after: bool) -> bool:
        """
        Détermine si l'analyse hybride doit suivre la collecte.

        En mode test, Google Trends ne déclenche pas NLP (aucune publication sociale
        collectée — le bouton « Analyse NLP » sert à traiter les données déjà en base).
        """
        if not auto_nlp_after or job not in cls.JOBS_AUTO_NLP:
            return False
        if test_mode and job == cls.JOB_GOOGLE:
            return False
        return True

    @classmethod
    def run_job(
        cls,
        job: str,
        *,
        keyword_id: int | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        headless: bool | None = None,
        auto_nlp_after: bool = True,
        test_mode: bool = False,
    ) -> dict:
        """Exécute un type de collecte et retourne un résumé."""
        job = (job or cls.JOB_FULL).strip().lower()
        chain_nlp = cls._should_chain_nlp(job, test_mode=test_mode, auto_nlp_after=auto_nlp_after)

        if job == cls.JOB_NLP:
            return cls._wrap_result(
                cls.run_nlp(
                    progress=progress,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                ),
                job,
            )

        if job == cls.JOB_FULL:
            return cls._wrap_result(
                cls.run_full(
                    progress=progress,
                    headless=headless,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                ),
                job,
            )

        collect_result: dict
        cancelled = False

        try:
            if job == cls.JOB_GOOGLE:
                collect_result = cls.run_google(
                    progress=progress,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                )
            elif job == cls.JOB_SOCIAL:
                collect_result = cls.run_social(
                    progress=progress,
                    headless=headless,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                )
            elif job == cls.JOB_KEYWORD:
                collect_result = cls.run_single_keyword(
                    keyword_id,
                    progress=progress,
                    headless=headless,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                )
            elif job == cls.JOB_JUMIA:
                collect_result = cls.run_jumia(
                    progress=progress,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                )
            elif job == cls.JOB_JIJI:
                collect_result = cls.run_jiji(
                    progress=progress,
                    should_cancel=should_cancel,
                    test_mode=test_mode,
                )
            else:
                raise ValueError(f'Type de collecte inconnu : {job}')
        except CollectionCancelled as exc:
            collect_result = exc.partial
            cancelled = True
        except CollectionAborted:
            # Arrêt levé au fond d'un scraper (pause anti-bot interrompue).
            collect_result = {
                'success': False,
                'message': 'Collecte interrompue — données déjà enregistrées conservées.',
                'nouvelles_donnees': 0,
                'cancelled': True,
            }
            cancelled = True

        if chain_nlp:
            return cls._wrap_result(
                cls._finalize_with_nlp(
                    collect_result,
                    progress=progress,
                    cancelled=cancelled,
                    test_mode=test_mode,
                ),
                job,
            )

        if cancelled:
            collect_result['cancelled'] = True
            collect_result['message'] = (
                collect_result.get('message') or 'Collecte interrompue.'
            )
        return cls._wrap_result(collect_result, job)

    @classmethod
    def _finalize_with_nlp(
        cls,
        collect_result: dict,
        *,
        progress: ProgressCallback | None,
        cancelled: bool,
        test_mode: bool = False,
    ) -> dict:
        """Enchaîne l'analyse hybride après une collecte (fin normale ou arrêt)."""
        prefix = 'Collecte interrompue — ' if cancelled else 'Collecte terminée — '
        cls._report(progress, 0, f'{prefix}lancement de l’analyse hybride…', phase='nlp')

        def nlp_progress(pct: int, msg: str) -> None:
            cls._report(progress, pct, msg, phase='nlp')

        nlp = cls.run_nlp(progress=nlp_progress, finalize=True, test_mode=test_mode)
        total = collect_result.get('nouvelles_donnees', 0) + nlp.get('nouvelles_donnees', 0)
        status = 'interrompue puis analysée' if cancelled else 'terminée et analysée'
        message = (
            f'Collecte {status} — {total} élément(s) au total '
            f'({nlp.get("nouvelles_donnees", 0)} analysé(s) par NLP).'
        )
        cls._report(progress, 100, message, phase='nlp')
        return {
            'success': True,
            'cancelled': cancelled,
            'message': message,
            'nouvelles_donnees': total,
            'collecte': collect_result,
            'nlp': nlp,
        }

    @classmethod
    def _check_cancel(cls, should_cancel: ShouldCancelCallback | None) -> None:
        if should_cancel and should_cancel():
            raise CollectionCancelled()

    @classmethod
    def _check_cancel_social(
        cls,
        should_cancel: ShouldCancelCallback | None,
        *,
        created_total: int,
        keyword_summary: list,
    ) -> None:
        if should_cancel and should_cancel():
            raise CollectionCancelled(
                cls._social_partial(
                    created_total=created_total,
                    keyword_summary=keyword_summary,
                )
            )

    @classmethod
    def run_google(
        cls,
        *,
        progress: ProgressCallback | None = None,
        finalize: bool = True,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        from intelligence.controllers.domain_discovery_controller import DomainDiscoveryCancelled

        cls._check_cancel(should_cancel)
        cls._report(progress, 8, 'Google Trends — préparation de la découverte…')

        # Progression fine entre seeds / domaines (0–95 %), pour UI + can_stop.
        progress_floor = 10
        progress_ceiling = 95 if finalize else 25

        def on_progress(message: str) -> None:
            # Incrémente doucement pour montrer l'activité sans fausse précision.
            current = getattr(on_progress, '_pct', progress_floor)
            current = min(progress_ceiling - 1, current + 2)
            on_progress._pct = current  # type: ignore[attr-defined]
            cls._report(progress, current, message)

        on_progress._pct = progress_floor  # type: ignore[attr-defined]

        try:
            stats = DiscoveryConfigService.run_discovery(
                should_cancel=should_cancel,
                on_progress=on_progress,
            )
        except DomainDiscoveryCancelled as exc:
            partial = exc.partial or {}
            created = int(partial.get('created', 0))
            raise CollectionCancelled({
                'success': False,
                'message': (
                    f'Google Trends interrompu — {created} nouvelle(s) requête(s) '
                    f'déjà enregistrée(s).'
                ),
                'nouvelles_donnees': created,
                'stats': partial,
                'cancelled': True,
            }) from exc
        except RuntimeError as exc:
            return {'success': False, 'message': str(exc), 'nouvelles_donnees': 0}

        created = int(stats.get('created', 0))
        if finalize:
            cls._report(progress, 100, f'Google Trends terminé — {created} nouvelle(s) requête(s).')
        else:
            cls._report(progress, 25, f'Google Trends — {created} nouvelle(s) requête(s).')
        return {
            'success': True,
            'message': f'Découverte Google Trends terminée ({created} nouvelle(s) requête(s)).',
            'nouvelles_donnees': created,
            'stats': stats,
        }

    @classmethod
    def run_jumia(
        cls,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        """Collecte Jumia.sn (produits + avis) via les mots-clés Paramètres."""
        from intelligence.services.jumia_collection_service import JumiaCollectionService

        return JumiaCollectionService.run(
            progress=progress,
            should_cancel=should_cancel,
            test_mode=test_mode,
        )

    @classmethod
    def run_jiji(
        cls,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        """Collecte Jiji.sn (annonces locales) via les mots-clés Paramètres."""
        from intelligence.services.jiji_collection_service import JijiCollectionService

        return JijiCollectionService.run(
            progress=progress,
            should_cancel=should_cancel,
            test_mode=test_mode,
        )

    @classmethod
    def run_social(
        cls,
        *,
        progress: ProgressCallback | None = None,
        headless: bool | None = None,
        finalize: bool = True,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        config = get_effective_collection_config(test_mode=test_mode)
        top_down = SearchTopDownService()
        keyword_search = SocialExtractionService()

        max_kw = int(config.get('MAX_KEYWORDS_PER_SESSION') or 0)
        keywords = ActiveKeywordService.list_for_social(
            limit=max_kw if max_kw > 0 else 0,
        )

        if not keywords:
            msg = 'Aucun mot-clé actif (TikTok/Facebook) dans Paramètres → Recherche.'
            cls._report(progress, 100 if finalize else 72, msg)
            return {
                'success': False,
                'message': msg,
                'nouvelles_donnees': 0,
                'keywords': [],
            }

        total_steps = max(1, len(keywords))
        step = 0
        created_total = 0
        keyword_summary = []

        cls._report(
            progress,
            5,
            f'Réseaux sociaux — {len(keywords)} mot(s)-clé(s) Paramètres…',
        )

        try:
            for keyword in keywords:
                cls._check_cancel_social(
                    should_cancel,
                    created_total=created_total,
                    keyword_summary=keyword_summary,
                )
                step += 1
                pct = 5 + int((step / total_steps) * 85)
                cls._report(
                    progress,
                    pct,
                    f'« {keyword.keyword} » ({keyword.get_platform_display()}) — collecte…',
                )

                if keyword.platform == MarketSearchKeyword.Platform.TIKTOK:
                    result = top_down.run_keyword(
                        keyword,
                        headless=headless,
                        scheduled=True,
                        max_videos_session=int(config.get('MAX_VIDEOS_PER_KEYWORD_SESSION') or 15),
                    )
                    created = result.created
                    keyword_summary.append({
                        'keyword': result.keyword,
                        'platform': keyword.get_platform_display(),
                        'created': created,
                        'skipped_urls': result.skipped_urls,
                        'mode': 'top_down',
                    })
                else:
                    fb_result = keyword_search.run_keyword_search(
                        keyword,
                        headless=headless,
                        max_posts=int(config.get('MAX_POSTS_PER_TARGET_SESSION') or 12),
                        skip_existing=True,
                    )
                    created = fb_result.created
                    keyword_summary.append({
                        'keyword': keyword.keyword,
                        'platform': keyword.get_platform_display(),
                        'created': created,
                        'skipped_urls': fb_result.skipped,
                        'mode': 'keyword_search',
                    })

                created_total += created
                if step < len(keywords):
                    random_sleep(
                        config['SOCIAL_KEYWORD_DELAY_MIN'],
                        config['SOCIAL_KEYWORD_DELAY_MAX'],
                    )
        except CollectionAborted as exc:
            raise CollectionCancelled(
                cls._social_partial(
                    created_total=created_total,
                    keyword_summary=keyword_summary,
                )
            ) from exc

        cls._report(
            progress,
            100 if finalize else 72,
            f'Réseaux terminés — {created_total} nouvelle(s) publication(s).',
        )
        return {
            'success': True,
            'message': f'Collecte réseaux terminée ({created_total} nouvelle(s) publication(s)).',
            'nouvelles_donnees': created_total,
            'keywords': keyword_summary,
            'top_down': keyword_summary,
            'bottom_up': [],
        }

    @classmethod
    def _social_partial(
        cls,
        *,
        created_total: int,
        keyword_summary: list,
    ) -> dict:
        return {
            'success': True,
            'message': f'Collecte réseaux interrompue ({created_total} publication(s) enregistrée(s)).',
            'nouvelles_donnees': created_total,
            'keywords': keyword_summary,
            'top_down': keyword_summary,
            'bottom_up': [],
        }

    @classmethod
    def run_nlp(
        cls,
        *,
        progress: ProgressCallback | None = None,
        finalize: bool = True,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        cls._report(
            progress,
            15,
            'Analyse NLP — synchronisation des commentaires…',
            phase='nlp',
        )
        config = get_effective_collection_config(test_mode=test_mode)
        from intelligence.services.nlp_analysis_service import NlpAnalysisService

        cls._report(
            progress,
            45,
            'CamemBERT — intentions et catégories…',
            phase='nlp',
        )
        result = NlpAnalysisService.run_full_pipeline(
            comment_limit=int(config.get('NLP_COMMENT_LIMIT') or 150),
            post_limit=int(config.get('NLP_POST_LIMIT') or 75),
            should_cancel=should_cancel,
        )
        analyzed = cls._count_nlp_analyzed(result)
        cancelled = bool(result.get('cancelled'))
        status = 'interrompue' if cancelled else 'terminée'
        cls._report(
            progress,
            100 if finalize else 98,
            f'Analyse NLP {status} — {analyzed} élément(s) traité(s) et affichage recalculé.',
            phase='nlp',
        )
        return {
            'success': True,
            'cancelled': cancelled,
            'message': (
                f'Pipeline NLP {status} — les résultats partiels sont disponibles.'
                if cancelled
                else 'Pipeline NLP terminé.'
            ),
            'nouvelles_donnees': analyzed,
            'nlp': result,
        }

    @classmethod
    def run_single_keyword(
        cls,
        keyword_id: int | None,
        *,
        progress: ProgressCallback | None = None,
        headless: bool | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        if not keyword_id:
            raise ValueError('Sélectionnez un mot-clé actif.')

        keyword = ActiveKeywordService.get_active_or_none(keyword_id)
        if not keyword:
            raise ValueError('Mot-clé introuvable ou inactif.')

        cls._check_cancel(should_cancel)
        config = get_effective_collection_config(test_mode=test_mode)
        cls._report(progress, 10, f'Initialisation — « {keyword.keyword} »…')

        if keyword.platform == MarketSearchKeyword.Platform.TIKTOK:
            cls._report(progress, 35, 'Récupération des URLs vidéo TikTok…')
            result = SearchTopDownService().run_keyword(
                keyword,
                headless=headless,
                scheduled=True,
                max_videos_session=int(config.get('MAX_VIDEOS_PER_KEYWORD_SESSION') or 15),
            )
            cls._report(progress, 85, 'Enregistrement en base…')
            cls._report(
                progress,
                100,
                f'Terminé — {result.created} nouvelle(s) publication(s) pour « {keyword.keyword} ».',
            )
            return {
                'success': result.success,
                'message': result.message,
                'nouvelles_donnees': result.created,
                'keyword': result.keyword,
                'urls_harvested': result.urls_harvested,
                'skipped_urls': result.skipped_urls,
            }

        cls._report(progress, 35, f'Recherche Facebook — « {keyword.keyword} »…')
        fb_result = SocialExtractionService().run_keyword_search(
            keyword,
            headless=headless,
            max_posts=int(config.get('MAX_POSTS_PER_TARGET_SESSION') or 12),
            skip_existing=True,
        )
        cls._report(progress, 100, f'Terminé — {fb_result.created} nouvelle(s) publication(s).')
        return {
            'success': fb_result.success,
            'message': fb_result.message,
            'nouvelles_donnees': fb_result.created,
            'keyword': keyword.keyword,
        }

    @classmethod
    def run_full(
        cls,
        *,
        progress: ProgressCallback | None = None,
        headless: bool | None = None,
        should_cancel: ShouldCancelCallback | None = None,
        test_mode: bool = False,
    ) -> dict:
        cls._report(progress, 3, 'Pipeline complet — démarrage…')
        cancelled = False
        google: dict = {'nouvelles_donnees': 0}
        social: dict = {'nouvelles_donnees': 0}

        try:
            google = cls.run_google(
                progress=progress,
                finalize=False,
                should_cancel=should_cancel,
                test_mode=test_mode,
            )
            cls._report(progress, 28, 'Étape 1/3 terminée — passage aux réseaux sociaux…')

            def social_progress(pct: int, msg: str) -> None:
                mapped = 30 + int(pct * 0.42)
                cls._report(progress, mapped, msg)

            social = cls.run_social(
                progress=social_progress,
                headless=headless,
                finalize=False,
                should_cancel=should_cancel,
                test_mode=test_mode,
            )
            cls._report(progress, 78, 'Étape 2/3 terminée — analyse NLP…', phase='nlp')
        except CollectionCancelled as exc:
            cancelled = True
            partial = exc.partial or {}
            if partial.get('top_down') is not None or partial.get('bottom_up') is not None:
                social = partial
            cls._report(progress, 72, 'Collecte interrompue — analyse hybride des données…', phase='nlp')
        except CollectionAborted:
            cancelled = True
            cls._report(progress, 72, 'Collecte interrompue — analyse hybride des données…', phase='nlp')

        def nlp_progress(pct: int, msg: str) -> None:
            mapped = 80 + int(pct * 0.18)
            cls._report(progress, mapped, msg, phase='nlp')

        nlp = cls.run_nlp(progress=nlp_progress, finalize=False, test_mode=test_mode)

        total_new = (
            google.get('nouvelles_donnees', 0)
            + social.get('nouvelles_donnees', 0)
            + nlp.get('nouvelles_donnees', 0)
        )
        suffix = ' (collecte partielle)' if cancelled else ''
        cls._report(
            progress,
            100,
            f'Pipeline complet terminé{suffix} — {total_new} élément(s) traité(s).',
            phase='nlp',
        )
        return {
            'success': True,
            'cancelled': cancelled,
            'message': f'Pipeline complet terminé{suffix}.',
            'nouvelles_donnees': total_new,
            'google': google,
            'social': social,
            'nlp': nlp,
        }

    @classmethod
    def get_page_context(cls, *, for_test_page: bool = False) -> dict:
        from intelligence.services.collection_test_context_service import CollectionTestContextService

        keywords = ActiveKeywordService.queryset_active()
        jobs = cls._build_job_cards(for_test_page=for_test_page)
        ctx = {
            'keywords': keywords,
            'keywords_count': keywords.count(),
            'social_keywords': ActiveKeywordService.queryset_active().filter(
                platform__in=(
                    MarketSearchKeyword.Platform.TIKTOK,
                    MarketSearchKeyword.Platform.FACEBOOK,
                ),
            ),
            'social_keywords_count': ActiveKeywordService.count_social(),
            'jobs': jobs,
        }
        if for_test_page:
            ctx['test_context'] = CollectionTestContextService.build()
        return ctx

    @classmethod
    def _build_job_cards(cls, *, for_test_page: bool) -> list[dict]:
        """Libellés UI — différencie session test et collecte production."""
        if for_test_page:
            return [
                {
                    'id': cls.JOB_FULL,
                    'label': 'Pipeline complet',
                    'desc': 'Google Trends → réseaux → NLP → Top 10 (flux test intégral)',
                    'tone': 'orange',
                    'auto_nlp': True,
                },
                {
                    'id': cls.JOB_GOOGLE,
                    'label': 'Google Trends',
                    'desc': 'Découverte requêtes uniquement — pas de NLP automatique',
                    'tone': 'bleu',
                    'auto_nlp': False,
                },
                {
                    'id': cls.JOB_SOCIAL,
                    'label': 'Réseaux sociaux',
                    'desc': 'Uniquement mots-clés actifs Paramètres (TikTok Top-Down, Facebook recherche)',
                    'tone': 'jaune',
                    'auto_nlp': True,
                },
                {
                    'id': cls.JOB_NLP,
                    'label': 'Analyse NLP',
                    'desc': 'Relancer NLP sur les données test déjà en base (sans collecte)',
                    'tone': 'noir',
                    'auto_nlp': False,
                },
                {
                    'id': cls.JOB_JUMIA,
                    'label': 'Jumia marché',
                    'desc': 'Prix, notes ★ et avis (volume = max_videos / max_comments Paramètres)',
                    'tone': 'bleu',
                    'auto_nlp': False,
                },
                {
                    'id': cls.JOB_JIJI,
                    'label': 'Jiji marché local',
                    'desc': 'Annonces locales neuf/occasion (volume = max_videos Paramètres)',
                    'tone': 'jaune',
                    'auto_nlp': False,
                },
                {
                    'id': cls.JOB_KEYWORD,
                    'label': 'Un mot-clé réseau',
                    'desc': 'Top-Down TikTok ou recherche Facebook selon la plateforme Paramètres',
                    'tone': 'orange',
                    'auto_nlp': True,
                },
            ]
        return [
            {
                'id': cls.JOB_FULL,
                'label': 'Pipeline complet',
                'desc': 'Google Trends → réseaux sociaux → analyse NLP',
                'tone': 'orange',
                'auto_nlp': True,
            },
            {
                'id': cls.JOB_GOOGLE,
                'label': 'Google Trends',
                'desc': 'Découverte des requêtes puis analyse hybride automatique',
                'tone': 'bleu',
                'auto_nlp': True,
            },
            {
                'id': cls.JOB_SOCIAL,
                'label': 'Réseaux sociaux',
                'desc': 'Mots-clés actifs Paramètres uniquement — TikTok & Facebook',
                'tone': 'jaune',
                'auto_nlp': True,
            },
            {
                'id': cls.JOB_NLP,
                'label': 'Analyse NLP',
                'desc': 'Traiter les publications en attente (CamemBERT local)',
                'tone': 'noir',
                'auto_nlp': False,
            },
            {
                'id': cls.JOB_JUMIA,
                'label': 'Jumia marché',
                'desc': 'Prix/stock/avis Jumia — nb produits = max_videos Paramètres',
                'tone': 'bleu',
                'auto_nlp': False,
            },
            {
                'id': cls.JOB_JIJI,
                'label': 'Jiji marché local',
                'desc': 'Annonces Jiji — nb annonces = max_videos Paramètres',
                'tone': 'jaune',
                'auto_nlp': False,
            },
            {
                'id': cls.JOB_KEYWORD,
                'label': 'Un mot-clé réseau',
                'desc': 'Top-Down TikTok ou recherche Facebook selon la plateforme Paramètres',
                'tone': 'orange',
                'auto_nlp': True,
            },
        ]

    @staticmethod
    def _count_nlp_analyzed(pipeline_result: dict) -> int:
        """Compte les commentaires + publications traités par le pipeline NLP."""
        comments = pipeline_result.get('comments') or {}
        posts = pipeline_result.get('posts') or {}
        return int(comments.get('total') or 0) + int(posts.get('updated') or 0)

    @staticmethod
    def _report(
        progress: ProgressCallback | None,
        pct: int,
        message: str,
        phase: str = 'collecte',
    ) -> None:
        if progress:
            try:
                progress(max(0, min(100, pct)), message, phase)
            except TypeError:
                progress(max(0, min(100, pct)), message)
        logger.info('[collecte manuelle %s%%][%s] %s', pct, phase, message)

    @staticmethod
    def _wrap_result(result: dict, job: str) -> dict:
        result['job'] = job
        if 'message' not in result:
            result['message'] = 'Terminé.'
        if 'nouvelles_donnees' not in result:
            result['nouvelles_donnees'] = 0
        return result
