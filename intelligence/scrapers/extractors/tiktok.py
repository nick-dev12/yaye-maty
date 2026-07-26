"""
Extracteur TikTok — hashtags, recherches et métriques d'engagement Sénégal.

Extrait : description, auteur, URL, vues/likes/partages/favoris, commentaires.
"""

from __future__ import annotations

import logging
import re

from playwright.sync_api import Locator, Page

from intelligence.scrapers.engagement_utils import (
    compute_demand_score,
    count_purchase_intents,
    extract_hashtags,
    parse_metric_value,
)
from intelligence.scrapers.extractors.base import ExtractedPost
from intelligence.scrapers.extractors.tiktok_comment_extractor import (
    TikTokCommentCapture,
    harvest_video_comments,
)
from intelligence.scrapers.extractors.tiktok_page_json import (
    extract_video_data_from_page,
    parse_relative_french_date,
)
from intelligence.scrapers.post_id_utils import extract_post_id
from intelligence.scrapers.human_behavior import organic_scroll, random_sleep
from intelligence.scrapers.tiktok_scrape_schema import MIN_COMMENTS_PER_VIDEO

logger = logging.getLogger(__name__)

TEXT_SELECTORS = [
    '[data-e2e="search-card-desc"]',
    '[data-e2e="challenge-item-desc"]',
    '[data-e2e="browse-video-desc"]',
    '[data-e2e="video-desc"]',
    '[data-e2e="search-card-user-unique-id"]',
]

LINK_SELECTORS = [
    'a[href*="/video/"]',
]

METRIC_SELECTORS = [
    '[data-e2e="video-views"]',
    '[data-e2e="browse-like-count"]',
    '[data-e2e="like-count"]',
    '[data-e2e="share-count"]',
    '[data-e2e="undefined-count"]',
    'strong',
    'span',
]

COMMENT_TIME_SELECTORS = [
    '[data-e2e="comment-time"]',
    'time',
]

COMMENT_SELECTORS = [
    '[data-e2e="comment-level-1"]',
    '[data-e2e="comment-item"]',
    '[class*="CommentItem"]',
]

DATE_SELECTORS = [
    '[data-e2e="browser-nickname"] + span',
    '[data-e2e="video-create-time"]',
    '[data-e2e="browse-video-desc"] + span',
    'span[data-e2e="video-create-time"]',
    'time[datetime]',
]

ACTION_METRIC_SELECTORS = [
    ('like_count', '[data-e2e="like-count"], [data-e2e="browse-like-count"]'),
    ('share_count', '[data-e2e="share-count"]'),
    ('save_count', '[data-e2e="undefined-count"], [data-e2e="collect-count"]'),
    ('comment_count', '[data-e2e="comment-count"], [data-e2e="video-comment-count"]'),
    ('view_count', '[data-e2e="video-views"], [data-e2e="browse-video-views"]'),
]

NOISE_TOKENS = (
    'Voir plus', 'Voir moins', 'Suivre', "J'aime", 'Partager', 'Favoris',
    'Commentaires', 'Répondre', 'Original sound',
)


