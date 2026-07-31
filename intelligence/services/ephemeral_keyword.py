"""Mot-clé éphémère pour collecte ad-hoc Trade Intelligence (sans Paramètres)."""

from __future__ import annotations

from intelligence.models import MarketSearchKeyword


def build_ephemeral_keyword(
    query: str,
    *,
    platform: str = MarketSearchKeyword.Platform.TIKTOK,
    product_category: str = '',
    max_videos: int = 10,
    max_comments: int = 15,
) -> MarketSearchKeyword:
    """Instancie un MarketSearchKeyword non persisté utilisable par les scrapers."""
    return MarketSearchKeyword(
        keyword=query.strip()[:200],
        label=query.strip()[:120],
        platform=platform,
        product_category=product_category[:80],
        region='SN',
        max_videos=max_videos,
        max_comments=max_comments,
        is_active=True,
        listing_page_offset=1,
    )
