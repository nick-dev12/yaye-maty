"""
Orchestration session Trade Intelligence — collecte parallèle bornée
sur la durée choisie, puis analyse Top 15 DeepSeek.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Callable

from django.db import close_old_connections
from django.utils import timezone
from django.utils.text import slugify

from intelligence.models import MarketResearchSession
from intelligence.services.deepseek_analysis_service import DeepSeekAnalysisService
from intelligence.services.trade_domain_catalog import DEFAULT_SOURCES, TradeDomainCatalog
from intelligence.services.trade_research_archive_service import TradeResearchArchiveService
from intelligence.services.trade_research_collection_service import TradeResearchCollectionService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str, str], None]
ShouldCancelCallback = Callable[[], bool]

# Pause entre passages d'une même lane (évite busy-loop / rate-limit)
LANE_PAUSE_SECONDS = 2.0
# Pause après quota Google Trends (429)
TRENDS_RATE_LIMIT_PAUSE_SECONDS = 45.0
TRENDS_RATE_LIMIT_MAX_STRIKES = 3
# Pause après échec marketplace (évite boucle rapide)
MARKETPLACE_FAIL_PAUSE_SECONDS = 5.0
# Alias rétrocompat tests / imports
ROUND_PAUSE_SECONDS = LANE_PAUSE_SECONDS
WEB_CONTEXT_MAX_CHARS = 14000

# Angles de recherche DeepSeek web (rotation)
WEB_FOCUS_HINTS = (
    'meilleurs modèles demandés et tendances',
    'prix Jumia.sn et Jiji.sn, stock et rotation',
    'avis clients, plaintes et points forts',
    'opportunité d’investissement et marge revendeur',
    'nouveautés et modèles en forte croissance TikTok SN',
)

_DB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ti-session-db')


class MarketResearchOrchestrator:
    """Exécute une session domaine : lanes parallèles sur toute la durée."""

    @classmethod
    def _persist_fields(cls, session_id: int, **fields) -> None:
        """
        Sauvegarde session. En contexte async (Playwright), bascule sur un thread
        pour éviter SynchronousOnlyOperation.
        """
        def _write(*, close_conn: bool = False) -> None:
            if close_conn:
                close_old_connections()
            try:
                obj = MarketResearchSession.objects.get(pk=session_id)
                for key, value in fields.items():
                    setattr(obj, key, value)
                obj.save(update_fields=list(fields.keys()))
            finally:
                if close_conn:
                    close_old_connections()

        try:
            _write(close_conn=False)
        except Exception as exc:
            msg = str(exc).lower()
            if (
                type(exc).__name__ == 'SynchronousOnlyOperation'
                or 'async context' in msg
                or 'synchronousonlyoperation' in msg
            ):
                _DB_EXECUTOR.submit(_write, close_conn=True).result(timeout=30)
            else:
                raise

    @classmethod
    def _build_lanes(cls, sources: list[str]) -> list[str]:
        """
        Lanes parallèles bornées :
        - trends (léger)
        - marketplaces (Jumia puis Jiji en alternance — 1 Playwright à la fois)
        - tiktok
        - deepseek_web
        """
        lanes: list[str] = []
        if 'google' in sources:
            lanes.append('trends')
        if 'jumia' in sources or 'jiji' in sources:
            lanes.append('marketplaces')
        if 'tiktok' in sources:
            lanes.append('tiktok')
        lanes.append('deepseek_web')
        if not any(l != 'deepseek_web' for l in lanes):
            lanes.insert(0, 'trends')
        return lanes

    @classmethod
    def run_session(
        cls,
        session_id: int,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        session = MarketResearchSession.objects.get(pk=session_id)
        query = session.search_query
        domain_label = session.domain_label
        sources = TradeDomainCatalog.normalize_sources(session.sources or list(DEFAULT_SOURCES))
        duration_seconds = max(60, int(session.duration_minutes or 20) * 60)
        started_mono = time.monotonic()
        deadline = started_mono + duration_seconds

        state_lock = threading.Lock()
        collect_results: dict = {}
        web_chunks: list[str] = []
        lane_status: dict[str, str] = {}
        lane_rounds: dict[str, int] = {}
        marketplace_turn = {'n': 0}
        trends_rate_strikes = {'n': 0}

        def timed_out() -> bool:
            return time.monotonic() >= deadline

        def user_stopped() -> bool:
            return bool(should_cancel and should_cancel())

        def cancelled() -> bool:
            """Arrêt manuel OU fin de durée → chaque lane s’arrête."""
            return user_stopped() or timed_out() or remaining_seconds() <= 0

        def remaining_seconds() -> int:
            return max(0, int(deadline - time.monotonic()))

        def collect_progress_pct() -> int:
            """0–82 % pendant la fenêtre de durée (analyse finale ensuite)."""
            elapsed = time.monotonic() - started_mono
            ratio = min(1.0, max(0.0, elapsed / duration_seconds))
            return int(5 + ratio * 77)

        def report(
            pct: int,
            msg: str,
            phase: str = 'collecte',
            *,
            notify_celery: bool = True,
        ) -> None:
            rem = remaining_seconds()
            mins, secs = divmod(rem, 60)
            suffix = f' · reste {mins}m{secs:02d}s' if phase == 'collecte' else ''
            full = (msg + suffix)[:300]
            session.progress_percent = pct
            session.progress_message = full
            cls._persist_fields(
                session_id,
                progress_percent=pct,
                progress_message=full,
            )
            if progress and notify_celery:
                try:
                    progress(pct, full, phase)
                except Exception as exc:
                    logger.debug('Progress Celery ignoré : %s', exc)

        def source_progress(_pct: int, message: str, *_extra) -> None:
            """Compatible progress(pct, msg) — sans update_state Celery (thread lane)."""
            with state_lock:
                lane_status['marketplaces'] = message[:120]
            report(
                min(82, collect_progress_pct()),
                message,
                'collecte',
                notify_celery=False,
            )

        def _pause_lane(*, minimum: float = 0.0) -> None:
            if cancelled():
                return
            rem = remaining_seconds()
            if rem <= 0:
                return
            pause = max(minimum, min(LANE_PAUSE_SECONDS, max(0.3, rem - 0.2)))
            end_pause = time.monotonic() + pause
            while time.monotonic() < end_pause:
                if cancelled():
                    return
                time.sleep(min(0.35, max(0.05, end_pause - time.monotonic())))

        def _store_result(key: str, value: dict) -> None:
            with state_lock:
                collect_results[key] = value

        def _run_trends_lane() -> None:
            close_old_connections()
            try:
                while not cancelled():
                    with state_lock:
                        lane_rounds['trends'] = lane_rounds.get('trends', 0) + 1
                        n = lane_rounds['trends']
                        lane_status['trends'] = f'Trends tour {n}'
                    try:
                        result = TradeResearchCollectionService.collect_trends(
                            query, should_cancel=cancelled,
                        )
                        _store_result('trends', result)
                        if result.get('success'):
                            trends_rate_strikes['n'] = 0
                        if not result.get('success'):
                            msg = str(result.get('message', ''))
                            if result.get('rate_limited') or '429' in msg:
                                trends_rate_strikes['n'] += 1
                                strikes = trends_rate_strikes['n']
                                if strikes >= TRENDS_RATE_LIMIT_MAX_STRIKES:
                                    with state_lock:
                                        lane_status['trends'] = 'Trends quota — collecte suspendue'
                                    while not cancelled():
                                        time.sleep(min(5.0, max(0.5, remaining_seconds())))
                                    continue
                                with state_lock:
                                    lane_status['trends'] = f'Trends quota — pause ({strikes}/{TRENDS_RATE_LIMIT_MAX_STRIKES})'
                                pause = min(
                                    TRENDS_RATE_LIMIT_PAUSE_SECONDS,
                                    max(5.0, remaining_seconds() - 1),
                                )
                                end_pause = time.monotonic() + pause
                                while time.monotonic() < end_pause and not cancelled():
                                    time.sleep(min(1.0, end_pause - time.monotonic()))
                                continue
                    except Exception as exc:
                        logger.warning('Lane trends tour échoué : %s', exc)
                        with state_lock:
                            lane_status['trends'] = f'Trends erreur: {exc}'[:120]
                    if cancelled():
                        break
                    _pause_lane()
            finally:
                close_old_connections()

        def _run_marketplaces_lane() -> None:
            """Jumia et Jiji en alternance pour limiter les navigateurs Playwright."""
            close_old_connections()
            do_jumia = 'jumia' in sources
            do_jiji = 'jiji' in sources
            try:
                while not cancelled():
                    with state_lock:
                        lane_rounds['marketplaces'] = lane_rounds.get('marketplaces', 0) + 1
                        n = lane_rounds['marketplaces']
                        turn = marketplace_turn['n']
                        marketplace_turn['n'] = turn + 1

                    if do_jumia and do_jiji:
                        use_jumia = (turn % 2 == 0)
                    else:
                        use_jumia = do_jumia

                    try:
                        if use_jumia:
                            with state_lock:
                                lane_status['marketplaces'] = f'Jumia tour {n}'
                            result = TradeResearchCollectionService.collect_jumia(
                                query,
                                product_category='',
                                progress=source_progress,
                                should_cancel=cancelled,
                            )
                            _store_result('jumia', result)
                        else:
                            with state_lock:
                                lane_status['marketplaces'] = f'Jiji tour {n}'
                            result = TradeResearchCollectionService.collect_jiji(
                                query,
                                product_category='',
                                progress=source_progress,
                                should_cancel=cancelled,
                            )
                            _store_result('jiji', result)
                    except Exception as exc:
                        logger.warning('Lane marketplaces tour échoué : %s', exc)
                        with state_lock:
                            lane_status['marketplaces'] = f'Marketplace erreur: {exc}'[:120]
                        if not cancelled() and remaining_seconds() > 0:
                            fail_pause = min(
                                MARKETPLACE_FAIL_PAUSE_SECONDS,
                                max(1.0, remaining_seconds() - 0.5),
                            )
                            end_fail = time.monotonic() + fail_pause
                            while time.monotonic() < end_fail and not cancelled():
                                time.sleep(min(0.5, end_fail - time.monotonic()))
                    if cancelled():
                        break
                    _pause_lane()
            finally:
                close_old_connections()

        def _run_tiktok_lane() -> None:
            close_old_connections()
            try:
                while not cancelled():
                    with state_lock:
                        lane_rounds['tiktok'] = lane_rounds.get('tiktok', 0) + 1
                        n = lane_rounds['tiktok']
                        lane_status['tiktok'] = f'TikTok tour {n}'
                    try:
                        result = TradeResearchCollectionService.collect_tiktok(
                            query,
                            should_cancel=cancelled,
                        )
                        _store_result('social', result)
                    except Exception as exc:
                        logger.warning('Lane TikTok tour échoué : %s', exc)
                        with state_lock:
                            lane_status['tiktok'] = f'TikTok erreur: {exc}'[:120]
                    if cancelled():
                        break
                    _pause_lane()
            finally:
                close_old_connections()

        def _run_deepseek_web_lane() -> None:
            close_old_connections()
            try:
                focus_idx = 0
                while not cancelled():
                    with state_lock:
                        lane_rounds['deepseek_web'] = lane_rounds.get('deepseek_web', 0) + 1
                        n = lane_rounds['deepseek_web']

                    if not DeepSeekAnalysisService.is_enabled():
                        with state_lock:
                            lane_status['deepseek_web'] = (
                                DeepSeekAnalysisService.format_web_watch_status(
                                    n, enabled=False,
                                )
                            )
                        _pause_lane()
                        continue

                    focus = WEB_FOCUS_HINTS[focus_idx % len(WEB_FOCUS_HINTS)]
                    focus_idx += 1
                    with state_lock:
                        lane_status['deepseek_web'] = (
                            DeepSeekAnalysisService.format_web_watch_status(
                                n, focus=focus,
                            )
                        )
                    try:
                        chunk = DeepSeekAnalysisService.fetch_web_context(
                            query,
                            domain_label=domain_label,
                            focus_hint=focus,
                        )
                        if chunk:
                            with state_lock:
                                web_chunks.append(
                                    f'--- Recherche {len(web_chunks) + 1} '
                                    f'({focus} · '
                                    f'{DeepSeekAnalysisService.web_watch_meta().get("max_uses", 0)}'
                                    f' recherches) ---\n{chunk}'
                                )
                                joined = cls._join_web_chunks(list(web_chunks))
                            cls._persist_fields(session_id, deepseek_web_context=joined)
                            with state_lock:
                                lane_status['deepseek_web'] = (
                                    DeepSeekAnalysisService.format_web_watch_status(
                                        n, focus=f'OK {focus}',
                                    )
                                )
                    except Exception as exc:
                        logger.warning('Lane DeepSeek web tour échoué : %s', exc)
                        with state_lock:
                            lane_status['deepseek_web'] = (
                                DeepSeekAnalysisService.format_web_watch_status(
                                    n, error=str(exc),
                                )
                            )
                    if cancelled():
                        break
                    _pause_lane()
            finally:
                close_old_connections()

        lane_runners = {
            'trends': _run_trends_lane,
            'marketplaces': _run_marketplaces_lane,
            'tiktok': _run_tiktok_lane,
            'deepseek_web': _run_deepseek_web_lane,
        }

        now = timezone.now()
        cls._persist_fields(
            session_id,
            status=MarketResearchSession.Status.COLLECTING,
            started_at=now,
        )
        session.status = MarketResearchSession.Status.COLLECTING
        session.started_at = now

        lanes = cls._build_lanes(sources)
        stop_reason = ''

        try:
            report(
                5,
                f'Collecte parallèle ({len(lanes)} voies) — chaque source sur toute la durée…',
                'collecte',
            )

            with ThreadPoolExecutor(
                max_workers=max(1, len(lanes)),
                thread_name_prefix=f'ti-lane-{session_id}',
            ) as pool:
                futures = [pool.submit(lane_runners[lane]) for lane in lanes]

                while not cancelled():
                    with state_lock:
                        parts = [
                            lane_status.get(lane, lane)
                            for lane in lanes
                        ]
                    # progress_message max 300 — garder place pour « · reste XmYYs »
                    snapshot = ' · '.join(parts)[:220]
                    report(
                        collect_progress_pct(),
                        f'Parallèle — {snapshot}' if snapshot else 'Collecte parallèle…',
                        'collecte',
                    )
                    # Toutes les lanes terminées prématurément ?
                    if all(f.done() for f in futures):
                        break
                    time.sleep(0.8)

                # Laisser les lanes voir cancelled() et sortir proprement
                wait(futures, timeout=max(5.0, remaining_seconds() + 15.0))

            if user_stopped():
                stop_reason = 'stop'
            else:
                stop_reason = 'timeout'

            with state_lock:
                results_snapshot = dict(collect_results)
                web_snapshot = list(web_chunks)
                rounds_snapshot = dict(lane_rounds)

            session = MarketResearchSession.objects.get(pk=session_id)
            result = cls._finalize_analysis(
                session,
                collect_results=results_snapshot,
                query=query,
                report=report,
                stop_reason=stop_reason,
                web_context_prefetched=cls._join_web_chunks(web_snapshot),
            )
            if isinstance(result.get('analysis'), dict):
                result['analysis']['lane_rounds'] = rounds_snapshot
            return result

        except Exception as exc:
            logger.exception('Session Trade Intelligence %s échouée', session_id)
            with state_lock:
                results_snapshot = dict(collect_results)
                web_snapshot = list(web_chunks)
            if results_snapshot or web_snapshot:
                try:
                    session = MarketResearchSession.objects.get(pk=session_id)
                    return cls._finalize_analysis(
                        session,
                        collect_results=results_snapshot,
                        query=query,
                        report=report,
                        stop_reason='error',
                        error_note=str(exc),
                        web_context_prefetched=cls._join_web_chunks(web_snapshot),
                    )
                except Exception:
                    logger.exception('Analyse partielle impossible')
            cls._persist_fields(
                session_id,
                status=MarketResearchSession.Status.FAILED,
                error_message=str(exc)[:2000],
                completed_at=timezone.now(),
            )
            TradeResearchArchiveService.prune_to_limit()
            report(0, str(exc)[:300], 'failed')
            return {'success': False, 'session_id': session_id, 'error': str(exc)}

    @staticmethod
    def _join_web_chunks(chunks: list[str]) -> str:
        if not chunks:
            return ''
        text = '\n\n'.join(chunks)
        if len(text) <= WEB_CONTEXT_MAX_CHARS:
            return text
        return text[-WEB_CONTEXT_MAX_CHARS:]

    @classmethod
    def _finalize_analysis(
        cls,
        session: MarketResearchSession,
        *,
        collect_results: dict,
        query: str,
        report: ProgressCallback,
        stop_reason: str = '',
        error_note: str = '',
        web_context_prefetched: str = '',
    ) -> dict:
        session_id = session.pk
        if stop_reason in ('stop', 'timeout', 'error'):
            cls._persist_fields(session_id, status=MarketResearchSession.Status.STOPPED)
            session.status = MarketResearchSession.Status.STOPPED
            labels = {
                'stop': 'arrêt manuel',
                'timeout': 'durée écoulée',
                'error': 'erreur collecte',
            }
            report(
                84,
                f'Collecte terminée ({labels.get(stop_reason, stop_reason)}) — analyse Top 15…',
                'analyse',
            )
        else:
            report(84, 'Agrégation des données — analyse Top 15…', 'analyse')

        payload = TradeResearchCollectionService.aggregate_payload(
            query, collect_results=collect_results,
        )
        cls._persist_fields(
            session_id,
            collect_payload=payload,
            status=MarketResearchSession.Status.ANALYZING,
        )
        session.collect_payload = payload
        session.status = MarketResearchSession.Status.ANALYZING

        web_context = (web_context_prefetched or session.deepseek_web_context or '').strip()
        if DeepSeekAnalysisService.is_enabled() and len(web_context) < 800:
            report(86, 'Complément recherche web…', 'analyse')
            extra = DeepSeekAnalysisService.fetch_web_context(
                query,
                domain_label=session.domain_label,
                focus_hint='synthèse finale modèles à investir',
            )
            if extra:
                web_context = cls._join_web_chunks(
                    [c for c in (web_context, extra) if c]
                )

        cls._persist_fields(session_id, deepseek_web_context=web_context)
        session.deepseek_web_context = web_context

        report(90, 'Analyse IA — tri et Top 15…', 'analyse')
        keyword_label = (session.keyword or '').strip() or session.domain_label
        if DeepSeekAnalysisService.is_enabled():
            try:
                analysis = DeepSeekAnalysisService.analyze_market(
                    payload,
                    web_context,
                    domain_label=session.domain_label,
                    category_label=keyword_label,
                    search_query=query,
                )
            except Exception as exc:
                logger.exception('DeepSeek analyse échouée : %s', exc)
                analysis = DeepSeekAnalysisService.fallback_result(
                    payload,
                    domain_label=session.domain_label,
                    category_label=keyword_label,
                    error=str(exc),
                )
        else:
            analysis = DeepSeekAnalysisService.fallback_result(
                payload,
                domain_label=session.domain_label,
                category_label=keyword_label,
                error=error_note or 'Analyse IA indisponible (configuration manquante).',
            )

        analysis = DeepSeekAnalysisService.ensure_top10(
            analysis,
            payload=payload,
            domain_label=session.domain_label,
            category_label=keyword_label,
        )

        if stop_reason:
            analysis['stop_reason'] = stop_reason
        research_rounds = (
            max(0, len(web_context.split('--- Recherche')) - 1) if web_context else 0
        )
        analysis['research_rounds'] = research_rounds
        web_meta = DeepSeekAnalysisService.web_watch_meta()
        analysis['web_watch'] = {
            **web_meta,
            'research_rounds': research_rounds,
            'context_chars': len(web_context or ''),
        }

        done_msg = (
            f'Analyse terminée — {research_rounds} tour(s) veille web '
            f'× {web_meta.get("max_uses") or "?"} recherches'
            + (f' (collecte {stop_reason}).' if stop_reason else '.')
        )
        if len(done_msg) > 280:
            done_msg = done_msg[:280]
        cls._persist_fields(
            session_id,
            analysis_result=analysis,
            status=MarketResearchSession.Status.DONE,
            completed_at=timezone.now(),
            progress_percent=100,
            progress_message=done_msg,
            error_message='',
        )
        TradeResearchArchiveService.prune_to_limit()

        report(100, done_msg, 'done')
        return {
            'success': True,
            'session_id': session_id,
            'analysis': analysis,
            'stop_reason': stop_reason,
        }

    @classmethod
    def create_session(
        cls,
        domain_slug: str,
        keyword: str,
        *,
        duration_minutes: int = 20,
        sources: list[str] | None = None,
    ) -> MarketResearchSession:
        domain = TradeDomainCatalog.get_domain(domain_slug)
        if not domain:
            raise ValueError('Domaine invalide ou inactif. Configurez-le dans Domaines.')
        kw = (keyword or '').strip()
        duration = TradeDomainCatalog.normalize_duration(duration_minutes)
        src = TradeDomainCatalog.normalize_sources(sources)
        query = TradeDomainCatalog.build_search_query(domain.label, kw)
        kw_slug = slugify(kw)[:80] if kw else 'domaine'
        session = MarketResearchSession.objects.create(
            domain=domain,
            domain_slug=domain.slug,
            domain_label=domain.label,
            category_slug=kw_slug,
            category_label=(kw[:120] if kw else domain.label[:120]),
            keyword=kw[:200],
            search_query=query,
            duration_minutes=duration,
            sources=src,
            status=MarketResearchSession.Status.PENDING,
        )
        TradeResearchArchiveService.prune_to_limit()
        return session
