"""
Extraction commentaires TikTok — API réseau + panneau DOM.

TikTok charge les commentaires via XHR après ouverture du panneau ;
cette couche combine interception réseau et sélecteurs Playwright.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone as dt_timezone

from playwright.sync_api import Page, Response

from intelligence.scrapers.human_behavior import random_sleep
from intelligence.scrapers.post_id_utils import build_comment_id

logger = logging.getLogger(__name__)

COMMENT_API_MARKERS = ('/api/comment/list', '/comment/list/', 'comment/list?')

COMMENT_BUTTON_SELECTORS = [
    '[data-e2e="comment-icon"]',
    '[data-e2e="browse-comment-icon"]',
    '[data-e2e="comment-count"]',
    '[data-e2e="video-comment-count"]',
    'button[aria-label*="comment" i]',
    'button[aria-label*="Commentaire" i]',
]

COMMENT_CONTAINER_SELECTORS = [
    '[data-e2e="comment-list"]',
    '[data-e2e="comment-list-container"]',
    '[class*="CommentListContainer"]',
    '[class*="DivCommentListContainer"]',
]

COMMENT_ITEM_SELECTORS = [
    '[data-e2e="comment-level-1"]',
    '[data-e2e="comment-item"]',
]

COMMENT_TEXT_SELECTORS = [
    '[data-e2e="comment-text"]',
    '[data-e2e="comment-level-1"] span[data-e2e="comment-text"]',
    '[class*="CommentText"]',
]

COMMENT_TIME_SELECTORS = [
    '[data-e2e="comment-time"]',
    'time[datetime]',
]

NOISE_TOKENS = frozenset({
    'Voir plus', 'Voir moins', 'Suivre', "J'aime", 'Partager', 'Favoris',
    'Commentaires', 'Répondre', 'Original sound', 'Reply', 'Like',
})


def parse_comment_api_payload(payload: dict, *, post_id: str = '') -> list[dict]:
    """Normalise la réponse JSON de l'API comment/list TikTok."""
    comments_raw = payload.get('comments')
    if comments_raw is None and isinstance(payload.get('data'), dict):
        comments_raw = payload['data'].get('comments')
    if not isinstance(comments_raw, list):
        return []

    results: list[dict] = []
    for index, item in enumerate(comments_raw):
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or item.get('content') or '').strip()
        if len(text) < 3:
            continue

        cid = str(item.get('cid') or item.get('comment_id') or item.get('id') or '')
        if not cid:
            cid = build_comment_id('tiktok', post_id, text, index)

        create_time = item.get('create_time') or item.get('createTime')
        published_at = _unix_to_iso(create_time)

        results.append({
            'text': text[:500],
            'platform_comment_id': cid[:100],
            'commented_at': published_at,
            'published_at': published_at,
        })

    return results


def _unix_to_iso(value) -> str:
    if not value:
        return ''
    try:
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ''


class TikTokCommentCapture:
    """Intercepte les réponses API comment/list pendant la navigation."""

    def __init__(self, *, post_id: str = ''):
        self.post_id = post_id
        self.items: list[dict] = []
        self._seen_ids: set[str] = set()
        self._seen_texts: set[str] = set()

    def on_response(self, response: Response) -> None:
        url = response.url or ''
        if not any(marker in url for marker in COMMENT_API_MARKERS):
            return
        if response.status != 200:
            return
        try:
            payload = response.json()
        except Exception:
            return

        for comment in parse_comment_api_payload(payload, post_id=self.post_id):
            key = comment['platform_comment_id'] or comment['text'][:80]
            if key in self._seen_ids or comment['text'] in self._seen_texts:
                continue
            self._seen_ids.add(key)
            self._seen_texts.add(comment['text'])
            self.items.append(comment)

    def merge(self, others: list[dict], *, max_comments: int) -> list[dict]:
        merged = list(self.items)
        for comment in others:
            key = comment.get('platform_comment_id') or comment.get('text', '')[:80]
            text = comment.get('text', '')
            if key in self._seen_ids or text in self._seen_texts:
                continue
            self._seen_ids.add(key)
            self._seen_texts.add(text)
            merged.append(comment)
        return merged[:max_comments]


def open_comments_panel(page: Page) -> bool:
    """Ouvre le panneau commentaires si nécessaire."""
    for selector in COMMENT_ITEM_SELECTORS + COMMENT_TEXT_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue

    for selector in COMMENT_BUTTON_SELECTORS:
        try:
            button = page.locator(selector).first
            if button.count() and button.is_visible(timeout=1_000):
                button.click(timeout=3_000)
                random_sleep(1.0, 2.0)
                return True
        except Exception:
            continue

    try:
        page.keyboard.press('c')
        random_sleep(0.8, 1.5)
    except Exception:
        pass

    return False


def scroll_comments_panel(page: Page, *, iterations: int = 4) -> None:
    """Scroll le conteneur commentaires pour déclencher le chargement XHR."""
    container = None
    for selector in COMMENT_CONTAINER_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible(timeout=800):
                container = loc
                break
        except Exception:
            continue

    for _ in range(iterations):
        try:
            if container:
                container.evaluate(
                    '(el) => { el.scrollTop = el.scrollTop + Math.max(el.clientHeight, 400); }'
                )
            else:
                page.mouse.wheel(0, 600)
        except Exception:
            page.mouse.wheel(0, 600)
        random_sleep(0.6, 1.2)


