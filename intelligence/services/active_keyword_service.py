"""Mots-clés actifs Paramètres — source unique pour réseaux, Jumia et Jiji."""

from __future__ import annotations

from intelligence.models import MarketSearchKeyword


class ActiveKeywordService:
    """Centralise la lecture des MarketSearchKeyword actifs."""

    SOCIAL_PLATFORMS = (
        MarketSearchKeyword.Platform.TIKTOK,
        MarketSearchKeyword.Platform.FACEBOOK,
    )

    MARKETPLACE_PLATFORMS = (
        MarketSearchKeyword.Platform.MARKETPLACE,
        MarketSearchKeyword.Platform.JUMIA,
        MarketSearchKeyword.Platform.JIJI,
    )

    @classmethod
    def queryset_active(cls):
        return MarketSearchKeyword.objects.filter(is_active=True).order_by(
            'last_scraped_at',
            'keyword',
        )

    @classmethod
    def _list_for_platforms(cls, platforms: tuple, *, limit: int = 0) -> list[MarketSearchKeyword]:
        qs = cls.queryset_active().filter(platform__in=platforms)
        if limit > 0:
            qs = qs[:limit]
        return list(qs)

    @classmethod
    def _dedupe_marketplace_keywords(
        cls,
        keywords: list[MarketSearchKeyword],
        *,
        limit: int = 0,
    ) -> list[MarketSearchKeyword]:
        """Évite les doublons legacy jumia/jiji pour un même mot-clé."""
        seen: set[tuple[str, str]] = set()
        unique: list[MarketSearchKeyword] = []
        priority = {
            MarketSearchKeyword.Platform.MARKETPLACE: 0,
            MarketSearchKeyword.Platform.JUMIA: 1,
            MarketSearchKeyword.Platform.JIJI: 2,
        }
        ordered = sorted(
            keywords,
            key=lambda kw: (
                priority.get(kw.platform, 9),
                kw.last_scraped_at or kw.created_at,
                kw.keyword,
            ),
        )
        for kw in ordered:
            key = (kw.keyword.strip().lower(), kw.region)
            if key in seen:
                continue
            seen.add(key)
            unique.append(kw)
        if limit > 0:
            return unique[:limit]
        return unique

    @classmethod
    def list_for_session(cls, *, limit: int = 0) -> list[MarketSearchKeyword]:
        """Tous les mots-clés actifs (comptages UI globaux)."""
        qs = cls.queryset_active()
        if limit > 0:
            qs = qs[:limit]
        return list(qs)

    @classmethod
    def list_for_social(cls, *, limit: int = 0) -> list[MarketSearchKeyword]:
        """TikTok / Facebook — collectes réseaux sociaux."""
        return cls._list_for_platforms(cls.SOCIAL_PLATFORMS, limit=limit)

    @classmethod
    def list_for_marketplace(cls, *, limit: int = 0) -> list[MarketSearchKeyword]:
        """Jumia + Jiji — mots-clés marché partagés."""
        keywords = cls._list_for_platforms(cls.MARKETPLACE_PLATFORMS, limit=0)
        return cls._dedupe_marketplace_keywords(keywords, limit=limit)

    @classmethod
    def list_for_jumia(cls, *, limit: int = 0) -> list[MarketSearchKeyword]:
        """Mots-clés marketplace actifs — collecte Jumia (même liste que Jiji)."""
        return cls.list_for_marketplace(limit=limit)

    @classmethod
    def list_for_jiji(cls, *, limit: int = 0) -> list[MarketSearchKeyword]:
        """Mots-clés marketplace actifs — collecte Jiji (même liste que Jumia)."""
        return cls.list_for_marketplace(limit=limit)

    @classmethod
    def get_active_or_none(cls, keyword_id: int | None) -> MarketSearchKeyword | None:
        if not keyword_id:
            return None
        return cls.queryset_active().filter(pk=keyword_id).first()

    @classmethod
    def count_active(cls) -> int:
        return cls.queryset_active().count()

    @classmethod
    def count_social(cls) -> int:
        return cls.queryset_active().filter(platform__in=cls.SOCIAL_PLATFORMS).count()

    @classmethod
    def count_marketplace(cls) -> int:
        return len(cls.list_for_marketplace())

    @classmethod
    def count_jumia(cls) -> int:
        return cls.count_marketplace()

    @classmethod
    def count_jiji(cls) -> int:
        return cls.count_marketplace()
