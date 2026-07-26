"""
Contrôleur d'extraction Google Trends via pytrends.

Collecte les scores d'intérêt (0-100) pour des mots-clés liés
à l'équipement agricole au Sénégal.
"""

import logging
import time
from typing import Sequence

import pandas as pd
from django.db import transaction
from pytrends import exceptions as pytrends_exceptions
from pytrends.request import TrendReq

from intelligence.models import TrendRecord

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    'tracteur',
    'engrais',
    'pompe solaire',
    'semence',
    'irrigation',
]

MAX_KEYWORDS_PER_REQUEST = 5
DEFAULT_REGION = 'SN'
DEFAULT_TIMEFRAME = 'today 3-m'
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10


class GoogleTrendsController:
    """Interroge Google Trends et persiste les résultats en base."""

    def __init__(self, hl: str = 'fr-FR', tz: int = 0):
        self._pytrends = TrendReq(hl=hl, tz=tz)

    def fetch_interest_over_time(
        self,
        keywords: Sequence[str],
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        region: str = DEFAULT_REGION,
    ) -> pd.DataFrame:
        """Récupère l'intérêt dans le temps pour une liste de mots-clés."""
        if not keywords:
            raise ValueError('Au moins un mot-clé est requis.')

        if len(keywords) > MAX_KEYWORDS_PER_REQUEST:
            raise ValueError(
                f'Pytrends accepte au maximum {MAX_KEYWORDS_PER_REQUEST} '
                f'mots-clés par requête.'
            )

        clean_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not clean_keywords:
            raise ValueError('Aucun mot-clé valide fourni.')

        logger.info(
            'Requête Google Trends — mots-clés: %s, région: %s, période: %s',
            clean_keywords,
            region,
            timeframe,
        )

        try:
            self._pytrends.build_payload(
                clean_keywords,
                timeframe=timeframe,
                geo=region,
            )
            df = self._fetch_with_retry()
        except Exception as exc:
            logger.exception('Échec de la requête Google Trends')
            raise RuntimeError(
                f'Erreur lors de la collecte Google Trends : {exc}'
            ) from exc

        if df is None or df.empty:
            raise RuntimeError(
                'Google Trends a renvoyé un jeu de données vide. '
                'Réessayez plus tard ou modifiez les mots-clés.'
            )

        if 'isPartial' in df.columns:
            df = df.drop(columns=['isPartial'])

        return df

    def _fetch_with_retry(self) -> pd.DataFrame:
        """Exécute interest_over_time() avec nouvelles tentatives en cas de 429."""
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self._pytrends.interest_over_time()
            except pytrends_exceptions.TooManyRequestsError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        'Google Trends 429 — nouvelle tentative %s/%s dans %ss',
                        attempt,
                        MAX_RETRIES,
                        RETRY_DELAY_SECONDS,
                    )
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
                else:
                    logger.error(
                        'Quota Google Trends dépassé après %s tentatives',
                        MAX_RETRIES,
                    )

        raise RuntimeError(
            'Google Trends a bloqué la requête (code 429). '
            'Attendez quelques minutes avant de relancer.'
        ) from last_error

    def save_dataframe(
        self,
        df: pd.DataFrame,
        *,
        region: str = DEFAULT_REGION,
    ) -> dict[str, int]:
        """Persiste un DataFrame Google Trends dans TrendRecord."""
        stats = {'created': 0, 'updated': 0, 'total_rows': 0}

        with transaction.atomic():
            for record_date, row in df.iterrows():
                record_day = (
                    record_date.date()
                    if hasattr(record_date, 'date')
                    else record_date
                )

                for keyword in df.columns:
                    score = int(row[keyword])
                    stats['total_rows'] += 1

                    _, created = TrendRecord.objects.update_or_create(
                        keyword=keyword,
                        date=record_day,
                        region=region,
                        source=TrendRecord.Source.GOOGLE_TRENDS,
                        defaults={'score': score},
                    )

                    if created:
                        stats['created'] += 1
                    else:
                        stats['updated'] += 1

        logger.info(
            'Sauvegarde terminée — créés: %(created)s, mis à jour: %(updated)s',
            stats,
        )
        return stats

    def fetch_and_save(
        self,
        keywords: Sequence[str],
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        region: str = DEFAULT_REGION,
    ) -> dict[str, int]:
        """Collecte et sauvegarde les tendances pour un lot de mots-clés."""
        df = self.fetch_interest_over_time(
            keywords,
            timeframe=timeframe,
            region=region,
        )
        return self.save_dataframe(df, region=region)

    def fetch_and_save_batches(
        self,
        keywords: Sequence[str],
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        region: str = DEFAULT_REGION,
    ) -> dict[str, int]:
        """Collecte les tendances par lots de 5 mots-clés maximum."""
        clean_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not clean_keywords:
            raise ValueError('Aucun mot-clé valide fourni.')

        totals = {'created': 0, 'updated': 0, 'total_rows': 0, 'batches': 0}

        for i in range(0, len(clean_keywords), MAX_KEYWORDS_PER_REQUEST):
            batch = clean_keywords[i:i + MAX_KEYWORDS_PER_REQUEST]
            batch_stats = self.fetch_and_save(
                batch,
                timeframe=timeframe,
                region=region,
            )
            totals['batches'] += 1
            totals['created'] += batch_stats['created']
            totals['updated'] += batch_stats['updated']
            totals['total_rows'] += batch_stats['total_rows']

            if i + MAX_KEYWORDS_PER_REQUEST < len(clean_keywords):
                time.sleep(RETRY_DELAY_SECONDS)

        return totals
