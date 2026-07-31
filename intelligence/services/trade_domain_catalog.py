"""
Catalogue domaines Trade Intelligence — source = MarketDomain (page Domaines).
"""

from __future__ import annotations

ALLOWED_DURATIONS = (10, 20, 30, 60, 120, 180, 240, 300)

DURATION_OPTIONS = [
    {'value': 10, 'label': '10 mn'},
    {'value': 20, 'label': '20 mn'},
    {'value': 30, 'label': '30 mn'},
    {'value': 60, 'label': '1 H'},
    {'value': 120, 'label': '2 H'},
    {'value': 180, 'label': '3 H'},
    {'value': 240, 'label': '4 H'},
    {'value': 300, 'label': '5 H'},
]

DEFAULT_SOURCES = ('google', 'jumia', 'jiji', 'tiktok')


class TradeDomainCatalog:
    """Accès aux domaines actifs configurés dans /intelligence/domaines/."""

    @classmethod
    def list_domains(cls) -> list[dict]:
        from intelligence.models import MarketDomain

        return [
            {'slug': d.slug, 'label': d.label, 'id': d.pk}
            for d in MarketDomain.objects.filter(is_active=True).order_by('label')
        ]

    @classmethod
    def get_domain(cls, slug: str):
        from intelligence.models import MarketDomain

        return MarketDomain.objects.filter(slug=slug, is_active=True).first()

    @classmethod
    def build_search_query(cls, domain_label: str, keyword: str = '') -> str:
        """Construit la requête : [mot-clé] + domaine + Sénégal (mot-clé optionnel)."""
        kw = (keyword or '').strip()
        label = (domain_label or '').strip()
        parts: list[str] = []
        if kw:
            parts.append(kw)
        if label and (not kw or label.lower() not in kw.lower()):
            parts.append(label)
        if not parts:
            raise ValueError('Sélectionnez un domaine.')
        parts.append('Sénégal')
        return ' '.join(parts)[:300]

    @classmethod
    def normalize_duration(cls, minutes) -> int:
        try:
            value = int(minutes)
        except (TypeError, ValueError):
            value = 20
        if value not in ALLOWED_DURATIONS:
            # Plus proche autorisée
            return min(ALLOWED_DURATIONS, key=lambda x: abs(x - value))
        return value

    @classmethod
    def normalize_sources(cls, sources) -> list[str]:
        if not sources:
            return list(DEFAULT_SOURCES)
        allowed = set(DEFAULT_SOURCES)
        cleaned = [str(s).strip().lower() for s in sources if str(s).strip().lower() in allowed]
        return cleaned or list(DEFAULT_SOURCES)
