"""
Filtres date pour la page Archives Intelligence (même UI que le flux actuel).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from django.utils import timezone


@dataclass
class ArchiveDateFilters:
    date_start: str = ''
    date_end: str = ''
    since: datetime | None = None
    until: datetime | None = None


class ArchivesDisplayService:
    """Parse les filtres GET de la page Archives."""

    @classmethod
    def parse_date_filters(cls, request) -> ArchiveDateFilters:
        date_start = (request.GET.get('date_debut') or '').strip()
        date_end = (request.GET.get('date_fin') or '').strip()
        return ArchiveDateFilters(
            date_start=date_start,
            date_end=date_end,
            since=cls._parse_date(date_start),
            until=cls._parse_date(date_end, end_of_day=True),
        )

    @staticmethod
    def _parse_date(value: str, *, end_of_day: bool = False) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return None
        combined = datetime.combine(parsed, time.max if end_of_day else time.min)
        if timezone.is_naive(combined):
            return timezone.make_aware(combined, timezone.get_current_timezone())
        return combined
