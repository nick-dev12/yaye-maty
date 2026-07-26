"""
Simulation de comportement humain pour limiter la détection anti-bot.
"""

from __future__ import annotations

import random

from playwright.sync_api import Page

from intelligence.scrapers.constants import (
    SCROLL_ITERATIONS_MAX,
    SCROLL_ITERATIONS_MIN,
    SCROLL_MAX_PX,
    SCROLL_MIN_PX,
    SLEEP_MAX_SECONDS,
    SLEEP_MIN_SECONDS,
)
from intelligence.services.collection_abort import interruptible_sleep


def random_sleep(min_seconds: float = SLEEP_MIN_SECONDS, max_seconds: float = SLEEP_MAX_SECONDS) -> None:
    """Pause aléatoire entre deux actions, annulable si un arrêt est demandé."""
    interruptible_sleep(random.uniform(min_seconds, max_seconds))


def organic_scroll(page: Page, *, iterations: int | None = None) -> None:
    """
    Scroll progressif avec pauses variables, comme un utilisateur réel.
    """
    count = iterations or random.randint(SCROLL_ITERATIONS_MIN, SCROLL_ITERATIONS_MAX)

    for _ in range(count):
        delta_y = random.randint(SCROLL_MIN_PX, SCROLL_MAX_PX)
        page.mouse.wheel(0, delta_y)
        random_sleep(0.8, 2.5)


def subtle_mouse_movement(page: Page) -> None:
    """Micro-mouvements de souris pour éviter un curseur figé."""
    viewport = page.viewport_size or {'width': 1280, 'height': 720}
    x = random.randint(80, max(120, viewport['width'] - 80))
    y = random.randint(80, max(120, viewport['height'] - 80))
    page.mouse.move(x, y, steps=random.randint(8, 18))
    random_sleep(0.3, 1.0)
