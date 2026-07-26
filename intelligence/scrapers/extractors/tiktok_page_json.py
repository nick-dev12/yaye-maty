"""
Extraction métriques TikTok depuis JSON embarqué (SIGI_STATE / rehydration).

TikTok expose souvent stats complètes (likes, partages, favoris, vues, date)
dans le HTML avant le rendu DOM — plus fiable que les sélecteurs CSS seuls.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone as dt_timezone
from typing import Any

from playwright.sync_api import Page

logger = logging.getLogger(__name__)

EMBED_SCRIPT_IDS = ('SIGI_STATE', '__UNIVERSAL_DATA_FOR_REHYDRATION__')

STAT_FIELD_MAP = {
    'diggCount': 'like_count',
    'digg_count': 'like_count',
    'likeCount': 'like_count',
    'like_count': 'like_count',
    'shareCount': 'share_count',
    'share_count': 'share_count',
    'collectCount': 'save_count',
    'collect_count': 'save_count',
    'saveCount': 'save_count',
    'save_count': 'save_count',
    'commentCount': 'comment_count',
    'comment_count': 'comment_count',
    'playCount': 'view_count',
    'play_count': 'view_count',
    'viewCount': 'view_count',
    'view_count': 'view_count',
}

TIME_FIELD_NAMES = frozenset({
    'createTime', 'create_time', 'createDate', 'create_date',
})


def _parse_int(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        if isinstance(value, str):
            cleaned = value.replace(',', '.').strip().lower()
            if cleaned.endswith('k'):
                return int(float(cleaned[:-1]) * 1_000)
            if cleaned.endswith('m'):
                return int(float(cleaned[:-1]) * 1_000_000)
            return int(float(cleaned))
        return int(value)
    except (TypeError, ValueError):
        return None


def _unix_to_iso(value: Any) -> str:
    if not value:
        return ''
    try:
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ''


def _looks_like_stats(node: dict) -> bool:
    keys = set(node.keys())
    indicators = {
        'diggCount', 'digg_count', 'likeCount', 'like_count',
        'shareCount', 'share_count', 'playCount', 'play_count',
        'commentCount', 'comment_count', 'collectCount', 'collect_count',
    }
    return len(keys & indicators) >= 2


def _extract_stats_dict(node: dict) -> dict[str, int | None]:
    metrics: dict[str, int | None] = {}
    stats_candidates = [node]

    for nested_key in ('stats', 'statsV2', 'statistics', 'videoStats'):
        nested = node.get(nested_key)
        if isinstance(nested, dict):
            stats_candidates.append(nested)

    for stats in stats_candidates:
        if not isinstance(stats, dict):
            continue
        for raw_key, target_key in STAT_FIELD_MAP.items():
            if target_key in metrics and metrics[target_key] is not None:
                continue
            if raw_key in stats:
                parsed = _parse_int(stats[raw_key])
                if parsed is not None:
                    metrics[target_key] = parsed

    return metrics


def _extract_item_struct(node: dict) -> dict[str, Any]:
    """Fusionne métriques, caption, auteur et date depuis un nœud itemStruct."""
    result: dict[str, Any] = {}

    metrics = _extract_stats_dict(node)
    if metrics:
        result.update(metrics)

    for time_key in TIME_FIELD_NAMES:
        if time_key in node:
            iso = _unix_to_iso(node[time_key])
            if iso:
                result['published_at'] = iso
                break

    desc = node.get('desc') or node.get('description') or node.get('title')
    if isinstance(desc, str) and len(desc.strip()) >= 8:
        result['content'] = desc.strip()

    author_meta = node.get('author') or node.get('authorMeta') or {}
    if isinstance(author_meta, dict):
        unique_id = author_meta.get('uniqueId') or author_meta.get('unique_id') or author_meta.get('nickname')
        if unique_id:
            result['author'] = str(unique_id).lstrip('@')

    return result


def _walk_for_video_data(
    node: Any,
    *,
    post_id: str = '',
    depth: int = 0,
    max_depth: int = 14,
) -> dict[str, Any]:
    if depth > max_depth:
        return {}

    if isinstance(node, dict):
        if post_id and str(node.get('id', '')) == post_id:
            found = _extract_item_struct(node)
            if found:
                return found

        if _looks_like_stats(node) or any(k in node for k in ('desc', 'author', 'authorMeta')):
            found = _extract_item_struct(node)
            if len(found) >= 2:
                return found

        for key in ('itemStruct', 'itemInfo', 'video', 'videoData', 'ItemModule'):
            child = node.get(key)
            if isinstance(child, dict):
                if key == 'ItemModule' and post_id and post_id in child:
                    found = _extract_item_struct(child[post_id])
                    if found:
                        return found
                found = _walk_for_video_data(child, post_id=post_id, depth=depth + 1, max_depth=max_depth)
                if found:
                    return found

        for value in node.values():
            if isinstance(value, (dict, list)):
                found = _walk_for_video_data(value, post_id=post_id, depth=depth + 1, max_depth=max_depth)
                if found:
                    return found

    elif isinstance(node, list):
        for item in node[:80]:
            found = _walk_for_video_data(item, post_id=post_id, depth=depth + 1, max_depth=max_depth)
            if found:
                return found

    return {}


def load_embedded_json(page: Page) -> dict | list | None:
    """Charge SIGI_STATE ou __UNIVERSAL_DATA_FOR_REHYDRATION__ depuis la page."""
    try:
        raw = page.evaluate(
            """() => {
                const ids = ['SIGI_STATE', '__UNIVERSAL_DATA_FOR_REHYDRATION__'];
                for (const id of ids) {
                    const el = document.getElementById(id);
                    if (el && el.textContent) return el.textContent;
                }
                return null;
            }"""
        )
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug('JSON embarqué TikTok indisponible : %s', exc)
        return None


def extract_video_data_from_page(page: Page, *, post_id: str = '') -> dict[str, Any]:
    """
    Extrait métriques, caption, auteur et published_at depuis le JSON embarqué.
    """
    payload = load_embedded_json(page)
    if payload is None:
        return {}

    found = _walk_for_video_data(payload, post_id=post_id)
    if found:
        logger.debug(
            'JSON TikTok [%s] : views=%s likes=%s shares=%s saves=%s date=%s',
            post_id or '?',
            found.get('view_count'),
            found.get('like_count'),
            found.get('share_count'),
            found.get('save_count'),
            bool(found.get('published_at')),
        )
    return found


def parse_relative_french_date(text: str) -> str:
    """
    Parse quelques formats relatifs TikTok FR (fallback si pas de createTime).
    Ex. « 2024-3-15 », « 15-3-2024 ».
    """
    if not text:
        return ''

    cleaned = re.sub(r'\s+', ' ', text.strip())
    match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', cleaned)
    if match:
        year, month, day = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day), tzinfo=dt_timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    match = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', cleaned)
    if match:
        day, month, year = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day), tzinfo=dt_timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    return ''
