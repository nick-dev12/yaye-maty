"""
Structure d'enregistrement des publications TikTok scrapées — YAYEMATY MARKET.

1. Validation (métriques de performance)
   - video_id, vues, likes, partages, saves

2. Contexte NLP
   - caption, hashtags, published_at

3. Conversion (commentaires)
   - 10 à 20 commentaires : text, commented_at
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from django.utils.dateparse import parse_datetime

from intelligence.scrapers.constants import PLATFORM_TIKTOK

if TYPE_CHECKING:
    from intelligence.models import SocialPost
    from intelligence.scrapers.extractors.base import ExtractedPost

# ─── Constantes scraping TikTok ───
MIN_COMMENTS_PER_VIDEO = 10
MAX_COMMENTS_PER_VIDEO = 20
DEFAULT_MAX_COMMENTS = 20
MAX_CAPTION_LENGTH = 5000
MAX_COMMENT_TEXT_LENGTH = 2000


def clamp_max_comments(value: int | None) -> int:
    """Borne le nombre de commentaires à collecter entre 10 et 20."""
    if value is None:
        return DEFAULT_MAX_COMMENTS
    return max(MIN_COMMENTS_PER_VIDEO, min(int(value), MAX_COMMENTS_PER_VIDEO))


def normalize_comment(raw, *, index: int = 0, video_id: str = '') -> dict | None:
    """
    Normalise un commentaire brut vers la structure conversion.

    Retourne : text, platform_comment_id, commented_at (+ published_at alias).
    """
    if isinstance(raw, dict):
        text = str(raw.get('text') or raw.get('content') or '').strip()
        platform_comment_id = str(
            raw.get('platform_comment_id') or raw.get('comment_id') or raw.get('cid') or ''
        ).strip()
        commented_at_raw = raw.get('commented_at') or raw.get('published_at') or raw.get('create_time')
    else:
        text = str(raw).strip()
        platform_comment_id = ''
        commented_at_raw = None

    if len(text) < 3:
        return None

    if not platform_comment_id:
        from intelligence.scrapers.post_id_utils import build_comment_id
        platform_comment_id = build_comment_id(PLATFORM_TIKTOK, video_id, text, index)

    commented_at = _normalize_datetime(commented_at_raw)

    return {
        'text': text[:MAX_COMMENT_TEXT_LENGTH],
        'platform_comment_id': platform_comment_id[:100],
        'commented_at': commented_at,
        'published_at': commented_at,
    }


def normalize_comments(
    comments: list,
    *,
    video_id: str = '',
    max_count: int = MAX_COMMENTS_PER_VIDEO,
) -> list[dict]:
    """Déduplique et borne la liste de commentaires (max 20)."""
    max_count = clamp_max_comments(max_count)
    normalized: list[dict] = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()

    for index, raw in enumerate(comments or []):
        if len(normalized) >= max_count:
            break

        item = normalize_comment(raw, index=index, video_id=video_id)
        if not item:
            continue

        dedupe_key = item['platform_comment_id'] or item['text'].lower()
        if dedupe_key in seen_ids or item['text'].lower() in seen_texts:
            continue

        seen_ids.add(dedupe_key)
        seen_texts.add(item['text'].lower())
        normalized.append(item)

    return normalized


def normalize_extracted_post(item: ExtractedPost, *, platform: str) -> ExtractedPost:
    """Applique la structure TikTok sur une publication extraite."""
    if platform != PLATFORM_TIKTOK:
        return item

    from intelligence.scrapers.engagement_utils import extract_hashtags
    from intelligence.models import SocialPost

    content = (item.content or '').strip()[:MAX_CAPTION_LENGTH]
    post_url = (item.post_url or '').strip()
    platform_post_id = SocialPost.resolve_platform_post_id(
        platform,
        post_url,
        item.platform_post_id,
    )
    hashtags = item.hashtags or extract_hashtags(content)
    comments = normalize_comments(
        item.comments,
        video_id=platform_post_id,
        max_count=MAX_COMMENTS_PER_VIDEO,
    )

    return replace(
        item,
        content=content,
        post_url=post_url,
        platform_post_id=platform_post_id,
        hashtags=hashtags,
        comments=comments,
        comment_count=item.comment_count or len(comments),
    )


def validate_tiktok_record(item: ExtractedPost) -> list[str]:
    """Retourne les erreurs bloquantes pour une vidéo TikTok."""
    errors: list[str] = []

    if not item.platform_post_id:
        errors.append('video_id (platform_post_id) manquant — doublons possibles.')

    if not (item.content or '').strip():
        errors.append('caption (description) vide.')

    if item.view_count is None and item.like_count is None and item.save_count is None:
        errors.append('Aucune métrique de validation (vues, likes ou saves).')

    if len(item.comments or []) < MIN_COMMENTS_PER_VIDEO:
        errors.append(
            f'Commentaires insuffisants ({len(item.comments or [])}/{MIN_COMMENTS_PER_VIDEO} minimum).'
        )

    return errors


def validation_warnings(item: ExtractedPost) -> list[str]:
    """Avertissements non bloquants (enregistrement possible)."""
    warnings: list[str] = []
    if len(item.comments or []) < MIN_COMMENTS_PER_VIDEO:
        warnings.append(
            f'Moins de {MIN_COMMENTS_PER_VIDEO} commentaires collectés '
            f'({len(item.comments or [])}).'
        )
    if item.save_count is None:
        warnings.append('save_count (favoris) non extrait — indicateur e-commerce crucial.')
    return warnings


def serialize_post_for_nlp(post: SocialPost) -> dict:
    """
    Exporte une publication au format spec hybride (filtre local + CamemBERT).
    """
    comments = []
    for raw in post.comments or []:
        if isinstance(raw, dict):
            text = raw.get('text', '')
            commented_at = raw.get('commented_at') or raw.get('published_at')
        else:
            text = str(raw)
            commented_at = None
        if not text:
            continue
        comments.append({
            'text': text,
            'commented_at': commented_at,
            'platform_comment_id': raw.get('platform_comment_id', '') if isinstance(raw, dict) else '',
        })

    return {
        'id': post.pk,
        'platform': post.platform,
        'video_id': post.platform_post_id,
        'validation': {
            'view_count': post.view_count,
            'like_count': post.like_count,
            'share_count': post.share_count,
            'save_count': post.save_count,
            'comment_count': post.comment_count,
            'demand_score': post.demand_score,
        },
        'context': {
            'caption': post.content,
            'hashtags': post.hashtags,
            'published_at': post.published_at.isoformat() if post.published_at else None,
            'author': post.author,
            'post_url': post.post_url,
            'source_url': post.source_url,
        },
        'conversion': {
            'comments': comments,
            'comments_scraped_count': post.comments_scraped_count,
        },
        'scraped_at': post.scraped_at.isoformat(),
    }


def _normalize_datetime(value) -> str:
    if not value:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    parsed = parse_datetime(str(value))
    if parsed:
        return parsed.isoformat()
    return str(value)
