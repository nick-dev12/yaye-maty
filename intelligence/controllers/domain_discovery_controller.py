"""
Contrôleur de découverte Bottom-Up par domaine Google Trends.

Interroge les catégories Google via related_queries() et suggestions()
pour révéler les recherches populaires au Sénégal.
"""

import logging
import random
import time
from typing import Callable, Sequence

import pandas as pd
from django.db import transaction
from pytrends import exceptions as pytrends_exceptions
from pytrends.request import TrendReq

from intelligence.collection_config import get_collection_config
from intelligence.constants import DEFAULT_REGION, DEFAULT_TIMEFRAME
from intelligence.models import MarketDomain
from intelligence.services.collection_model_router import CollectionModelRouter

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10
SEED_DELAY_SECONDS = 8
CANCEL_POLL_SECONDS = 0.4

ShouldCancelCallback = Callable[[], bool]
ProgressHook = Callable[[str], None]


class DomainDiscoveryCancelled(Exception):
    """Arrêt coopératif demandé pendant une découverte Google Trends."""

    def __init__(self, partial: dict | None = None):
        self.partial = partial or {}
        super().__init__('Découverte Google Trends annulée')


class DomainDiscoveryController:
    """Découvre les requêtes recherchées dans un domaine via Google Trends."""

    def __init__(
        self,
        hl: str = 'fr-FR',
        tz: int = 0,
        *,
        should_cancel: ShouldCancelCallback | None = None,
        on_progress: ProgressHook | None = None,
    ):
        self._pytrends = TrendReq(hl=hl, tz=tz)
        self._should_cancel = should_cancel
        self._on_progress = on_progress

    def _check_cancel(self, partial: dict | None = None) -> None:
        if self._should_cancel and self._should_cancel():
            raise DomainDiscoveryCancelled(partial)

    def _report(self, message: str) -> None:
        if self._on_progress:
            self._on_progress(message)

    def discover_domain(
        self,
        domain_slug: str,
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        region: str = DEFAULT_REGION,
    ) -> dict[str, int]:
        """Explore un domaine enregistré en base et persiste les résultats."""
        self._check_cancel()
        try:
            market_domain = MarketDomain.objects.get(slug=domain_slug, is_active=True)
        except MarketDomain.DoesNotExist as exc:
            raise ValueError(f'Domaine inconnu ou inactif : {domain_slug}') from exc

        cat_id = market_domain.cat_id
        seeds = market_domain.get_seed_list()

        if not seeds:
            raise ValueError(
                f'Le domaine {market_domain.label} n\'a aucun mot-clé de départ.'
            )

        logger.info(
            'Découverte domaine %s (cat %s) — %s seed(s), région %s, période %s',
            domain_slug,
            cat_id,
            len(seeds),
            region,
            timeframe,
        )

        stats = {
            'created': 0,
            'updated': 0,
            'total': 0,
            'top': 0,
            'rising': 0,
            'suggestions': 0,
            'seeds_processed': 0,
        }

        for i, seed in enumerate(seeds):
            self._check_cancel(stats)
            self._report(
                f'Google Trends — {market_domain.label} · seed « {seed} » '
                f'({i + 1}/{len(seeds)})…'
            )
            seed_stats = self._discover_from_seed(
                domain_slug,
                seed,
                cat_id=cat_id,
                timeframe=timeframe,
                region=region,
                partial=stats,
            )

            stats['seeds_processed'] += 1
            stats['created'] += seed_stats['created']
            stats['updated'] += seed_stats['updated']
            stats['total'] += seed_stats['total']
            stats['top'] += seed_stats['top']
            stats['rising'] += seed_stats['rising']
            stats['suggestions'] += seed_stats['suggestions']

            if i < len(seeds) - 1:
                self._sleep_between_seeds(partial=stats)

        if stats['total'] == 0:
            raise RuntimeError(
                f'Aucune requête découverte pour le domaine {market_domain.label}. '
                f'Google Trends renvoie peu de données pour la région {region} — '
                f'réessayez dans quelques minutes ou élargissez la période.'
            )

        return stats

    def discover_domains(
        self,
        domain_slugs: Sequence[str],
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        region: str = DEFAULT_REGION,
    ) -> dict[str, int | dict]:
        """Explore plusieurs domaines avec pause entre chaque requête."""
        totals = {
            'domains': 0,
            'created': 0,
            'updated': 0,
            'total': 0,
            'details': {},
        }

        for i, domain_slug in enumerate(domain_slugs):
            self._check_cancel(totals)
            self._report(
                f'Google Trends — domaine {i + 1}/{len(domain_slugs)} : {domain_slug}…'
            )
            try:
                stats = self.discover_domain(
                    domain_slug,
                    timeframe=timeframe,
                    region=region,
                )
            except DomainDiscoveryCancelled as exc:
                # Fusionne les stats du domaine partiel dans le total global.
                partial_domain = exc.partial or {}
                if partial_domain.get('total') or partial_domain.get('created'):
                    totals['domains'] += 1
                    totals['created'] += int(partial_domain.get('created', 0))
                    totals['updated'] += int(partial_domain.get('updated', 0))
                    totals['total'] += int(partial_domain.get('total', 0))
                    totals['details'][domain_slug] = partial_domain
                raise DomainDiscoveryCancelled(totals) from exc

            totals['domains'] += 1
            totals['created'] += stats['created']
            totals['updated'] += stats['updated']
            totals['total'] += stats['total']
            totals['details'][domain_slug] = stats

            if i < len(domain_slugs) - 1:
                self._sleep_between_domains(partial=totals)

        return totals

    def _discover_from_seed(
        self,
        domain_slug: str,
        seed: str,
        *,
        cat_id: int,
        timeframe: str,
        region: str,
        partial: dict | None = None,
    ) -> dict[str, int]:
        """Interroge related_queries et suggestions pour un mot-clé de départ."""
        self._check_cancel(partial)
        stats = {
            'created': 0,
            'updated': 0,
            'total': 0,
            'top': 0,
            'rising': 0,
            'suggestions': 0,
        }

        try:
            self._pytrends.build_payload(
                [seed],
                cat=cat_id,
                timeframe=timeframe,
                geo=region,
            )
            self._check_cancel(partial)
            related = self._fetch_related_with_retry(partial=partial)

            if related and seed in related:
                domain_data = related[seed]

                if domain_data.get('top') is not None:
                    top_stats = self._save_queries(
                        domain_slug,
                        domain_data['top'],
                        CollectionModelRouter().discovered_model.QueryType.TOP,
                        region,
                    )
                    stats['top'] += top_stats['total']
                    stats['created'] += top_stats['created']
                    stats['updated'] += top_stats['updated']

                if domain_data.get('rising') is not None:
                    rising_stats = self._save_queries(
                        domain_slug,
                        domain_data['rising'],
                        CollectionModelRouter().discovered_model.QueryType.RISING,
                        region,
                    )
                    stats['rising'] += rising_stats['total']
                    stats['created'] += rising_stats['created']
                    stats['updated'] += rising_stats['updated']

        except DomainDiscoveryCancelled:
            raise
        except Exception as exc:
            logger.warning('related_queries échoué pour seed "%s" : %s', seed, exc)

        try:
            self._check_cancel(partial)
            suggestion_stats = self._discover_suggestions(
                domain_slug, seed, region, partial=partial
            )
            stats['suggestions'] += suggestion_stats['total']
            stats['created'] += suggestion_stats['created']
            stats['updated'] += suggestion_stats['updated']
        except DomainDiscoveryCancelled:
            raise
        except Exception as exc:
            logger.warning('suggestions échoué pour seed "%s" : %s', seed, exc)

        stats['total'] = stats['top'] + stats['rising'] + stats['suggestions']
        return stats

    def _discover_suggestions(
        self,
        domain_slug: str,
        seed: str,
        region: str,
        *,
        partial: dict | None = None,
    ) -> dict[str, int]:
        """Enregistre les suggestions autocomplete Google comme requêtes top."""
        stats = {'created': 0, 'updated': 0, 'total': 0}

        suggestions = self._fetch_suggestions_with_retry(seed, partial=partial)
        if not suggestions:
            return stats

        rows = []
        for item in suggestions:
            title = str(item.get('title', '')).strip()
            if title and title.lower() != seed.lower():
                rows.append({'query': title, 'value': 'suggestion'})

        if not rows:
            return stats

        df = pd.DataFrame(rows)
        return self._save_queries(
            domain_slug,
            df,
            CollectionModelRouter().discovered_model.QueryType.TOP,
            region,
        )

    def _fetch_related_with_retry(self, *, partial: dict | None = None) -> dict:
        """Appelle related_queries() avec retry en cas de 429."""
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            self._check_cancel(partial)
            try:
                return self._pytrends.related_queries()
            except DomainDiscoveryCancelled:
                raise
            except pytrends_exceptions.TooManyRequestsError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        'Google Trends 429 — retry %s/%s',
                        attempt,
                        MAX_RETRIES,
                    )
                    self._interruptible_sleep(
                        RETRY_DELAY_SECONDS * attempt,
                        partial=partial,
                    )

        raise RuntimeError(
            'Google Trends a bloqué la requête (429). Attendez quelques minutes.'
        ) from last_error

    def _fetch_suggestions_with_retry(
        self,
        keyword: str,
        *,
        partial: dict | None = None,
    ) -> list:
        """Appelle suggestions() avec retry en cas de 429."""
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            self._check_cancel(partial)
            try:
                return self._pytrends.suggestions(keyword) or []
            except DomainDiscoveryCancelled:
                raise
            except pytrends_exceptions.TooManyRequestsError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    self._interruptible_sleep(
                        RETRY_DELAY_SECONDS * attempt,
                        partial=partial,
                    )

        raise RuntimeError(
            'Google Trends a bloqué la requête (429). Attendez quelques minutes.'
        ) from last_error

    def _save_queries(
        self,
        domain_slug: str,
        df: pd.DataFrame,
        query_type: str,
        region: str,
    ) -> dict[str, int]:
        """Persiste un DataFrame de requêtes associées."""
        stats = {'created': 0, 'updated': 0, 'total': 0}

        if df is None or df.empty:
            return stats

        router = CollectionModelRouter()
        Discovered = router.discovered_model

        with transaction.atomic():
            for _, row in df.iterrows():
                query_text = str(row.get('query', '')).strip()
                if not query_text:
                    continue

                value_display = str(row.get('value', ''))
                stats['total'] += 1

                _, created = Discovered.objects.update_or_create(
                    domain=domain_slug,
                    query=query_text,
                    query_type=query_type,
                    region=region,
                    defaults={'value_display': value_display},
                )

                if created:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1

        return stats

    def _interruptible_sleep(self, seconds: float, *, partial: dict | None = None) -> None:
        """Pause découpée pour honorer l'annulation rapidement (< ~0,5 s)."""
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            self._check_cancel(partial)
            step = min(CANCEL_POLL_SECONDS, remaining)
            time.sleep(step)
            remaining -= step

    def _sleep_between_seeds(self, *, partial: dict | None = None) -> None:
        """Pause aléatoire entre seeds Google Trends (anti-détection)."""
        config = get_collection_config()
        delay_min = float(config.get('GOOGLE_SEED_DELAY_MIN', SEED_DELAY_SECONDS))
        delay_max = float(config.get('GOOGLE_SEED_DELAY_MAX', delay_min + 35))
        delay = random.uniform(delay_min, max(delay_min, delay_max))
        self._report(f'Google Trends — pause anti-blocage ({int(delay)} s)…')
        self._interruptible_sleep(delay, partial=partial)

    def _sleep_between_domains(self, *, partial: dict | None = None) -> None:
        """Pause aléatoire entre domaines Google Trends."""
        config = get_collection_config()
        delay_min = float(config.get('GOOGLE_DOMAIN_DELAY_MIN', 45))
        delay_max = float(config.get('GOOGLE_DOMAIN_DELAY_MAX', 120))
        delay = random.uniform(delay_min, max(delay_min, delay_max))
        self._report(f'Google Trends — pause entre domaines ({int(delay)} s)…')
        self._interruptible_sleep(delay, partial=partial)
