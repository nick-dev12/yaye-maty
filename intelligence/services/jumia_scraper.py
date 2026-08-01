"""
Scraper Jumia Sénégal — listings, fiches produit (JSON-LD), avis clients.

Respecte robots.txt Jumia :
- User-Agent clairement identifié (bot + contact)
- < 200 requêtes / minute
- Endpoint avis `/catalog/productratingsreviews/sku/<SKU>/` autorisé
- Pas d'URL `?q=` (interdit aux crawlers) — catégories + filtre mot-clé
- Playwright uniquement en repli si challenge anti-bot détecté
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import urljoin, urlparse

import requests
from lxml import html as lxml_html

from intelligence.models.jumia_product import JumiaProduct

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.jumia.sn'
USER_AGENT = (
    'YayematyMarketBot/1.0 (+https://yayematy.local/contact; market-intelligence; respectful; <200rpm)'
)

# Mapping mot-clé → catégorie Jumia (évite /*q=) — généraliste, piloté par mots-clés
KEYWORD_CATEGORY_PATHS: dict[str, str] = {
    # Téléphones & tech
    'iphone': '/telephones-tablettes/',
    'telephone': '/telephones-tablettes/',
    'smartphone': '/telephones-tablettes/',
    'samsung': '/telephones-tablettes/',
    'xiaomi': '/telephones-tablettes/',
    'tecno': '/telephones-tablettes/',
    'infinix': '/telephones-tablettes/',
    'tablette': '/telephones-tablettes/',
    'ecouteur': '/electronique/',
    'chargeur': '/electronique/',
    'accessoire telephone': '/telephones-tablettes/',
    'telephone et accessoir': '/telephones-tablettes/',
    # TV & électro
    'television': '/tv-audio-video/',
    'tv': '/tv-audio-video/',
    'televiseur': '/tv-audio-video/',
    'climatiseur': '/electronique/',
    'ventilateur': '/electronique/',
    'electromenager': '/electromenager/',
    'refrigerateur': '/electromenager/',
    'micro onde': '/electromenager/',
    # Informatique
    'ordinateur': '/informatique/',
    'laptop': '/informatique/',
    'pc': '/informatique/',
    # Mode
    'chaussure': '/mode/',
    'vetement': '/mode/',
    'sac': '/mode/',
    # Maison / jardin / agricole (si mot-clé le demande)
    'motopompe': '/terrasse-jardin-exterieur/',
    'pompe': '/terrasse-jardin-exterieur/',
    'pompe solaire': '/terrasse-jardin-exterieur/',
    'irrigation': '/terrasse-jardin-exterieur/',
    'goutte a goutte': '/terrasse-jardin-exterieur/',
    'pulverisateur': '/terrasse-jardin-exterieur/',
    'pulvérisateur': '/terrasse-jardin-exterieur/',
    'brouette': '/terrasse-jardin-exterieur/',
    'tronconneuse': '/terrasse-jardin-exterieur/',
    'couveuse': '/terrasse-jardin-exterieur/',
    'tracteur': '/terrasse-jardin-exterieur/',
    'engrais': '/supermarche/',
    'semence': '/supermarche/',
    'materiel agricole': '/terrasse-jardin-exterieur/',
    'jardin': '/terrasse-jardin-exterieur/',
    # Beauté / supermarché
    'parfum': '/sante-beaute/',
    'cosmetique': '/sante-beaute/',
    'beaute': '/sante-beaute/',
    'supermarche': '/supermarche/',
}

CHALLENGE_MARKERS = (
    'cf-challenge',
    'challenge-platform',
    'just a moment',
    'verify you are human',
    'attention required',
    'security verification',
    'checking your browser',
)

ShouldCancel = Callable[[], bool]


@dataclass
class ExtractedJumiaReview:
    rating_stars: int | None = None
    title: str = ''
    comment_text: str = ''
    author: str = ''
    review_date: date | None = None
    verified_purchase: bool = False


@dataclass
class ExtractedJumiaProduct:
    sku: str
    product_url: str
    name: str
    brand: str = ''
    category: str = ''
    seller_name: str = ''
    price_xof: Decimal | None = None
    old_price_xof: Decimal | None = None
    discount_percent: float | None = None
    currency: str = 'XOF'
    availability: str = ''
    stock_status: str = JumiaProduct.StockStatus.UNKNOWN
    stock_quantity: int | None = None
    is_in_stock: bool | None = None
    rating_value: float | None = None
    rating_count: int = 0
    rating_distribution: dict = field(default_factory=dict)
    comments_count: int = 0
    description: str = ''
    image_url: str = ''
    search_keyword: str = ''
    catalog_product_slug: str = ''
    reviews: list[ExtractedJumiaReview] = field(default_factory=list)


class JumiaScraperError(Exception):
    """Erreur récupérable du scraper Jumia."""


class JumiaScraper:
    """Client HTTP Jumia avec rythme respectueux, parsing lxml et repli Playwright."""

    def __init__(
        self,
        *,
        delay_min: float = 1.5,
        delay_max: float = 3.5,
        timeout: float = 25.0,
        should_cancel: ShouldCancel | None = None,
        use_playwright_fallback: bool = True,
        max_listing_pages: int = 3,
    ):
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.timeout = timeout
        self.should_cancel = should_cancel
        self.use_playwright_fallback = use_playwright_fallback
        self.max_listing_pages = max(1, min(3, int(max_listing_pages or 3)))
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        })
        self._last_request_at = 0.0
        self.request_count = 0
        self.playwright_fetches = 0
        self._pw_bundle = None

    def close(self) -> None:
        self.session.close()
        if self._pw_bundle is not None:
            try:
                self._pw_bundle.close()
            except Exception:
                logger.debug('Fermeture Playwright Jumia ignorée', exc_info=True)
            self._pw_bundle = None

    def _check_cancel(self) -> None:
        if self.should_cancel and self.should_cancel():
            raise JumiaScraperError('Annulé')

    def _throttle(self) -> None:
        from intelligence.scrapers.human_behavior import random_sleep
        from intelligence.services.collection_abort import interruptible_sleep

        elapsed = time.monotonic() - self._last_request_at
        min_gap = self.delay_min
        if elapsed < min_gap:
            interruptible_sleep(min_gap - elapsed)
        random_sleep(0.2, max(0.3, self.delay_max - self.delay_min))

    @staticmethod
    def _looks_like_challenge(html: str, status_code: int | None = None) -> bool:
        if status_code in (403, 503, 429):
            return True
        low = (html or '')[:8000].lower()
        return any(marker in low for marker in CHALLENGE_MARKERS)

    def _get(self, path_or_url: str) -> str:
        self._check_cancel()
        self._throttle()
        url = path_or_url if path_or_url.startswith('http') else urljoin(BASE_URL, path_or_url)
        self._last_request_at = time.monotonic()
        self.request_count += 1
        try:
            resp = self.session.get(url, timeout=self.timeout)
            html = resp.text or ''
            if self._looks_like_challenge(html, resp.status_code):
                logger.warning('Challenge anti-bot détecté sur %s (HTTP %s)', url, resp.status_code)
                if self.use_playwright_fallback:
                    return self._get_playwright(url)
                resp.raise_for_status()
                raise JumiaScraperError(f'Challenge anti-bot sur {url}')
            resp.raise_for_status()
            return html
        except requests.RequestException as exc:
            if self.use_playwright_fallback:
                logger.warning('HTTP Jumia échoué (%s) — repli Playwright', exc)
                return self._get_playwright(url)
            raise JumiaScraperError(str(exc)) from exc

    def _ensure_playwright(self):
        if self._pw_bundle is not None:
            return self._pw_bundle
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth

        from intelligence.scrapers.constants import CHROMIUM_LAUNCH_ARGS, DEFAULT_VIEWPORT

        stealth = Stealth(navigator_languages_override=('fr-FR', 'fr'))
        stealth_cm = stealth.use_sync(sync_playwright())
        playwright = stealth_cm.__enter__()
        browser = playwright.chromium.launch(headless=True, args=CHROMIUM_LAUNCH_ARGS)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale='fr-FR',
            viewport=DEFAULT_VIEWPORT,
        )
        page = context.new_page()

        class _Bundle:
            def __init__(self, playwright, browser, context, page, stealth_cm):
                self.playwright = playwright
                self.browser = browser
                self.context = context
                self.page = page
                self.stealth_cm = stealth_cm

            def close(self):
                try:
                    self.browser.close()
                finally:
                    self.stealth_cm.__exit__(None, None, None)

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
            page.wait_for_timeout(1200)
        except Exception:
            pass
        html = page.content()
        if self._looks_like_challenge(html):
            raise JumiaScraperError(f'Challenge anti-bot persistant (Playwright) sur {url}')
        return html

    @staticmethod
    def resolve_category_path(keyword: str, product_category: str = '') -> str:
        from intelligence.services.marketplace_catalog_utils import resolve_jumia_category_path

        return resolve_jumia_category_path(keyword, product_category=product_category)

    def search_listing_urls(
        self,
        keyword: str,
        *,
        product_category: str = '',
        max_products: int = 8,
        max_pages: int | None = None,
        known_skus: set[str] | None = None,
        known_urls: set[str] | None = None,
        skip_known: bool = True,
        start_page: int = 1,
        max_scan_pages: int | None = None,
    ) -> list[dict]:
        """
        Collecte des URLs produit depuis pages catégorie (+ accueil si besoin).

        Si ``skip_known`` : parcourt plus de pages jusqu'à trouver de nouveaux SKU
        (non présents dans ``known_skus`` / ``known_urls``).
        """
        from intelligence.services.jumia_dedup_service import JumiaDedupService

        path = self.resolve_category_path(keyword, product_category=product_category)
        pages_per_run = max_pages or self.max_listing_pages
        scan_limit = max_scan_pages or max(pages_per_run, pages_per_run * 3)
        known_skus = known_skus or set()
        known_urls = known_urls or set()
        start_page = max(1, int(start_page or 1))

        cards: list[dict] = []
        seen_urls: set[str] = set()
        pages_scanned = 0
        end_page = start_page + scan_limit - 1

        for page_no in range(start_page, end_page + 1):
            if not path:
                cards = self.fetch_homepage_cards()
                pages_scanned = 1
                break
            page_path = (
                path if page_no == 1
                else f'{path.rstrip("/")}/?page={page_no}#catalog-listing'
            )
            try:
                html = self._get(page_path)
            except JumiaScraperError:
                if page_no == start_page:
                    break
                continue
            page_cards = self._parse_listing_cards(html)

            pages_scanned += 1
            if not page_cards:
                break
            for card in page_cards:
                url = card.get('url') or ''
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    cards.append(card)

            filtered = self._filter_cards_by_keyword(cards, keyword) or cards
            JumiaDedupService.enrich_cards_with_sku(filtered)
            if skip_known:
                new_cards, _ = JumiaDedupService.filter_new_cards(
                    filtered,
                    known_skus=known_skus,
                    known_urls=known_urls,
                    limit=max_products,
                )
                if len(new_cards) >= max_products:
                    break
            elif len(filtered) >= max_products:
                break

        if not cards and path:
            logger.info('Catégorie %s vide pour %r — complément accueil', path, keyword)
            cards = self.fetch_homepage_cards()

        filtered = self._filter_cards_by_keyword(cards, keyword)
        if skip_known:
            chosen, skipped = JumiaDedupService.filter_new_cards(
                filtered if filtered else cards,
                known_skus=known_skus,
                known_urls=known_urls,
                limit=max_products,
            )
            logger.info(
                'Jumia listing %r via %s (%d p. scannées) → %d retenues, %d connues ignorées',
                keyword, path or 'accueil', pages_scanned, len(chosen), skipped,
            )
            return chosen

        if filtered:
            chosen = filtered[:max_products]
        else:
            tokens = [
                t for t in self._normalize_needle(keyword).split()
                if len(t) >= 2 and t not in {'et', 'de', 'du', 'la', 'le', 'les', 'des', 'un', 'une', 'pour', 'avec'}
            ]
            chosen = [] if len(tokens) >= 2 else cards[:max_products]
        logger.info(
            'Jumia listing %r via %s (%d p.) → %d carte(s), %d retenues',
            keyword, path or 'accueil', pages_scanned, len(cards), len(chosen),
        )
        return chosen

    def fetch_homepage_cards(self) -> list[dict]:
        """Parse les cartes produit de la page d'accueil Jumia."""
        html = self._get('/')
        return self._parse_listing_cards(html, source='homepage')

    def filter_cards_by_keyword(self, cards: list[dict], keyword: str) -> list[dict]:
        """Filtre public — alias de ``_filter_cards_by_keyword``."""
        return self._filter_cards_by_keyword(cards, keyword)

    def _filter_cards_by_keyword(self, cards: list[dict], keyword: str) -> list[dict]:
        needle = self._normalize_needle(keyword)
        stop = {'et', 'de', 'du', 'la', 'le', 'les', 'des', 'un', 'une', 'pour', 'avec'}
        tokens = [t for t in needle.split() if len(t) >= 2 and t not in stop]
        if not tokens:
            return list(cards)

        accessory_mode = any(t.startswith('accessoir') for t in tokens)
        accessory_synonyms = (
            'accessoir', 'chargeur', 'coque', 'cable', 'ecouteur', 'oreillett',
            'powerbank', 'etui', 'film', 'verre', 'support', 'dock', 'adaptateur',
            'batterie', 'housse', 'protection',
        )

        scored: list[tuple[int, dict]] = []
        for card in cards:
            name_n = self._normalize_needle(card.get('name') or '')
            hits = sum(1 for t in tokens if t in name_n)
            if accessory_mode:
                has_phone = any(
                    p in name_n
                    for p in ('telephone', 'iphone', 'smartphone', 'mobile', 'android')
                )
                has_acc = any(a in name_n for a in accessory_synonyms)
                if has_acc:
                    scored.append((hits + 2 + (1 if has_phone else 0), card))
                elif has_phone and hits >= 1:
                    # Téléphone lié, priorité plus faible que les accessoires purs
                    scored.append((hits, card))
                continue
            required = max(1, (len(tokens) + 1) // 2)
            if hits >= required:
                scored.append((hits, card))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored]

    def fetch_product(
        self,
        product_url: str,
        *,
        keyword: str = '',
        product_category: str = '',
        max_reviews: int = 20,
    ) -> ExtractedJumiaProduct | None:
        html = self._get(product_url)
        product = self._parse_product_page(html, product_url)
        if not product:
            return None
        product.search_keyword = keyword
        from intelligence.services.marketplace_catalog_utils import resolve_catalog_slug

        product.catalog_product_slug = resolve_catalog_slug(
            product.name,
            keyword,
            product_category=product_category,
        )
        if product.sku:
            # max_reviews=0 → toutes les pages d'avis
            pages = 0 if max_reviews <= 0 else 3
            reviews, dist, comments_count = self.fetch_reviews(
                product.sku, max_reviews=max_reviews, max_pages=pages,
            )
            product.reviews = reviews
            if dist:
                product.rating_distribution = dist
            if comments_count:
                product.comments_count = comments_count
        return product

    def fetch_reviews(
        self,
        sku: str,
        *,
        max_reviews: int = 20,
        max_pages: int = 3,
    ) -> tuple[list[ExtractedJumiaReview], dict, int]:
        """
        Récupère les avis d'un SKU.

        ``max_reviews=0`` ou ``max_pages=0`` = pas de plafond (jusqu'à pages vides).
        """
        all_reviews: list[ExtractedJumiaReview] = []
        distribution: dict = {}
        comments_count = 0
        path = f'/catalog/productratingsreviews/sku/{sku}/'
        page_limit = 500 if max_pages <= 0 else max_pages
        for page in range(1, page_limit + 1):
            url = path if page == 1 else f'{path}?page={page}'
            try:
                html = self._get(url)
            except JumiaScraperError as exc:
                logger.warning('Avis Jumia SKU=%s page=%s : %s', sku, page, exc)
                break
            page_reviews, page_dist, page_comments = self._parse_reviews_page(html)
            if page == 1:
                distribution = page_dist
                comments_count = page_comments
            all_reviews.extend(page_reviews)
            if len(page_reviews) == 0:
                break
            if max_reviews > 0 and len(all_reviews) >= max_reviews:
                break
        if max_reviews > 0:
            return all_reviews[:max_reviews], distribution, comments_count
        return all_reviews, distribution, comments_count

    # ------------------------------------------------------------------ parsing

    def _parse_listing_cards(self, html: str, *, source: str = 'listing') -> list[dict]:
        tree = lxml_html.fromstring(html)
        cards = []
        for art in tree.xpath('//article[contains(@class,"prd")]'):
            links = art.xpath('.//a[contains(@class,"core")]')
            if not links:
                continue
            link = links[0]
            href = link.get('href') or ''
            name_el = art.xpath('.//*[contains(@class,"name")]')
            name = (name_el[0].text_content() if name_el else '').strip()
            price_el = art.xpath('.//*[contains(@class,"prc")]')
            price = (price_el[0].text_content() if price_el else '').strip()
            old_el = art.xpath('.//*[contains(@class,"old")]')
            old_price = (old_el[0].text_content() if old_el else '').strip()
            disc_el = art.xpath('.//*[contains(@class,"_dsct")]')
            discount_badge = (disc_el[0].text_content() if disc_el else '').strip()
            brand = (
                link.get('data-brand')
                or link.get('data-gtm-brand')
                or ''
            ).strip()
            card_category = (
                link.get('data-category')
                or link.get('data-gtm-category')
                or ''
            ).strip()
            gtm_sku = (link.get('data-gtm-id') or link.get('data-id') or '').strip()
            stars_el = art.xpath('.//*[contains(@class,"stars")]')
            rating = None
            review_count = None
            if stars_el:
                stars_txt = stars_el[0].text_content()
                m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*out of 5', stars_txt, re.I)
                if m:
                    rating = float(m.group(1))
                m2 = re.search(r'\(([0-9]+)\)', stars_txt)
                if m2:
                    review_count = int(m2.group(1))
            raw_text = art.text_content()
            stock_remaining = None
            m_stock = re.search(r'(\d+)\s*articles?\s*restants?', raw_text, re.I)
            if m_stock:
                stock_remaining = int(m_stock.group(1))
            discount_percent = None
            if discount_badge:
                m_disc = re.search(r'(\d+(?:\.\d+)?)', discount_badge.replace(',', '.'))
                if m_disc:
                    discount_percent = float(m_disc.group(1))
            if href and name:
                abs_url = urljoin(BASE_URL, href)
                from intelligence.services.jumia_dedup_service import JumiaDedupService

                cards.append({
                    'url': abs_url,
                    'name': name,
                    'brand': brand[:120],
                    'category': card_category[:160],
                    'price': price,
                    'old_price': old_price,
                    'discount_badge': discount_badge,
                    'discount_percent': discount_percent,
                    'rating': rating,
                    'review_count': review_count,
                    'stock_remaining': stock_remaining,
                    'raw_text': raw_text,
                    'section_label': 'ventes_flash' if source == 'homepage' and stock_remaining else source,
                    'sku': gtm_sku or JumiaDedupService.extract_sku_from_url(abs_url),
                })
        return cards

    def _parse_product_page(self, html: str, product_url: str) -> ExtractedJumiaProduct | None:
        product_node = self._extract_jsonld_product(html)
        if not product_node:
            logger.warning('JSON-LD Product absent : %s', product_url)
            return None

        sku = (product_node.get('sku') or '').strip()
        if not sku:
            return None

        offers = product_node.get('offers') or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        seller = offers.get('seller') or {}
        if isinstance(seller, list):
            seller = seller[0] if seller else {}

        brand_raw = product_node.get('brand') or {}
        if isinstance(brand_raw, dict):
            brand = (brand_raw.get('name') or '').strip()
        elif isinstance(brand_raw, str):
            brand = brand_raw.strip()
        else:
            brand = ''

        agg = product_node.get('aggregateRating') or {}
        image_url = self._extract_image_url(product_node.get('image'))

        tree = lxml_html.fromstring(html)
        page_text = tree.text_content()

        price = self._to_decimal(offers.get('price'))
        old_price, discount = self._extract_prices_and_discount(tree, price, offers)

        availability = self._short_availability(offers.get('availability') or '')
        stock_status, stock_qty, is_in_stock = self._parse_stock(page_text, availability)

        abs_url = product_url if product_url.startswith('http') else urljoin(BASE_URL, product_url)
        return ExtractedJumiaProduct(
            sku=sku,
            product_url=abs_url,
            name=(product_node.get('name') or '').strip()[:400],
            brand=brand[:120],
            category=(product_node.get('category') or '').strip()[:160],
            seller_name=(seller.get('name') or '').strip()[:160],
            price_xof=price,
            old_price_xof=old_price,
            discount_percent=discount,
            currency=(offers.get('priceCurrency') or 'XOF')[:8],
            availability=availability,
            stock_status=stock_status,
            stock_quantity=stock_qty,
            is_in_stock=is_in_stock,
            rating_value=self._to_float(agg.get('ratingValue')),
            rating_count=int(agg.get('ratingCount') or 0),
            description=(product_node.get('description') or '')[:4000],
            image_url=image_url[:500],
        )

    def _parse_reviews_page(
        self, html: str,
    ) -> tuple[list[ExtractedJumiaReview], dict, int]:
        tree = lxml_html.fromstring(html)
        reviews: list[ExtractedJumiaReview] = []
        for art in tree.xpath('//article'):
            stars_el = art.xpath('.//*[contains(@class,"stars")]')
            if not stars_el:
                continue
            stars = None
            m = re.search(r'([1-5])\s*out of 5', stars_el[0].text_content(), re.I)
            if m:
                stars = int(m.group(1))
            title_el = art.xpath('.//h3')
            title = (title_el[0].text_content() if title_el else '').strip()[:200]
            p_el = art.xpath('.//p')
            comment = (p_el[0].text_content() if p_el else '').strip()
            blob = f'{title} {comment}'.lower()
            if 'cookie' in blob or 'confidentialit' in blob:
                continue
            author = ''
            review_date = None
            text_block = art.text_content()
            m_date = re.search(r'(\d{2}-\d{2}-\d{4})', text_block)
            if m_date:
                review_date = self._parse_date(m_date.group(1))
            m_author = re.search(r'par\s+([^\n]+?)(?:\s*Achat|\s*$)', text_block)
            if m_author:
                author = m_author.group(1).strip()[:120]
            art_html = lxml_html.tostring(art, encoding='unicode')
            verified = 'Achat vérifié' in text_block or 'check-verified' in art_html
            if stars is None and not title and not comment:
                continue
            reviews.append(ExtractedJumiaReview(
                rating_stars=stars,
                title=title,
                comment_text=comment,
                author=author,
                review_date=review_date,
                verified_purchase=verified,
            ))

        page_text = tree.text_content()
        distribution: dict[str, int] = {}
        for star in range(5, 0, -1):
            m = re.search(rf'{star}\s*\((\d+)\)', page_text)
            if m:
                distribution[str(star)] = int(m.group(1))
        comments_count = 0
        m_com = re.search(r'Commentaires\s*\((\d+)\)', page_text, re.I)
        if m_com:
            comments_count = int(m_com.group(1))
        return reviews, distribution, comments_count

    @classmethod
    def _extract_prices_and_discount(
        cls,
        tree,
        price: Decimal | None,
        offers: dict | None = None,
    ) -> tuple[Decimal | None, float | None]:
        """Extrait prix barré et remise (% badge _dsct, JSON-LD highPrice, ou calcul)."""
        old_price = None
        discount = None
        offers = offers or {}

        # JSON-LD : highPrice
        high = cls._to_decimal(offers.get('highPrice'))
        if high and price and high > price:
            old_price = high

        old_els = tree.xpath(
            '//*[contains(@class,"old") or contains(@class,"-old") '
            'or contains(@class,"price-old")]'
        )
        for el in old_els:
            parsed = cls._parse_price(el.text_content())
            if parsed and (price is None or parsed > price):
                old_price = parsed
                break

        # Badge remise Jumia : class "_dsct" → "11%"
        for el in tree.xpath('//*[contains(@class,"_dsct")]'):
            m = re.search(r'(\d+)\s*%', (el.text_content() or ''))
            if m:
                discount = float(m.group(1))
                break

        if discount is None and price and old_price:
            discount = JumiaProduct.compute_discount_percent(price, old_price)
        elif discount is not None and price and old_price is None and discount < 100:
            # Reconstituer le prix barré à partir du % affiché
            try:
                factor = Decimal('1') - (Decimal(str(discount)) / Decimal('100'))
                if factor > 0:
                    old_price = (price / factor).quantize(Decimal('1'))
            except (InvalidOperation, ZeroDivisionError):
                pass
        elif discount is None:
            discount = JumiaProduct.compute_discount_percent(price, old_price)

        return old_price, discount

    @staticmethod
    def _parse_stock(page_text: str, availability: str) -> tuple[str, int | None, bool | None]:
        text = (page_text or '').lower()
        qty = None
        m_qty = re.search(
            r"(?:il n'en reste plus que|plus que|seulement|reste(?:nt)?)\s*(\d+)\s*(?:article|unité|unite|en stock)?",
            text,
            re.I,
        )
        if m_qty:
            qty = int(m_qty.group(1))

        avail = (availability or '').lower()
        # JSON-LD prioritaire (fiable) — éviter faux positifs footer « politique de retour »
        if 'outofstock' in avail:
            return JumiaProduct.StockStatus.OUT_OF_STOCK, qty, False
        if 'instock' in avail or 'limitedavailability' in avail:
            if qty is not None and qty <= 5:
                return JumiaProduct.StockStatus.LOW_STOCK, qty, True
            return JumiaProduct.StockStatus.IN_STOCK, qty, True

        if re.search(r'rupture de stock|actuellement indisponible|produit indisponible', text):
            return JumiaProduct.StockStatus.OUT_OF_STOCK, qty, False
        if qty is not None and qty <= 5:
            return JumiaProduct.StockStatus.LOW_STOCK, qty, True
        if qty is not None or 'ajouter au panier' in text:
            return JumiaProduct.StockStatus.IN_STOCK, qty, True
        return JumiaProduct.StockStatus.UNKNOWN, qty, None

    @staticmethod
    def _guess_catalog_slug(name: str, keyword: str = '') -> str:
        from intelligence.nlp_taxonomy import PRODUCT_CATALOG

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
    def _extract_image_url(image) -> str:
        if isinstance(image, dict):
            urls = image.get('contentUrl') or image.get('url') or []
            if isinstance(urls, list) and urls:
                return urls[0]
            if isinstance(urls, str):
                return urls
        elif isinstance(image, str):
            return image
        elif isinstance(image, list) and image:
            return image[0] if isinstance(image[0], str) else ''
        return ''

    @staticmethod
    def _extract_jsonld_product(html: str) -> dict | None:
        for match in re.finditer(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.I | re.S,
        ):
            raw = match.group(1).strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get('@type') == 'Product':
                return data
            if isinstance(data, dict) and '@graph' in data:
                for node in data['@graph']:
                    if isinstance(node, dict) and node.get('@type') == 'Product':
                        return node
            if isinstance(data, list):
                for node in data:
                    if isinstance(node, dict) and node.get('@type') == 'Product':
                        return node
        return None

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
        cleaned = re.sub(r'[^\d]', '', text.replace('\u202f', '').replace(' ', ''))
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    @staticmethod
    def _to_decimal(value) -> Decimal | None:
        if value is None or value == '':
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _short_availability(raw: str) -> str:
        if not raw:
            return ''
        return urlparse(raw).path.rstrip('/').split('/')[-1][:80] or raw[:80]

    @staticmethod
    def _parse_date(raw: str) -> date | None:
        try:
            return datetime.strptime(raw, '%d-%m-%Y').date()
        except ValueError:
            return None
