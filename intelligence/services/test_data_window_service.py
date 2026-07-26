"""
Fenêtre temporelle des données collectées en mode test (session 20 min).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from intelligence.services.collection_test_context_service import CollectionTestContextService
from intelligence.services.market_data_window_service import MarketDataWindowService


class TestDataWindowService:
    """Persiste et résout la plage horaire d'une session de test."""

    SESSION_KEY = 'collecte_test_window'

    @classmethod
    def mark_started(cls, request) -> None:
        now = timezone.now()
        request.session[cls.SESSION_KEY] = {
            'started_at': now.isoformat(),
            'ended_at': None,
            'job': '',
        }
        request.session.modified = True

    @classmethod
    def mark_completed(cls, request) -> None:
        payload = request.session.get(cls.SESSION_KEY) or {}
        if not payload.get('started_at'):
            return
        payload['ended_at'] = timezone.now().isoformat()
        request.session[cls.SESSION_KEY] = payload
        request.session.modified = True

    @classmethod
    def touch_job(cls, request, job: str) -> None:
        payload = request.session.get(cls.SESSION_KEY) or {}
        if payload:
            payload['job'] = job
            request.session[cls.SESSION_KEY] = payload
            request.session.modified = True

    @classmethod
    def get_window(cls, request) -> dict:
        """Retourne since/until pour filtrer les données de la dernière session test."""
        payload = request.session.get(cls.SESSION_KEY) or {}
        minutes = CollectionTestContextService.SESSION_MINUTES
        now = timezone.now()

        started_raw = payload.get('started_at')
        ended_raw = payload.get('ended_at')

        if started_raw:
            since = cls._parse_iso(started_raw) or (now - timedelta(minutes=minutes))
            until = cls._parse_iso(ended_raw) if ended_raw else now
        else:
            since = now - timedelta(minutes=minutes)
            until = now

        if since > until:
            since, until = until, since

        has_session = bool(started_raw)
        job = payload.get('job') or ''

        return {
            'since': since,
            'until': until,
            'minutes': minutes,
            'has_session': has_session,
            'job': job,
            'started_at': cls._parse_iso(started_raw) if started_raw else None,
            'ended_at': cls._parse_iso(ended_raw) if ended_raw else None,
            'label': cls._build_label(has_session, since, until, minutes),
            'short_label': f'Test · {minutes} min',
            'last_update': until if has_session else None,
            'last_update_label': MarketDataWindowService.format_relative(until) if has_session else 'Aucun test lancé',
            'is_live': False,
            'is_test': True,
            'days': max(1, int((until - since).total_seconds() // 86400) + 1),
        }

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_label(has_session: bool, since: datetime, until: datetime, minutes: int) -> str:
        if not has_session:
            return f'Données des {minutes} dernières minutes (aucune session enregistrée)'
        start = timezone.localtime(since).strftime('%H:%M')
        end = timezone.localtime(until).strftime('%H:%M')
        return f'Session de test · {start} → {end}'