def extract_comments_from_dom(
    page: Page,
    *,
    max_comments: int,
    post_id: str = '',
) -> list[dict]:
    """Extrait les commentaires visibles dans le DOM TikTok."""
    comments: list[dict] = []
    seen: set[str] = set()

    for text_selector in COMMENT_TEXT_SELECTORS:
        if len(comments) >= max_comments:
            break
        locator = page.locator(text_selector)
        count = min(locator.count(), max_comments * 2)

        for index in range(count):
            if len(comments) >= max_comments:
                break
            try:
                element = locator.nth(index)
                text = _clean_text(element.inner_text(timeout=1_500))
                text = _strip_comment_noise(text)
                if not text or len(text) < 4 or text in seen:
                    continue

                parent = element.locator(
                    'xpath=ancestor::*[@data-e2e="comment-level-1" or @data-e2e="comment-item"][1]'
                ).first
                platform_comment_id = ''
                published_at = ''
                if parent.count():
                    platform_comment_id = (
                        parent.get_attribute('data-comment-id')
                        or parent.get_attribute('id')
                        or ''
                    )
                    published_at = _extract_comment_datetime(parent)

                if not platform_comment_id:
                    platform_comment_id = build_comment_id('tiktok', post_id, text, index)

                seen.add(text)
                comments.append({
                    'text': text[:500],
                    'platform_comment_id': str(platform_comment_id)[:100],
                    'published_at': published_at,
                })
            except Exception:
                continue

    if len(comments) < max_comments // 2:
        comments.extend(
            _extract_comments_from_items(page, max_comments=max_comments, post_id=post_id, seen=seen)
        )

    return comments[:max_comments]


def _extract_comments_from_items(
    page: Page,
    *,
    max_comments: int,
    post_id: str,
    seen: set[str],
) -> list[dict]:
    comments: list[dict] = []
    for item_selector in COMMENT_ITEM_SELECTORS:
        if len(comments) >= max_comments:
            break
        locator = page.locator(item_selector)
        count = min(locator.count(), max_comments * 2)

        for index in range(count):
            if len(comments) >= max_comments:
                break
            try:
                element = locator.nth(index)
                text = _clean_text(element.inner_text(timeout=1_500))
                text = _strip_comment_noise(text)
                if not text or len(text) < 4 or text in seen:
                    continue

                seen.add(text)
                platform_comment_id = (
                    element.get_attribute('data-comment-id')
                    or element.get_attribute('id')
                    or build_comment_id('tiktok', post_id, text, index)
                )
                comments.append({
                    'text': text[:500],
                    'platform_comment_id': str(platform_comment_id)[:100],
                    'published_at': _extract_comment_datetime(element),
                })
            except Exception:
                continue

    return comments


def extract_comments_from_page_scripts(page: Page, *, post_id: str = '', max_comments: int = 20) -> list[dict]:
    """Tente d'extraire les commentaires depuis SIGI_STATE / rehydration JSON."""
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
            return []
        data = json.loads(raw)
        return _find_comments_in_json(data, post_id=post_id, max_comments=max_comments)
    except Exception:
        return []


def _find_comments_in_json(node, *, post_id: str, max_comments: int, depth: int = 0) -> list[dict]:
    if depth > 12:
        return []
    if isinstance(node, dict):
        if 'comments' in node and isinstance(node['comments'], list):
            parsed = parse_comment_api_payload(node, post_id=post_id)
            if parsed:
                return parsed[:max_comments]
        for value in node.values():
            found = _find_comments_in_json(value, post_id=post_id, max_comments=max_comments, depth=depth + 1)
            if found:
                return found[:max_comments]
    elif isinstance(node, list):
        for item in node[:50]:
            found = _find_comments_in_json(item, post_id=post_id, max_comments=max_comments, depth=depth + 1)
            if found:
                return found[:max_comments]
    return []


def _extract_comment_datetime(element) -> str:
    for selector in COMMENT_TIME_SELECTORS:
        try:
            time_el = element.locator(selector).first
            if not time_el.count():
                continue
            datetime_value = time_el.get_attribute('datetime')
            if datetime_value:
                return datetime_value
        except Exception:
            continue
    return ''


def _strip_comment_noise(text: str) -> str:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    filtered = [line for line in lines if line not in NOISE_TOKENS and len(line) > 2]
    if not filtered:
        return ''
    return filtered[0] if len(filtered) == 1 else ' '.join(filtered[:2])


def _clean_text(value: str) -> str:
    text = re.sub(r'\s+', ' ', value or '').strip()
    for item in NOISE_TOKENS:
        text = text.replace(item, '')
    return text.strip()


def harvest_video_comments(
    page: Page,
    *,
    post_id: str = '',
    max_comments: int = 20,
    capture: TikTokCommentCapture | None = None,
) -> list[dict]:
    """
    Pipeline complet : ouverture panneau → scroll → API + DOM + JSON embarqué.
    """
    owns_capture = capture is None
    if capture is None:
        capture = TikTokCommentCapture(post_id=post_id)
        page.on('response', capture.on_response)

    try:
        open_comments_panel(page)
        random_sleep(1.0, 2.0)

        for selector in COMMENT_TEXT_SELECTORS + COMMENT_ITEM_SELECTORS:
            try:
                page.wait_for_selector(selector, timeout=5_000, state='attached')
                break
            except Exception:
                continue

        scroll_comments_panel(page, iterations=8)
        random_sleep(2.0, 3.0)
        scroll_comments_panel(page, iterations=3)

        dom_comments = extract_comments_from_dom(page, max_comments=max_comments, post_id=post_id)
        script_comments = extract_comments_from_page_scripts(
            page, post_id=post_id, max_comments=max_comments,
        )
        merged = capture.merge(dom_comments + script_comments, max_comments=max_comments)

        logger.info(
            'Commentaires TikTok [%s] : api=%s dom=%s script=%s total=%s',
            post_id or '?',
            len(capture.items),
            len(dom_comments),
            len(script_comments),
            len(merged),
        )
        return merged
    finally:
        if owns_capture:
            try:
                page.remove_listener('response', capture.on_response)
            except Exception:
                pass
