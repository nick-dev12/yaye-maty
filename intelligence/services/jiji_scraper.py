"""
Scraper Jiji Sénégal — listings catégories + fiches annonces.

- User-Agent identifié, délais aléatoires
- Catégories en priorité (évite la surcharge search)
- Recherche ``/search?query=`` autorisée pour User-agent * (interdite à Bingbot)
- Playwright : scroll / « Charger plus » + révélation contact optionnelle (désactivée par défaut)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from lxml import html as lxml_html

from intelligence.models.jiji_listing import JijiListing

logger = logging.getLogger(__name__)

BASE_URL = 'https://jiji.sn'
USER_AGENT = (
    'YayematyMarketBot/1.0 (+https://yayematy.local/contact; market-intelligence; respectful)'
)

KEYWORD_CATEGORY_PATHS: dict[str, str] = {
    # Téléphones & tech
    'iphone': '/mobile-phones-tablets',
    'telephone': '/mobile-phones-tablets',
    'smartphone': '/mobile-phones-tablets',
    'samsung': '/mobile-phones-tablets',
    'xiaomi': '/mobile-phones-tablets',
    'tecno': '/mobile-phones-tablets',
    'infinix': '/mobile-phones-tablets',
    'tablette': '/mobile-phones-tablets',
    'ecouteur': '/electronics',
    'chargeur': '/electronics',
    'accessoire telephone': '/mobile-phones-tablets',
    'telephone et accessoir': '/mobile-phones-tablets',
    # TV & électro
    'television': '/electronics',
    'tv': '/electronics',
    'televiseur': '/electronics',
    'climatiseur': '/electronics',
    'ventilateur': '/electronics',
    'electromenager': '/home-appliances',
    'refrigerateur': '/home-appliances',
    'micro onde': '/home-appliances',
    # Informatique
    'ordinateur': '/computer-accessories',
    'laptop': '/computer-accessories',
    'pc': '/computer-accessories',
    # Mode
    'chaussure': '/clothing',
    'vetement': '/clothing',
    'sac': '/clothing',
    # Agricole / jardin (si mot-clé le demande)
    'motopompe': '/farm-machinery-equipment',
    'pompe': '/farm-machinery-equipment',
    'pompe solaire': '/solar-energy-products',
    'pompe immergee': '/farm-machinery-equipment',
    'pompes immergees': '/farm-machinery-equipment',
    'irrigation': '/farm-machinery-equipment',
    'goutte a goutte': '/farm-machinery-equipment',
    'pulverisateur': '/farm-machinery-equipment',
    'pulvérisateur': '/farm-machinery-equipment',
    'brouette': '/farm-machinery-equipment',
    'tronconneuse': '/farm-machinery-equipment',
    'couveuse': '/farm-machinery-equipment',
    'tracteur': '/farm-machinery-equipment',
    'motoculteur': '/farm-machinery-equipment',
    'engrais': '/agriculture-and-foodstuff',
    'semence': '/agriculture-and-foodstuff',
    'materiel agricole': '/farm-machinery-equipment',
    'jardin': '/farm-machinery-equipment',
    # Beauté / supermarché
    'parfum': '/health-beauty',
    'cosmetique': '/health-beauty',
    'beaute': '/health-beauty',
    'supermarche': '/meals-drink',
}

CHALLENGE_MARKERS = (
    'cf-challenge',
    'challenge-platform',
    'just a moment',
    'verify you are human',
    'attention required',
)

ShouldCancel = Callable[[], bool]


@dataclass
class ExtractedJijiListing:
    listing_id: str
    listing_url: str
    title: str
    category: str = ''
    price_xof: Decimal | None = None
    is_negotiable: bool = False
    condition: str = JijiListing.Condition.UNKNOWN
    location_region: str = ''
    location_area: str = ''
    views_count: int = 0
    seller_name: str = ''
    seller_member_since: str = ''
    seller_is_verified: bool = False
    seller_is_premium: bool = False
    seller_response_stat: str = ''
    seller_ads_count: int | None = None
    search_keyword: str = ''
    catalog_product_slug: str = ''
    description: str = ''
    image_url: str = ''
    attributes: dict = field(default_factory=dict)
    phone_revealed: bool = False


class JijiScraperError(Exception):
    """Erreur récupérable du scraper Jiji."""


class JijiScraper:
    """Client Jiji — requests/lxml + Playwright (scroll / contact optionnel)."""

    def __init__(
        self,
        *,
        delay_min: float = 1.5,
        delay_max: float = 3.5,
        timeout: float = 35.0,
        should_cancel: ShouldCancel | None = None,
        use_playwright: bool = True,
        reveal_contacts: bool = False,
        max_scroll_rounds: int = 6,
    ):
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.timeout = timeout
        self.should_cancel = should_cancel
        self.use_playwright = use_playwright
        self.reveal_contacts = reveal_contacts
        self.max_scroll_rounds = max_scroll_rounds
        self.request_count = 0
        self.playwright_fetches = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept-Language': 'fr-FR,fr;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        self._pw_bundle = None
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._pw_bundle is not None:
            try:
                self._pw_bundle.close()
            except Exception:
                logger.exception('Fermeture Playwright Jiji')
            self._pw_bundle = None
        self.session.close()

    # ------------------------------------------------------------------ public

    @staticmethod
    def resolve_category_path(keyword: str, product_category: str = '') -> str:
        from intelligence.services.marketplace_catalog_utils import resolve_jiji_category_path

        return resolve_jiji_category_path(keyword, product_category=product_category)

    def search_listing_urls(
        self,
        keyword: str,
        *,
        product_category: str = '',
        max_products: int = 8,
        known_ids: set[str] | None = None,
        known_urls: set[str] | None = None,
        skip_known: bool = True,
        search_first: bool = True,
        listing_page_offset: int = 1,
    ) -> list[dict]:
        """
        Collecte des cartes annonces — recherche prioritaire, puis catégorie.

        Si ``skip_known`` : ne retient que les annonces absentes de la base.
        """
        from intelligence.services.jiji_dedup_service import JijiDedupService

        path = self.resolve_category_path(keyword, product_category=product_category)
        known_ids = known_ids or set()
        known_urls = known_urls or set()
        cards: list[dict] = []
        seen: set[str] = set()

        def _merge(page_cards: list[dict]) -> None:
            for card in page_cards:
                url = card.get('url') or ''
                if url and url not in seen:
                    seen.add(url)
                    cards.append(card)

        # 1) Recherche directe (plus précise pour le mot-clé)
        if search_first and keyword.strip():
            q = quote_plus(keyword.strip())
            page = max(1, int(listing_page_offset or 1))
            search_path = f'/search?query={q}' if page <= 1 else f'/search?query={q}&page={page}'
            try:
                html = self._get(search_path, card_fallback=True)
                _merge(self._parse_listing_cards(html))
                if self.use_playwright and len(cards) < max_products * 2:
                    try:
                        more = self._playwright_load_more(
                            urljoin(BASE_URL, search_path),
                            max_products=max_products * 3,
                        )
                        _merge(more)
                    except Exception:
                        logger.exception('Scroll search Jiji échoué pour %r', keyword)
            except JijiScraperError:
                logger.info('Search Jiji indisponible pour %r', keyword)

        # 2) Catégorie + scroll
        if path and len(cards) < max_products:
            try:
                html = self._get(path, card_fallback=True)
                _merge(self._parse_listing_cards(html))
                if self.use_playwright:
                    try:
                        more = self._playwright_load_more(
                            urljoin(BASE_URL, path),
                            max_products=max_products * 3,
                        )
                        _merge(more)
                    except Exception:
                        logger.exception('Scroll catégorie Jiji échoué sur %s', path)
            except JijiScraperError:
                logger.info('Catégorie Jiji indisponible %s pour %r', path, keyword)

        # 3) Repli search si catégorie seule insuffisante
        if not search_first and len(cards) < max(1, max_products // 2) and keyword.strip():
            q = quote_plus(keyword.strip())
            try:
                html = self._get(f'/search?query={q}', card_fallback=True)
                _merge(self._parse_listing_cards(html))
            except JijiScraperError:
                pass

        filtered = self._filter_cards_by_keyword(cards, keyword)
        pool = filtered if filtered else cards

        if skip_known:
            chosen, skipped = JijiDedupService.filter_new_cards(
                pool,
                known_ids=known_ids,
                known_urls=known_urls,
                limit=max_products,
            )
            logger.info(
                'Jiji listing %r via %s/search → %d carte(s), %d nouvelles, %d ignorées',
                keyword, path or '—', len(pool), len(chosen), skipped,
            )
            return chosen

        stop = {'et', 'de', 'du', 'la', 'le', 'les', 'des', 'un', 'une', 'pour', 'avec'}
        tokens = [
            t for t in self._normalize_needle(keyword).split()
            if len(t) >= 2 and t not in stop
        ]
        if filtered:
            chosen = filtered[:max_products]
        else:
            chosen = [] if len(tokens) >= 2 else cards[:max_products]
        logger.info(
            'Jiji listing %r via %s → %d carte(s), %d retenues',
            keyword, path or 'search', len(cards), len(chosen),
        )
        return chosen

    def fetch_homepage_cards(self) -> list[dict]:
        """Parse les annonces Trending de la page d'accueil Jiji."""
        html = self._get('/', card_fallback=True)
        return self._parse_listing_cards(html, source='trending')

    def filter_cards_by_keyword(self, cards: list[dict], keyword: str) -> list[dict]:
        return self._filter_cards_by_keyword(cards, keyword)

    def fetch_listing(
        self,
        listing_url: str,
        *,
        keyword: str = '',
        product_category: str = '',
    ) -> ExtractedJijiListing | None:
        html = self._get(listing_url)
        extracted = self._parse_listing_page(html, listing_url)
        if not extracted and self.use_playwright:
            full_url = listing_url if listing_url.startswith('http') else urljoin(BASE_URL, listing_url)
            logger.info('Fiche Jiji illisible en HTTP — repli Playwright sur %s', full_url)
            html = self._get_playwright(full_url)
            extracted = self._parse_listing_page(html, listing_url)
        if not extracted:
            return None
        extracted.search_keyword = keyword
        from intelligence.services.marketplace_catalog_utils import resolve_catalog_slug

        extracted.catalog_product_slug = resolve_catalog_slug(
            extracted.title,
            keyword,
            product_category=product_category,
        )
        if self.reveal_contacts and self.use_playwright:
            try:
                revealed = self._playwright_reveal_contact(listing_url)
                if revealed:
                    extracted.phone_revealed = True
            except Exception:
                logger.exception('Révélation contact Jiji échouée')
        return extracted

    # ------------------------------------------------------------------ HTTP

    def _throttle(self) -> None:
        import random

        from intelligence.services.collection_abort import interruptible_sleep

        elapsed = time.monotonic() - self._last_request_at
        wait = random.uniform(self.delay_min, self.delay_max) - elapsed
        if wait > 0:
            interruptible_sleep(wait)

    def _check_cancel(self) -> None:
        if self.should_cancel and self.should_cancel():
            raise JijiScraperError('Collecte Jiji annulée')

    def _looks_like_challenge(self, html: str, status_code: int | None = None) -> bool:
        if status_code in (403, 429, 503):
            return True
        low = (html or '').lower()
        return any(m in low for m in CHALLENGE_MARKERS)

    def _get(self, path_or_url: str, *, card_fallback: bool = False) -> str:
        """
        Charge une page Jiji (HTTP puis repli Playwright si besoin).

        ``card_fallback`` : si le HTML HTTP ne contient aucune carte annonce,
        retente avec Playwright (pages rendues côté client sur le VPS).
        """
        self._check_cancel()
        self._throttle()
        url = path_or_url if path_or_url.startswith('http') else urljoin(BASE_URL, path_or_url)
        self.request_count += 1
        self._last_request_at = time.monotonic()
        try:
            resp = self.session.get(url, timeout=self.timeout)
            html = resp.text or ''
            if self._looks_like_challenge(html, resp.status_code):
                if self.use_playwright:
                    logger.info('Jiji challenge HTTP %s — repli Playwright sur %s', resp.status_code, url)
                    return self._get_playwright(url)
                raise JijiScraperError(f'Blocage Jiji HTTP {resp.status_code} sur {url}')
            if resp.status_code >= 400:
                if self.use_playwright:
                    logger.info('Jiji HTTP %s — repli Playwright sur %s', resp.status_code, url)
                    return self._get_playwright(url)
                raise JijiScraperError(f'HTTP {resp.status_code} sur {url}')
        except requests.RequestException as exc:
            if self.use_playwright:
                logger.warning('Requête Jiji échouée (%s) — repli Playwright sur %s', exc, url)
                return self._get_playwright(url)
            raise JijiScraperError(f'Requête Jiji échouée : {exc}') from exc
        else:
            if card_fallback and self.use_playwright and not self._parse_listing_cards(html):
                logger.info('Jiji HTTP sans cartes — repli Playwright sur %s', url)
                return self._get_playwright(url)
            return html

    def _ensure_playwright(self):
        if self._pw_bundle is not None:
            return self._pw_bundle
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise JijiScraperError('Playwright non installé') from exc

        stealth_cm = None
        try:
            from playwright_stealth import Stealth
            from intelligence.scrapers.constants import CHROMIUM_LAUNCH_ARGS, DEFAULT_VIEWPORT

            stealth = Stealth(navigator_languages_override=('fr-FR', 'fr'))
            stealth_cm = stealth.use_sync(sync_playwright())
            playwright = stealth_cm.__enter__()
            browser = playwright.chromium.launch(headless=True, args=CHROMIUM_LAUNCH_ARGS)
            viewport = DEFAULT_VIEWPORT
        except ImportError:
            from intelligence.scrapers.constants import DEFAULT_VIEWPORT

            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            viewport = DEFAULT_VIEWPORT

        context = browser.new_context(
            user_agent=USER_AGENT,
            locale='fr-FR',
            viewport=viewport,
        )
        page = context.new_page()

        class _Bundle:
            def __init__(self, pw, br, ctx, pg, stealth_context=None):
                self.playwright = pw
                self.browser = br
                self.context = ctx
                self.page = pg
                self.stealth_cm = stealth_context

            def close(self):
                try:
                    self.context.close()
                finally:
                    try:
                        self.browser.close()
                    finally:
                        if self.stealth_cm is not None:
                            self.stealth_cm.__exit__(None, None, None)
                        else:
                            self.playwright.stop()

        self._pw_bundle = _Bundle(playwright, browser, context, page, stealth_cm)
        return self._pw_bundle

    def _get_playwright(self, url: str) -> str:
        self._check_cancel()
        self._throttle()
        bundle = self._ensure_playwright()
        self.request_count += 1
        self.playwright_fetches += 1
        page = bundle.page
        page.goto(url, wait_until='domcontentloaded', timeout=int(self.timeout * 1000))
        try:
            page.wait_for_selector('a.qa-advert-list-item, .qa-advert-title', timeout=8000)
        except Exception:
            try:
                page.wait_for_timeout(1800)
            except Exception:
                pass
        html = page.content()
        if self._looks_like_challenge(html):
            raise JijiScraperError(f'Challenge anti-bot persistant (Playwright) sur {url}')
        return html

    def _playwright_load_more(self, url: str, *, max_products: int) -> list[dict]:
        bundle = self._ensure_playwright()
        page = bundle.page
        self.playwright_fetches += 1
        page.goto(url, wait_until='domcontentloaded', timeout=int(self.timeout * 1000))
        cards: list[dict] = []
        seen: set[str] = set()
        for _ in range(self.max_scroll_rounds):
            self._check_cancel()
            html = page.content()
            for card in self._parse_listing_cards(html):
                u = card.get('url') or ''
                if u and u not in seen:
                    seen.add(u)
                    cards.append(card)
            if len(cards) >= max_products:
                break
            # Bouton « Charger plus » ou scroll
            clicked = False
            for sel in [
                'button:has-text("Charger plus")',
                'button:has-text("Voir plus")',
                'a:has-text("Charger plus")',
                '.qa-load-more',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() and btn.is_visible():
                        btn.click(timeout=2000)
                        page.wait_for_timeout(1500)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                page.wait_for_timeout(1400)
        return cards

    def _playwright_reveal_contact(self, url: str) -> bool:
        """Clique « Montrer contact » — à utiliser avec parcimonie (quotas Jiji)."""
        bundle = self._ensure_playwright()
        page = bundle.page
        self.playwright_fetches += 1
        page.goto(url, wait_until='domcontentloaded', timeout=int(self.timeout * 1000))
        for sel in ['.qa-show-contact', 'button:has-text("Montrer contact")', 'a:has-text("Montrer contact")']:
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_visible():
                    btn.click(timeout=2500)
                    page.wait_for_timeout(1200)
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------ parse

    def _parse_listing_cards(self, html: str, *, source: str = 'listing') -> list[dict]:
        from intelligence.services.jiji_dedup_service import JijiDedupService

        tree = lxml_html.fromstring(html)
        cards = []
        for art in tree.xpath('//a[contains(@class,"qa-advert-list-item")]'):
            href = art.get('href') or ''
            title_el = art.xpath('.//*[contains(@class,"qa-advert-title")]')
            price_el = art.xpath('.//*[contains(@class,"qa-advert-price")]')
            loc_el = art.xpath(
                './/*[contains(@class,"b-list-advert-base__location") '
                'or contains(@class,"b-list-advert__region")]'
            )
            title = (title_el[0].text_content() if title_el else '').strip()
            price = (price_el[0].text_content() if price_el else '').strip()
            loc = ' '.join((loc_el[0].text_content() if loc_el else '').split())
            raw_text = art.text_content()
            condition_label = ''
            for label in ('Brand New', 'Used', 'Refurbished', 'Neuf', 'Occasion', 'Nouveau'):
                if label.lower() in raw_text.lower():
                    condition_label = label
                    break
            if href and title:
                abs_url = urljoin(BASE_URL, href.split('?')[0])
                cards.append({
                    'url': abs_url,
                    'name': title,
                    'title': title,
                    'price': price,
                    'location': loc,
                    'condition_label': condition_label,
                    'raw_text': raw_text,
                    'section_label': source,
                    'listing_id': JijiDedupService.extract_listing_id(abs_url),
                })
        return cards

    def _parse_listing_page(self, html: str, listing_url: str) -> ExtractedJijiListing | None:
        tree = lxml_html.fromstring(html)
        title_el = tree.xpath('//*[contains(@class,"qa-advert-title")]')
        title = (title_el[0].text_content() if title_el else '').strip()
        if not title:
            h1 = tree.xpath('//h1')
            title = (h1[0].text_content() if h1 else '').strip()
        if not title:
            return None

        listing_id = self._extract_listing_id(listing_url)
        if not listing_id:
            return None

        price_el = tree.xpath('//*[contains(@class,"qa-advert-price-view-value") or contains(@class,"qa-advert-price")]')
        price_txt = (price_el[0].text_content() if price_el else '')
        price = self._parse_price(price_txt)

        price_type_el = tree.xpath('//*[contains(@class,"qa-advert-price-view-type") or contains(@class,"b-alt-advert-price__type")]')
        price_type = (price_type_el[0].text_content() if price_type_el else '').lower()
        page_text = tree.text_content()
        is_negotiable = (
            'négociable' in price_type
            or 'negociable' in price_type
            or bool(re.search(r'prix\s*négociable|prix\s*negociable', page_text, re.I))
        )
        if 'fixe' in price_type:
            is_negotiable = False

        attrs = {}
        for row in tree.xpath('//*[contains(@class,"b-advert-attribute") and contains(@class,"h-pb-5")]'):
            keys = row.xpath('.//*[contains(@class,"b-advert-attribute__key")]')
            vals = row.xpath('.//*[contains(@class,"b-advert-attribute__value")]')
            if keys and vals:
                attrs[keys[0].text_content().strip()] = vals[0].text_content().strip()

        condition = self._parse_condition(attrs.get('État') or attrs.get('Etat') or page_text)
        region, area = self._parse_location(tree, page_text)
        views = self._parse_views_count(tree, page_text)

        seller_name = ''
        name_el = tree.xpath('//*[contains(@class,"b-seller-block__name")]')
        if name_el:
            seller_name = name_el[0].text_content().strip()[:160]
        member_since = ''
        badge_el = tree.xpath('//*[contains(@class,"b-seller-badge")]')
        if badge_el:
            member_since = badge_el[0].text_content().strip()[:80]
        response_stat = ''
        stat_el = tree.xpath('//*[contains(@class,"b-seller-block__info__stat")]')
        if stat_el:
            response_stat = stat_el[0].text_content().strip()[:120]

        seller_block = ' '.join(
            el.text_content() for el in tree.xpath('//*[contains(@class,"b-seller-info-wrapper")]')
        ).lower()
        is_premium = 'premium' in seller_block
        is_verified = 'vérifié' in seller_block or 'verifie' in seller_block or 'verified' in seller_block

        desc_el = tree.xpath('//*[contains(@class,"qa-advert-description")]')
        description = (desc_el[0].text_content() if desc_el else '')[:4000].strip()

        image_url = ''
        img_el = tree.xpath('//meta[@property="og:image"]/@content')
        if img_el:
            image_url = img_el[0]
        else:
            imgs = tree.xpath('//picture//img/@src | //img[contains(@class,"advert")]/@src')
            if imgs:
                image_url = imgs[0]

        # catégorie depuis URL /breadcrumbs
        category = ''
        parts = [p for p in urlparse(listing_url).path.split('/') if p]
        if len(parts) >= 2:
            category = parts[1].replace('-', ' ')[:160]
        crumbs = tree.xpath('//nav//a')
        if crumbs:
            category = crumbs[-1].text_content().strip()[:160] or category

        abs_url = listing_url if listing_url.startswith('http') else urljoin(BASE_URL, listing_url)
        return ExtractedJijiListing(
            listing_id=listing_id,
            listing_url=abs_url.split('?')[0],
            title=title[:400],
            category=category,
            price_xof=price,
            is_negotiable=is_negotiable,
            condition=condition,
            location_region=region[:120],
            location_area=area[:120],
            views_count=views,
            seller_name=seller_name,
            seller_member_since=member_since,
            seller_is_verified=is_verified,
            seller_is_premium=is_premium,
            seller_response_stat=response_stat,
            description=description,
            image_url=(image_url or '')[:500],
            attributes=attrs,
        )

    @staticmethod
    def _parse_views_count(tree, page_text: str) -> int:
        """
        Extrait le nombre de vues depuis ``.b-advert-info-statistics`` (ex. « 20 views »)
        ou le texte page (ex. « 234 vus »). Ignore ``--region`` (date/lieu).
        """
        views_re = re.compile(r'(\d[\d\s,]*)\s*(?:views?|vus|vue\b)', re.I)
        for el in tree.xpath(
            '//*[contains(@class,"b-advert-info-statistics")'
            ' and not(contains(@class,"b-advert-info-statistics--"))]'
        ):
            txt = (el.text_content() or '').strip()
            m = views_re.search(txt)
            if m:
                val = int(re.sub(r'\D', '', m.group(1)) or 0)
                if val > 0:
                    return val
        for pattern in (
            r'(\d[\d\s,]*)\s*views?',
            r'(\d[\d\s,]*)\s*vus',
            r'(\d[\d\s,]*)\s*vue\b',
        ):
            m = re.search(pattern, page_text or '', re.I)
            if m:
                val = int(re.sub(r'\D', '', m.group(1)) or 0)
                if val > 0:
                    return val
        return 0

    def _filter_cards_by_keyword(self, cards: list[dict], keyword: str) -> list[dict]:
        needle = self._normalize_needle(keyword)
        stop = {'et', 'de', 'du', 'la', 'le', 'les', 'des', 'un', 'une', 'pour', 'avec'}
        tokens = [t for t in needle.split() if len(t) >= 2 and t not in stop]
        if not tokens:
            return list(cards)
        scored = []
        for card in cards:
            name_n = self._normalize_needle(card.get('title') or card.get('name') or '')
            hits = sum(1 for t in tokens if t in name_n)
            required = max(1, (len(tokens) + 1) // 2)
            if hits >= required:
                scored.append((hits, card))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored]

    @staticmethod
    def _extract_listing_id(url: str) -> str:
        path = urlparse(url).path
        # …-BCXxdM14MbJZbitbPnU6hfJf.html
        m = re.search(r'-([A-Za-z0-9]{10,})\.html', path)
        if m:
            return m.group(1)
        m = re.search(r'/([A-Za-z0-9_-]{12,})\.html', path)
        if m:
            return m.group(1)[-40:]
        return ''

    @staticmethod
    def _parse_condition(raw: str) -> str:
        text = (raw or '').lower()
        if 'neuf' in text or 'new' in text:
            return JijiListing.Condition.NEW
        if 'recondition' in text or 'refurb' in text:
            return JijiListing.Condition.REFURBISHED
        if 'occasion' in text or 'used' in text or 'seconde main' in text:
            return JijiListing.Condition.USED
        return JijiListing.Condition.UNKNOWN

    @staticmethod
    def _parse_location(tree, page_text: str) -> tuple[str, str]:
        region = area = ''
        loc_el = tree.xpath('//*[contains(@class,"b-advert-info-statistics--region") or contains(@class,"b-advert-card__head-region")]')
        loc = ' '.join((loc_el[0].text_content() if loc_el else '').split())
        if not loc:
            m = re.search(r'Région de ([^,]+),\s*([^,]+)', page_text)
            if m:
                return m.group(1).strip()[:120], m.group(2).strip()[:120]
            return '', ''
        # "Région de Dakar, Rufisque, il y a 2 heures"
        m = re.search(r'Région de ([^,]+),\s*([^,]+)', loc)
        if m:
            region, area = m.group(1).strip(), m.group(2).strip()
        else:
            parts = [p.strip() for p in loc.split(',') if p.strip()]
            if parts:
                region = parts[0].replace('Région de ', '')
            if len(parts) > 1:
                area = parts[1]
        return region[:120], area[:120]

    @staticmethod
    def _guess_catalog_slug(name: str, keyword: str = '') -> str:
        try:
            from intelligence.nlp_taxonomy import PRODUCT_CATALOG
        except Exception:
            return ''
        blob = f'{name} {keyword}'.lower()
        best_slug = ''
        best_hits = 0
        for slug, meta in PRODUCT_CATALOG.items():
            hits = sum(1 for kw in meta.get('keywords', ()) if kw.lower() in blob)
            if hits > best_hits:
                best_hits = hits
                best_slug = slug
        return best_slug if best_hits > 0 else ''

    @staticmethod
    def _normalize_needle(text: str) -> str:
        t = (text or '').lower()
        for a, b in (('é', 'e'), ('è', 'e'), ('ê', 'e'), ('à', 'a'), ('ù', 'u'), ('ô', 'o')):
            t = t.replace(a, b)
        return ' '.join(t.split())

    @staticmethod
    def _parse_price(text: str) -> Decimal | None:
        if not text:
            return None
        cleaned = re.sub(r'[^\d]', '', text.replace(',', ''))
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
