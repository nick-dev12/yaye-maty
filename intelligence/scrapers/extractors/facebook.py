"""
Extracteur Facebook — groupes et pages publiques.

Nécessite une session connectée pour la plupart des groupes.
"""

from __future__ import annotations

import logging
import re

from playwright.sync_api import Page

from intelligence.scrapers.extractors.base import ExtractedPost
from intelligence.scrapers.human_behavior import organic_scroll, random_sleep

logger = logging.getLogger(__name__)

TEXT_SELECTORS = [
    '[data-ad-preview="message"]',
    '[data-ad-comet-preview="message"]',
    'div[data-ad-rendering-role="story_message"]',
]

AUTHOR_SELECTORS = [
    'a[role="link"] strong',
    'h2 a',
    'span[dir="auto"] strong',
]


class FacebookExtractor:
    """Extrait les textes de publications visibles sur Facebook."""

    def extract(self, page: Page, *, max_posts: int = 20) -> list[ExtractedPost]:
        organic_scroll(page, iterations=5)
        random_sleep(1.5, 3.0)

        posts: list[ExtractedPost] = []
        seen_texts: set[str] = set()

        for selector in TEXT_SELECTORS:
            if len(posts) >= max_posts:
                break

            locator = page.locator(selector)
            count = min(locator.count(), max_posts - len(posts))

            for index in range(count):
                try:
                    element = locator.nth(index)
                    text = self._clean_text(element.inner_text(timeout=2_000))
                    if not text or text in seen_texts or len(text) < 20:
                        continue

                    author = self._extract_author(element)
                    post_url = self._find_post_link(element)
                    seen_texts.add(text)
                    posts.append(
                        ExtractedPost(content=text, author=author, post_url=post_url)
                    )
                except Exception as exc:
                    logger.debug('Facebook selector %s[%s] ignoré : %s', selector, index, exc)

        if not posts:
            posts = self._fallback_articles(page, max_posts=max_posts)

        logger.info('Facebook : %s publication(s) extraite(s).', len(posts))
        return posts[:max_posts]

    def _fallback_articles(self, page: Page, *, max_posts: int) -> list[ExtractedPost]:
        """Parcourt les articles visibles si les sélecteurs dédiés échouent."""
        results: list[ExtractedPost] = []
        seen: set[str] = set()
        articles = page.locator('[role="article"]')
        count = min(articles.count(), max_posts * 2)

        for index in range(count):
            try:
                article = articles.nth(index)
                paragraphs = article.locator('div[dir="auto"]')
                parts = []

                for p_index in range(min(paragraphs.count(), 4)):
                    chunk = self._clean_text(paragraphs.nth(p_index).inner_text(timeout=1_000))
                    if chunk and len(chunk) > 15:
                        parts.append(chunk)

                text = ' '.join(parts).strip()
                if not text or text in seen or len(text) < 30:
                    continue

                seen.add(text)
                results.append(ExtractedPost(content=text[:2000]))
            except Exception:
                continue

            if len(results) >= max_posts:
                break

        return results

    @staticmethod
    def _extract_author(element) -> str:
        try:
            article = element.locator('xpath=ancestor::*[@role="article"][1]')
            for selector in AUTHOR_SELECTORS:
                author_loc = article.locator(selector).first
                if author_loc.count() > 0:
                    author = author_loc.inner_text(timeout=800).strip()
                    if author:
                        return author[:120]
        except Exception:
            pass
        return ''

    @staticmethod
    def _find_post_link(element) -> str:
        try:
            link = element.locator('xpath=ancestor::a[contains(@href, "/posts/")][1]').first
            href = link.get_attribute('href', timeout=800)
            if href:
                return href if href.startswith('http') else f'https://www.facebook.com{href}'
        except Exception:
            pass
        return ''

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r'\s+', ' ', value or '').strip()