class TikTokExtractor:
    """Extrait publications TikTok avec métriques et commentaires."""

    def extract(self, page: Page, *, max_posts: int = 20) -> list[ExtractedPost]:
        organic_scroll(page, iterations=5)
        random_sleep(1.5, 2.5)

        posts = self._extract_from_video_links(page, max_posts=max_posts)

        if len(posts) < max_posts // 2:
            posts.extend(self._extract_from_text_selectors(page, max_posts=max_posts, existing=posts))

        for post in posts:
            post.metadata['demand_score'] = compute_demand_score(
                views=post.view_count,
                likes=post.like_count,
                shares=post.share_count,
                saves=post.save_count,
                comment_count=post.comment_count,
                purchase_intent_count=count_purchase_intents(post.comments),
            )

        logger.info('TikTok : %s publication(s) extraite(s).', len(posts))
        return posts[:max_posts]

    def harvest_search_video_urls(
        self,
        page: Page,
        search_url: str,
        *,
        max_urls: int = 15,
        skip_post_ids: set[str] | None = None,
        prefer_recent: bool = False,
    ) -> list[str]:
        """
        Phase 1 Top-Down — récolte les URLs vidéo depuis une recherche TikTok.

        Si prefer_recent=True, tente le tri « Plus récentes » pour privilégier le nouveau contenu.
        skip_post_ids : IDs déjà en base — ignorés pour ne pas revisiter les mêmes vidéos.
        """
        skip_post_ids = skip_post_ids or set()
        logger.info('Phase 1 — récolte URLs : %s', search_url)
        page.goto(search_url, wait_until='domcontentloaded', timeout=60_000)
        random_sleep(3.0, 5.0)

        try:
            video_tab = page.locator('[data-e2e="search_video-tab"], a[href*="search/video"]').first
            if video_tab.count():
                video_tab.click(timeout=3_000)
                random_sleep(1.5, 2.5)
        except Exception:
            pass

        if prefer_recent:
            self._activate_recent_search_sort(page)

        urls: list[str] = []
        seen: set[str] = set()
        max_scroll_rounds = 10

        for _round in range(max_scroll_rounds):
            if len(urls) >= max_urls:
                break

            for selector in LINK_SELECTORS:
                locator = page.locator(selector)
                count = min(locator.count(), max_urls * 4)

                for index in range(count):
                    if len(urls) >= max_urls:
                        break
                    try:
                        href = locator.nth(index).get_attribute('href') or ''
                        post_url = self._normalize_url(href)
                        if '/video/' not in post_url or post_url in seen:
                            continue
                        post_id = extract_post_id('tiktok', post_url)
                        if post_id and post_id in skip_post_ids:
                            continue
                        seen.add(post_url)
                        urls.append(post_url)
                    except Exception:
                        continue

            if len(urls) >= max_urls:
                break
            organic_scroll(page, iterations=1)
            random_sleep(1.0, 2.5)

        logger.info('Phase 1 — %s URL(s) vidéo nouvelle(s) collectée(s).', len(urls))
        return urls[:max_urls]

    def _activate_recent_search_sort(self, page: Page) -> None:
        """Tente d'activer le tri par date (publications récentes) sur la recherche TikTok."""
        selectors = (
            '[data-e2e="search-time-tab"]',
            'button:has-text("Plus récent")',
            'button:has-text("Recent")',
            'span:has-text("Plus récent")',
        )
        for selector in selectors:
            try:
                tab = page.locator(selector).first
                if tab.count():
                    tab.click(timeout=3_000)
                    random_sleep(1.5, 3.0)
                    logger.info('Recherche TikTok — tri « récentes » activé.')
                    return
            except Exception:
                continue

    def extract_video_detail(
        self,
        page: Page,
        video_url: str,
        *,
        max_comments: int = 20,
    ) -> ExtractedPost | None:
        """
        Phase 2 Top-Down — extraction profonde d'une vidéo (métriques + commentaires).
        """
        try:
            post_id = extract_post_id('tiktok', video_url)
            capture = TikTokCommentCapture(post_id=post_id)
            page.on('response', capture.on_response)

            try:
                page.goto(video_url, wait_until='domcontentloaded', timeout=45_000)
                random_sleep(2.0, 4.0)
                organic_scroll(page, iterations=2)

                metrics = self._extract_video_page_metrics(page, post_id=post_id)
                content = metrics.get('content', '')
                if not content:
                    return None

                comments = harvest_video_comments(
                    page,
                    post_id=post_id,
                    max_comments=max_comments,
                    capture=capture,
                )
            finally:
                try:
                    page.remove_listener('response', capture.on_response)
                except Exception:
                    pass

            post = ExtractedPost(
                content=content,
                author=metrics.get('author', self._author_from_url(video_url)),
                post_url=video_url,
                platform_post_id=post_id,
                hashtags=extract_hashtags(content),
                view_count=metrics.get('view_count'),
                like_count=metrics.get('like_count'),
                share_count=metrics.get('share_count'),
                save_count=metrics.get('save_count'),
                comment_count=metrics.get('comment_count') or len(comments),
                published_at=metrics.get('published_at', ''),
                comments=comments,
            )
            post.metadata['demand_score'] = compute_demand_score(
                views=post.view_count,
                likes=post.like_count,
                shares=post.share_count,
                saves=post.save_count,
                comment_count=post.comment_count,
                purchase_intent_count=count_purchase_intents(comments),
            )
            post.metadata['scrape_strategy'] = 'search_top_down'
            return post

        except Exception as exc:
            logger.debug('Extraction vidéo ignorée %s : %s', video_url, exc)
            return None

    def enrich_with_comments(
        self,
        page: Page,
        posts: list[ExtractedPost],
        *,
        max_posts: int = 5,
        max_comments: int = 20,
    ) -> None:
        """Visite les pages vidéo pour extraire les commentaires (intention d'achat)."""
        enriched = 0

        for post in posts:
            if enriched >= max_posts or not post.post_url:
                break
            if post.comments and len(post.comments) >= MIN_COMMENTS_PER_VIDEO:
                continue

            try:
                post_id = post.platform_post_id or extract_post_id('tiktok', post.post_url)
                capture = TikTokCommentCapture(post_id=post_id)
                page.on('response', capture.on_response)

                try:
                    page.goto(post.post_url, wait_until='domcontentloaded', timeout=45_000)
                    random_sleep(2.0, 4.0)
                    organic_scroll(page, iterations=2)

                    comments = harvest_video_comments(
                        page,
                        post_id=post_id,
                        max_comments=max_comments,
                        capture=capture,
                    )
                    metrics = self._extract_video_page_metrics(
                        page,
                        post_id=post_id,
                    )
                finally:
                    try:
                        page.remove_listener('response', capture.on_response)
                    except Exception:
                        pass

                if comments:
                    post.comments = comments
                self._apply_metrics_to_post(post, metrics)
                if metrics.get('content') and len(metrics['content']) > len(post.content):
                    post.content = metrics['content']
                if metrics.get('author') and not post.author:
                    post.author = metrics['author']
                if metrics.get('published_at') and not post.published_at:
                    post.published_at = metrics['published_at']
                if metrics.get('content'):
                    post.hashtags = extract_hashtags(metrics['content'])

                post.metadata['demand_score'] = compute_demand_score(
                    views=post.view_count,
                    likes=post.like_count,
                    shares=post.share_count,
                    saves=post.save_count,
                    comment_count=post.comment_count or len(post.comments),
                    purchase_intent_count=count_purchase_intents(post.comments),
                )
                enriched += 1
                random_sleep(1.5, 3.0)

            except Exception as exc:
                logger.debug('Commentaires ignorés pour %s : %s', post.post_url, exc)

    def _extract_from_video_links(self, page: Page, *, max_posts: int) -> list[ExtractedPost]:
        posts: list[ExtractedPost] = []
        seen_urls: set[str] = set()

        for selector in LINK_SELECTORS:
            locator = page.locator(selector)
            count = min(locator.count(), max_posts * 3)

            for index in range(count):
                if len(posts) >= max_posts:
                    break

                try:
                    element = locator.nth(index)
                    href = element.get_attribute('href') or ''
                    post_url = self._normalize_url(href)
                    if not post_url or post_url in seen_urls:
                        continue

                    seen_urls.add(post_url)
                    author = self._author_from_url(post_url)
                    content = self._extract_card_content(element)
                    metrics = self._extract_card_metrics(element)

                    if not content:
                        aria = self._clean_text(element.get_attribute('aria-label') or '')
                        content = aria

                    if not content or len(content) < 8:
                        continue

                    posts.append(self._build_post(
                        content=content,
                        post_url=post_url,
                        author=author,
                        metrics=metrics,
                    ))
                except Exception as exc:
                    logger.debug('Lien TikTok[%s] ignoré : %s', index, exc)

        return posts

    def _extract_from_text_selectors(
        self,
        page: Page,
        *,
        max_posts: int,
        existing: list[ExtractedPost],
    ) -> list[ExtractedPost]:
        posts: list[ExtractedPost] = []
        seen_texts = {item.content for item in existing}

        for selector in TEXT_SELECTORS:
            if len(existing) + len(posts) >= max_posts:
                break

            locator = page.locator(selector)
            count = min(locator.count(), max_posts)

            for index in range(count):
                try:
                    element = locator.nth(index)
                    text = self._clean_text(element.inner_text(timeout=2_000))
                    if not text or text in seen_texts:
                        continue

                    post_url = self._find_nearby_link(element)
                    seen_texts.add(text)
                    posts.append(self._build_post(
                        content=text,
                        post_url=post_url,
                        author=self._author_from_url(post_url),
                    ))
                except Exception:
                    continue

        return posts

    def _extract_card_content(self, element: Locator) -> str:
        for selector in TEXT_SELECTORS:
            try:
                nested = element.locator(selector).first
                if nested.count():
                    text = self._clean_text(nested.inner_text(timeout=1_000))
                    if text:
                        return text
            except Exception:
                continue

        try:
            container = element.locator('xpath=ancestor::div[contains(@class,"DivItem")][1]').first
            text = self._clean_text(container.inner_text(timeout=1_500))
            return self._strip_metrics_from_text(text)
        except Exception:
            return ''

    def _extract_card_metrics(self, element: Locator) -> dict[str, int | None]:
        metrics: dict[str, int | None] = {}

        try:
            container = element.locator('xpath=ancestor::div[1]').first
            blob = self._clean_text(container.inner_text(timeout=1_500))
            metrics.update(self._parse_metrics_blob(blob))
        except Exception:
            pass

        aria = element.get_attribute('aria-label') or ''
        if aria:
            metrics.update(self._parse_metrics_blob(aria))

        return metrics

    def _extract_video_page_metrics(self, page: Page, *, post_id: str = '') -> dict:
        result: dict = dict(extract_video_data_from_page(page, post_id=post_id))

        for selector in TEXT_SELECTORS:
            if result.get('content'):
                break
            try:
                text = self._clean_text(page.locator(selector).first.inner_text(timeout=2_000))
                if text:
                    result['content'] = text
                    break
            except Exception:
                continue

        if not result.get('author'):
            try:
                author = self._clean_text(
                    page.locator('[data-e2e="browse-username"], [data-e2e="video-author-uniqueid"]').first.inner_text(timeout=1_500)
                )
                if author:
                    result['author'] = author.lstrip('@')
            except Exception:
                pass

        dom_metrics = self._extract_dom_metrics(page)
        for field, value in dom_metrics.items():
            if result.get(field) is None and value is not None:
                result[field] = value

        if not result.get('published_at'):
            result['published_at'] = self._extract_page_datetime(page)

        return result

    def _extract_dom_metrics(self, page: Page) -> dict[str, int | None]:
        metrics: dict[str, int | None] = {}

        for field, selector_group in ACTION_METRIC_SELECTORS:
            if metrics.get(field) is not None:
                continue
            for selector in selector_group.split(', '):
                try:
                    locator = page.locator(selector.strip()).first
                    if not locator.count():
                        continue
                    text = self._clean_text(locator.inner_text(timeout=800))
                    value = parse_metric_value(text)
                    if value is not None:
                        metrics[field] = value
                        break
                    aria = locator.get_attribute('aria-label') or ''
                    if aria:
                        parsed = self._parse_metrics_blob(aria)
                        if parsed.get(field) is not None:
                            metrics[field] = parsed[field]
                            break
                except Exception:
                    continue

        blob_parts: list[str] = []
        for selector in METRIC_SELECTORS:
            try:
                locator = page.locator(selector)
                count = min(locator.count(), 12)
                for idx in range(count):
                    element = locator.nth(idx)
                    part = self._clean_text(element.inner_text(timeout=800))
                    if part:
                        blob_parts.append(part)
                    aria = element.get_attribute('aria-label') or ''
                    if aria:
                        blob_parts.append(aria)
            except Exception:
                continue

        for field, value in self._parse_metrics_blob(' '.join(blob_parts)).items():
            if metrics.get(field) is None and value is not None:
                metrics[field] = value

        return metrics

    @staticmethod
    def _apply_metrics_to_post(post: ExtractedPost, metrics: dict) -> None:
        """Fusionne les métriques extraites dans un ExtractedPost (sans écraser les valeurs existantes)."""
        field_map = (
            'view_count', 'like_count', 'share_count', 'save_count', 'comment_count',
        )
        for field in field_map:
            value = metrics.get(field)
            if value is not None and getattr(post, field) is None:
                setattr(post, field, value)

    def _extract_comments(self, page: Page, *, max_comments: int, post_id: str = '') -> list[dict]:
        """Délègue au module commentaires (API + DOM + JSON embarqué)."""
        return harvest_video_comments(page, post_id=post_id, max_comments=max_comments)

    def _build_post(
        self,
        *,
        content: str,
        post_url: str,
        author: str = '',
        metrics: dict | None = None,
    ) -> ExtractedPost:
        metrics = metrics or {}
        platform_post_id = extract_post_id('tiktok', post_url)
        return ExtractedPost(
            content=content,
            author=author,
            post_url=post_url,
            platform_post_id=platform_post_id,
            hashtags=extract_hashtags(content),
            view_count=metrics.get('view_count'),
            like_count=metrics.get('like_count'),
            share_count=metrics.get('share_count'),
            save_count=metrics.get('save_count'),
            comment_count=metrics.get('comment_count'),
        )

    def _extract_page_datetime(self, page: Page) -> str:
        for selector in DATE_SELECTORS:
            try:
                element = page.locator(selector).first
                if not element.count():
                    continue
                datetime_value = element.get_attribute('datetime')
                if datetime_value:
                    return datetime_value
                text = self._clean_text(element.inner_text(timeout=800))
                relative = parse_relative_french_date(text)
                if relative:
                    return relative
            except Exception:
                continue
        return ''

    def _extract_comment_datetime(self, element: Locator) -> str:
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

    def _parse_metrics_blob(self, blob: str) -> dict[str, int | None]:
        metrics: dict[str, int | None] = {}
        lowered = blob.lower()

        patterns = {
            'view_count': (r'([\d.,]+\s*[km]?)\s*(?:vues?|views?|lectures?)', r'(?:vues?|views?)\s*([\d.,]+\s*[km]?)'),
            'like_count': (r'([\d.,]+\s*[km]?)\s*(?:likes?|j\'?aime)', r'(?:likes?|j\'?aime)\s*([\d.,]+\s*[km]?)'),
            'share_count': (r'([\d.,]+\s*[km]?)\s*(?:partages?|shares?)', r'(?:partages?|shares?)\s*([\d.,]+\s*[km]?)'),
            'save_count': (r'([\d.,]+\s*[km]?)\s*(?:favoris|saves?|enregistrements?)',),
            'comment_count': (r'([\d.,]+\s*[km]?)\s*(?:commentaires?|comments?)',),
        }

        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, lowered)
                if match:
                    value = parse_metric_value(match.group(1))
                    if value is not None:
                        metrics[field] = value
                        break

        if not metrics.get('view_count'):
            standalone = re.findall(r'\b([\d.,]+\s*[km]?)\b', lowered)
            for token in standalone:
                value = parse_metric_value(token)
                if value and value > 100:
                    metrics['view_count'] = value
                    break

        return metrics

    @staticmethod
    def _author_from_url(url: str) -> str:
        match = re.search(r'tiktok\.com/@([^/?#]+)', url or '')
        return match.group(1) if match else ''

    @staticmethod
    def _normalize_url(href: str) -> str:
        if not href:
            return ''
        return href if href.startswith('http') else f'https://www.tiktok.com{href}'

    @staticmethod
    def _find_nearby_link(element: Locator) -> str:
        try:
            link = element.locator('xpath=ancestor::a[1]').first
            href = link.get_attribute('href', timeout=1_000)
            if href:
                return href if href.startswith('http') else f'https://www.tiktok.com{href}'
        except Exception:
            pass
        return ''

    @staticmethod
    def _strip_metrics_from_text(text: str) -> str:
        cleaned = re.sub(r'\b[\d.,]+\s*[kmKMB]?\b', ' ', text)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned[:500]

    @staticmethod
    def _strip_comment_noise(text: str) -> str:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        filtered = [line for line in lines if line not in NOISE_TOKENS and len(line) > 2]
        return ' '.join(filtered[:3])

    @staticmethod
    def _clean_text(value: str) -> str:
        text = re.sub(r'\s+', ' ', value or '').strip()
        for item in NOISE_TOKENS:
            text = text.replace(item, '')
        return text.strip()
