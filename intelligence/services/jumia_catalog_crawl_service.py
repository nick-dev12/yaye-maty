"""
Crawl catalogue Jumia — catégories + produits + avis complets (hors mots-clés session).

Destiné à un run local (IP résidentielle) pour peupler la BDD consommée
ensuite par Trade Intelligence (100 produits/tour × 3 tours).
"""

from __future__ import annotations

import logging
import re
from typing import Callable
from urllib.parse import urljoin, urlparse

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from lxml import html as lxml_html

from intelligence.models import JumiaCategory, JumiaProduct, JumiaReview
from intelligence.services.jumia_scraper import BASE_URL, JumiaScraper, JumiaScraperError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]
StatsCallback = Callable[[dict], None]
ShouldCancelCallback = Callable[[], bool]

# Garde-fou anti-boucle pagination (pas une limite métier UI)
_MAX_PAGES_HARD = 500
_MAX_CAT_DEPTH = 3

# Noms lisibles pour slugs connus Jumia SN
CATEGORY_LABELS: dict[str, str] = {
    'telephones-tablettes': 'Téléphones & Tablettes',
    'smartphones': 'Smartphones',
    'electronique': 'Électronique',
    'informatique': 'Informatique',
    'electromenager': 'Électroménager',
    'mode': 'Mode',
    'sante-beaute': 'Santé & Beauté',
    'supermarche': 'Supermarché',
    'tv-audio-video': 'TV Audio Vidéo',
    'terrasse-jardin-exterieur': 'Terrasse & Jardin',
    'maison-bureau-industrie': 'Maison & Bureau',
    'jeux-videos-consoles': 'Jeux vidéos & Consoles',
    'sports-fitness': 'Sports & Fitness',
    'bebe-puericulture': 'Bébé & Puériculture',
    'auto-moto': 'Auto & Moto',
    'animaux': 'Animaux',
    'bagages-voyage': 'Bagages & Voyage',
    'jardin-plein-air': 'Jardin & Plein air',
}

# Racines Jumia SN si découverte accueil échoue
FALLBACK_ROOT_CATEGORIES: list[tuple[str, str]] = [
    ('telephones-tablettes', 'Téléphones & Tablettes'),
    ('telephone-tablette', 'Téléphones & Tablettes'),
    ('electronique', 'Électronique'),
    ('informatique', 'Informatique'),
    ('electromenager', 'Électroménager'),
    ('tv-audio-video', 'TV Audio Vidéo'),
    ('mode', 'Mode'),
    ('fashion-mode', 'Mode'),
    ('sante-beaute', 'Santé & Beauté'),
    ('beaute-hygiene-sante', 'Santé & Beauté'),
    ('supermarche', 'Supermarché'),
    ('epiceries', 'Supermarché'),
    ('maison-bureau-industrie', 'Maison & Bureau'),
    ('maison-cuisine-jardin', 'Maison & Cuisine'),
    ('jeux-videos-consoles', 'Jeux vidéos & Consoles'),
    ('sports-fitness', 'Sports & Fitness'),
    ('sports-loisirs', 'Sports & Loisirs'),
    ('bebe-puericulture', 'Bébé & Puériculture'),
    ('auto-moto', 'Auto & Moto'),
    ('terrasse-jardin-exterieur', 'Terrasse & Jardin'),
    ('animaux', 'Animaux'),
    ('bagages-voyage', 'Bagages & Voyage'),
]

_SKIP_ROOT_SLUGS = {
    'cart', 'customer', 'login', 'newsletter', 'flash-sales', 'mlp-',
    'catalog', 'all-products', 'event', 'sp-', 'php', 'help',
    'about', 'contact', 'vendor', 'seller', 'checkout', 'order',
    'search', 'c', 'en', 'fr', 'ar', 'account', 'wishlist',
    'track', 'politique-confidentialite', 'brand', 'brands',
}

# Slugs racines marketplace Jumia SN (pas les pages marque / vendeur)
_KNOWN_ROOT_SLUGS = frozenset(slug for slug, _ in FALLBACK_ROOT_CATEGORIES)


class JumiaCatalogCrawlService:
    """Peuple JumiaCategory + JumiaProduct (+ JumiaReview) depuis les listings."""

    @classmethod
    def crawl_full_catalog(
        cls,
        *,
        with_reviews: bool = True,
        dry_run: bool = False,
        roots_filter: list[tuple[str, str]] | None = None,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        on_stats: StatsCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        """
        Crawl automatique : toutes les catégories racines, toutes les sous-cats,
        toutes les pages, tous les produits (anti-doublon note/avis).
        """
        scraper = JumiaScraper(
            delay_min=1.2,
            delay_max=2.8,
            should_cancel=should_cancel,
            use_playwright_fallback=True,
            max_listing_pages=_MAX_PAGES_HARD,
        )
        counters = {
            'products_created': 0,
            'products_updated': 0,
            'products_skipped': 0,
            'reviews_created': 0,
            'products_seen': 0,
            'categories_done': 0,
            'roots_total': 0,
            'subs_total': 0,
        }
        categories_touched: list[str] = []
        errors: list[str] = []
        seen_skus: set[str] = set()
        known_products: dict[str, dict] = {}

        def _log(msg: str) -> None:
            logger.info('%s', msg)
            if log:
                try:
                    log(msg)
                except Exception:
                    pass
            cls._report(progress, None, msg)

        def _emit_stats(payload: dict | None = None, **extra) -> None:
            data = {
                **counters,
                'categories': list(categories_touched),
                **extra,
            }
            if payload:
                data.update(payload)
            if on_stats:
                try:
                    on_stats(data)
                except Exception:
                    pass

        if not dry_run:
            known_products = cls._run_orm_safe(cls._load_known_products_cache)
            _log(f'Cache anti-doublon : {len(known_products)} SKU déjà en base')

        try:
            _log('Démarrage crawl catalogue Jumia — découverte des catégories…')
            cls._report(progress, 2, 'Découverte des catégories racines…')

            if roots_filter:
                roots = list(roots_filter)
                _log(f'Crawl ciblé — {len(roots)} catégorie(s) racine(s)')
            else:
                try:
                    home_html = scraper._get('/')
                except Exception as exc:
                    _log(f'Accueil Jumia inaccessible : {exc}')
                    home_html = ''

                roots = cls._discover_root_categories(home_html)
                if not roots:
                    roots = cls._dedupe_roots(FALLBACK_ROOT_CATEGORIES)
                    _log(f'Fallback — {len(roots)} catégorie(s) racine(s) marketplace')
                else:
                    _log(f'{len(roots)} catégorie(s) racine marketplace')
            for s, n in roots:
                _log(f'  · {n} (/{s}/)')

            counters['roots_total'] = len(roots)
            _emit_stats(current_category='')

            for root_idx, (root_slug, root_name) in enumerate(roots):
                if should_cancel and should_cancel():
                    _log('Arrêt demandé — crawl interrompu')
                    break

                root_path = f'/{root_slug}/'
                pct = 3 + int(90 * root_idx / max(len(roots), 1))
                cls._report(
                    progress, pct,
                    f'Catégorie {root_idx + 1}/{len(roots)} — {root_name}',
                )
                _log('─' * 48)
                _log(
                    f'▶ Catégorie racine {root_idx + 1}/{len(roots)} : '
                    f'{root_name} ({root_path})'
                )

                root_obj = None
                if not dry_run:
                    root_obj = cls._upsert_category_safe(
                        slug=root_slug, path=root_path, parent=None, name=root_name,
                    )
                    categories_touched.append(root_obj.slug)

                # Sous-catégories niveau 1 depuis la page racine (sans BFS HTTP)
                _log(f'  Chargement page {root_path}…')
                try:
                    root_html = scraper._get(root_path)
                except Exception as exc:
                    errors.append(f'{root_path}: {exc}')
                    _log(f'  ✗ Impossible de charger {root_path} : {exc}')
                    continue
                _log('  Page chargée — découverte sous-catégories…')

                nodes: list[tuple[JumiaCategory | None, str, str, str]] = [
                    (root_obj, root_slug, root_path, root_name),
                ]
                seen_cat_paths = {root_path}
                sub_count = 0

                children = cls._discover_subcategories(root_html, root_slug)
                for child_slug, child_path, child_name in children:
                    if should_cancel and should_cancel():
                        break
                    if child_path in seen_cat_paths:
                        continue
                    seen_cat_paths.add(child_path)
                    child_obj = None
                    if not dry_run and root_obj is not None:
                        child_obj = cls._upsert_category_safe(
                            slug=child_slug,
                            path=child_path,
                            parent=root_obj,
                            name=child_name,
                        )
                        categories_touched.append(child_obj.slug)
                    nodes.append((child_obj, child_slug, child_path, child_name))
                    sub_count += 1
                    if sub_count <= 12 or sub_count % 10 == 0:
                        _log(f'    · sous-cat {sub_count} : {child_name} ({child_path})')

                counters['subs_total'] += sub_count
                _log(
                    f'  {sub_count} sous-catégorie(s) · '
                    f'{len(nodes)} listing(s) à parcourir '
                    f'(racine + sous-cats)'
                )
                _emit_stats(
                    current_category=root_name,
                    current_subs=sub_count,
                )

                for n_idx, (cat_obj, cat_slug, cat_path, cat_name) in enumerate(nodes):
                    if should_cancel and should_cancel():
                        break
                    _log(
                        f'  → Listing [{n_idx + 1}/{len(nodes)}] '
                        f'{cat_name} ({cat_path})'
                    )
                    before_created = counters['products_created']
                    before_updated = counters['products_updated']
                    before_skipped = counters['products_skipped']
                    before_reviews = counters['reviews_created']
                    before_seen = len(seen_skus)

                    cls._crawl_listing_pages(
                        scraper,
                        cat_obj=cat_obj,
                        cat_slug=cat_slug,
                        cat_path=cat_path,
                        cat_name=cat_name,
                        with_reviews=with_reviews,
                        dry_run=dry_run,
                        seen_skus=seen_skus,
                        known_products=known_products,
                        counters=counters,
                        errors=errors,
                        should_cancel=should_cancel,
                        log=_log,
                        on_stats=_emit_stats,
                    )

                    if not dry_run and cat_obj:
                        cls._run_orm_safe(cls._refresh_category_stats, cat_obj)
                        counters['categories_done'] += 1

                    _log(
                        f'    ✓ {cat_name} : '
                        f"+{counters['products_created'] - before_created} créés · "
                        f"{counters['products_updated'] - before_updated} maj · "
                        f"{counters['products_skipped'] - before_skipped} ignorés · "
                        f"{counters['reviews_created'] - before_reviews} avis · "
                        f"{len(seen_skus) - before_seen} SKU vus "
                        f"(total session : {counters['products_created']} créés / "
                        f"{len(seen_skus)} vus)"
                    )
                    _emit_stats(current_category=cat_name)

                _log(
                    f'■ Fin catégorie « {root_name} » — '
                    f'total créés {counters["products_created"]}, '
                    f'maj {counters["products_updated"]}, '
                    f'ignorés {counters["products_skipped"]}'
                )

            cancelled = bool(should_cancel and should_cancel())
            msg = (
                f'Catalogue Jumia terminé{" (interrompu)" if cancelled else ""} : '
                f'{counters["products_created"]} créé(s), '
                f'{counters["products_updated"]} maj, '
                f'{counters["products_skipped"]} ignoré(s), '
                f'{counters["reviews_created"]} avis, '
                f'{len(categories_touched)} catégorie(s)'
            )
            _log(msg)
            cls._report(progress, 100 if not cancelled else 95, msg)
            _emit_stats()
            return {
                'success': not cancelled or counters['products_created'] > 0,
                'message': msg,
                'products_created': counters['products_created'],
                'products_updated': counters['products_updated'],
                'products_skipped': counters['products_skipped'],
                'reviews_created': counters['reviews_created'],
                'products_seen': len(seen_skus),
                'categories': categories_touched,
                'roots_total': counters['roots_total'],
                'subs_total': counters['subs_total'],
                'errors': errors[:40],
                'dry_run': dry_run,
                'requests': scraper.request_count,
                'playwright_fetches': scraper.playwright_fetches,
                'cancelled': cancelled,
            }
        finally:
            scraper.close()

    @classmethod
    def crawl(
        cls,
        category_slug: str = '',
        *,
        max_pages: int = 0,
        max_products: int = 0,
        with_reviews: bool = True,
        include_subcategories: bool = True,
        dry_run: bool = False,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        on_stats: StatsCallback | None = None,
        should_cancel: ShouldCancelCallback | None = None,
    ) -> dict:
        """
        Compatibilité CLI.

        Sans ``category_slug`` → crawl catalogue complet.
        Avec slug → une racine + sous-cats, pages illimitées (max_pages=0).
        """
        if not (category_slug or '').strip():
            return cls.crawl_full_catalog(
                with_reviews=with_reviews,
                dry_run=dry_run,
                progress=progress,
                log=log,
                on_stats=on_stats,
                should_cancel=should_cancel,
            )

        slug = cls._normalize_slug(category_slug)
        name = CATEGORY_LABELS.get(slug) or slug.replace('-', ' ').title()
        return cls.crawl_full_catalog(
            with_reviews=with_reviews,
            dry_run=dry_run,
            roots_filter=[(slug, name)],
            progress=progress,
            log=log,
            on_stats=on_stats,
            should_cancel=should_cancel,
        )

    # ------------------------------------------------------------------ listing

    @classmethod
    def _crawl_listing_pages(
        cls,
        scraper: JumiaScraper,
        *,
        cat_obj: JumiaCategory | None,
        cat_slug: str,
        cat_path: str,
        cat_name: str,
        with_reviews: bool,
        dry_run: bool,
        seen_skus: set[str],
        known_products: dict[str, dict],
        counters: dict,
        errors: list[str],
        should_cancel: ShouldCancelCallback | None,
        log: LogCallback | None,
        on_stats: StatsCallback | None,
    ) -> None:
        for page_no in range(1, _MAX_PAGES_HARD + 1):
            if should_cancel and should_cancel():
                break
            page_path = (
                cat_path if page_no == 1
                else f'{cat_path.rstrip("/")}/?page={page_no}#catalog-listing'
            )
            try:
                page_html = scraper._get(page_path)
            except JumiaScraperError as exc:
                errors.append(f'{page_path}: {exc}')
                if log:
                    log(f'    page {page_no} erreur : {exc}')
                break
            cards = scraper._parse_listing_cards(page_html)
            if not cards:
                if page_no == 1 and log:
                    log('    (aucun produit sur ce listing)')
                break
            if log and page_no == 1:
                log(f'    page 1 · {len(cards)} carte(s) — traitement produit par produit…')
            elif log and page_no > 1:
                log(f'    page {page_no} · {len(cards)} carte(s)')

            card_index = 0
            for card in cards:
                if should_cancel and should_cancel():
                    break
                sku = (card.get('sku') or '').strip()
                url = card.get('url') or ''
                if not sku and url:
                    from intelligence.services.jumia_dedup_service import JumiaDedupService
                    sku = JumiaDedupService.extract_sku_from_url(url) or ''
                if not sku or sku in seen_skus:
                    continue
                seen_skus.add(sku)
                counters['products_seen'] = len(seen_skus)
                card_index += 1

                if dry_run:
                    counters['products_created'] += 1
                    if log:
                        log(f'      [{card_index}/{len(cards)}] {sku} · dry-run')
                    continue

                try:
                    created, updated, rev_n, skipped = cls._persist_card(
                        scraper,
                        card=card,
                        sku=sku,
                        category=cat_obj,
                        category_label=cat_name or cat_slug,
                        with_reviews=with_reviews,
                        known_products=known_products,
                        log=log,
                    )
                    counters['products_created'] += created
                    counters['products_updated'] += updated
                    counters['reviews_created'] += rev_n
                    counters['products_skipped'] += skipped
                    if log:
                        action = (
                            'créé' if created else
                            'maj' if updated else
                            'ignoré' if skipped else 'ok'
                        )
                        extra = f' · {rev_n} avis' if rev_n else ''
                        log(f'      [{card_index}/{len(cards)}] {sku[:24]} · {action}{extra}')
                    if on_stats:
                        on_stats({
                            **counters,
                            'current_category': cat_name,
                            'current_sku': sku,
                        })
                except Exception as exc:
                    logger.exception('Persist catalogue SKU=%s', sku)
                    errors.append(f'{sku}: {exc}')
                    if log:
                        log(f'      [{card_index}/{len(cards)}] {sku} · erreur : {exc}')

    # ------------------------------------------------------------------ ORM (hors contexte Playwright)

    @staticmethod
    def _run_orm_safe(fn, *args, **kwargs):
        """Exécute une opération Django ORM hors du contexte async Playwright."""
        from django.db import close_old_connections

        def _invoke():
            close_old_connections()
            try:
                return fn(*args, **kwargs)
            finally:
                close_old_connections()

        try:
            return _invoke()
        except Exception as exc:
            from django.core.exceptions import SynchronousOnlyOperation

            if not isinstance(exc, SynchronousOnlyOperation):
                raise

        from concurrent.futures import ThreadPoolExecutor
        from contextvars import copy_context

        ctx = copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(ctx.run, _invoke).result()

    @staticmethod
    def _load_known_products_cache() -> dict[str, dict]:
        return {
            row['sku']: row
            for row in JumiaProduct.objects.values(
                'sku', 'rating_value', 'rating_count',
                'comments_count', 'jumia_category_id',
            )
        }

    @classmethod
    def _upsert_category_safe(cls, **kwargs) -> JumiaCategory:
        return cls._run_orm_safe(lambda: cls._upsert_category(**kwargs))

    # ------------------------------------------------------------------ persist / dedup

    @classmethod
    def _persist_card(
        cls,
        scraper: JumiaScraper,
        *,
        card: dict,
        sku: str,
        category: JumiaCategory | None,
        category_label: str,
        with_reviews: bool,
        known_products: dict[str, dict] | None = None,
        log: LogCallback | None = None,
    ) -> tuple[int, int, int, int]:
        """
        Anti-doublon catalogue — enregistrement depuis la carte listing (rapide).

        Les avis sont récupérés via l'endpoint dédié (pas fetch_product complet).
        """
        known_products = known_products if known_products is not None else {}
        cached = known_products.get(sku)
        card_rating = card.get('rating')
        card_review_count = int(card.get('review_count') or 0)
        use_cache = bool(known_products)

        if use_cache and cached is not None:
            if not cls._cache_needs_update(cached, card_rating, card_review_count):
                if category and not cached.get('jumia_category_id'):
                    cls._run_orm_safe(
                        lambda: JumiaProduct.objects.filter(sku=sku).update(
                            jumia_category=category,
                        ),
                    )
                    cached['jumia_category_id'] = category.pk
                return 0, 0, 0, 1
            existing = cls._run_orm_safe(
                lambda: JumiaProduct.objects.filter(sku=sku).first(),
            )
        elif use_cache:
            existing = None
        else:
            existing = cls._run_orm_safe(
                lambda: JumiaProduct.objects.filter(sku=sku).first(),
            )
            if existing is not None and not cls._needs_rating_or_reviews_update(
                existing,
                card_rating=card_rating,
                card_review_count=card_review_count,
            ):
                if category and existing.jumia_category_id is None:
                    cls._run_orm_safe(
                        lambda: JumiaProduct.objects.filter(pk=existing.pk).update(
                            jumia_category=category,
                        ),
                    )
                return 0, 0, 0, 1

        price = scraper._parse_price(card.get('price') or '')
        old_price = scraper._parse_price(card.get('old_price') or '')
        discount = card.get('discount_percent')
        if discount is None:
            discount = JumiaProduct.compute_discount_percent(price, old_price)

        brand = (card.get('brand') or '')[:120]
        cat_label = (card.get('category') or category_label or '')[:160]
        rating = card_rating
        rating_count = card_review_count
        distribution: dict = {}
        comments_count = 0
        reviews_data: list = []

        need_reviews = with_reviews and (
            existing is None
            or cls._needs_rating_or_reviews_update(
                existing,
                card_rating=card_rating,
                card_review_count=card_review_count,
            )
        )
        if need_reviews:
            if log:
                log(f'        ↳ avis {sku[:20]}…')
            reviews_data, distribution, comments_count = cls._fetch_reviews_safe(
                scraper, sku, log=log,
            )

        return cls._run_orm_safe(
            cls._persist_card_db,
            card=card,
            sku=sku,
            category=category,
            category_label=category_label,
            existing=existing,
            price=price,
            old_price=old_price,
            discount=discount,
            brand=brand,
            cat_label=cat_label,
            rating=rating,
            rating_count=rating_count,
            distribution=distribution,
            comments_count=comments_count,
            reviews_data=reviews_data,
            known_products=known_products,
        )

    @classmethod
    @transaction.atomic
    def _persist_card_db(
        cls,
        *,
        card: dict,
        sku: str,
        category: JumiaCategory | None,
        category_label: str,
        existing: JumiaProduct | None,
        price,
        old_price,
        discount,
        brand: str,
        cat_label: str,
        rating,
        rating_count: int,
        distribution: dict,
        comments_count: int,
        reviews_data: list,
        known_products: dict[str, dict],
    ) -> tuple[int, int, int, int]:
        """Écriture BDD — toujours via ``_run_orm_safe`` depuis le thread crawl."""
        if existing is None:
            obj = JumiaProduct.objects.create(
                sku=sku,
                product_url=card.get('url') or '',
                name=(card.get('name') or '')[:400],
                brand=brand,
                category=cat_label,
                jumia_category=category,
                seller_name='',
                price_xof=price,
                old_price_xof=old_price,
                discount_percent=discount,
                currency='XOF',
                rating_value=rating,
                rating_count=rating_count,
                rating_distribution=distribution or {},
                comments_count=comments_count or len(reviews_data),
                description='',
                image_url='',
            )
            reviews_created = cls._upsert_reviews(obj, reviews_data)
            if reviews_data:
                obj.comments_count = max(obj.comments_count or 0, obj.reviews.count())
                obj.save(update_fields=['comments_count', 'updated_at'])
            known_products[sku] = {
                'sku': sku,
                'rating_value': obj.rating_value,
                'rating_count': obj.rating_count,
                'comments_count': obj.comments_count,
                'jumia_category_id': obj.jumia_category_id,
            }
            return 1, 0, reviews_created, 0

        prev_rating = existing.rating_value
        prev_count = int(existing.rating_count or 0)
        prev_comments = int(existing.comments_count or 0)

        obj = existing
        update_fields = ['updated_at']
        if cls._rating_value_changed(prev_rating, rating):
            obj.rating_value = rating
            update_fields.append('rating_value')
        if rating_count and rating_count != prev_count:
            obj.rating_count = rating_count
            update_fields.append('rating_count')
        if distribution:
            obj.rating_distribution = distribution
            update_fields.append('rating_distribution')
        if comments_count and comments_count != prev_comments:
            obj.comments_count = comments_count
            update_fields.append('comments_count')
        if category and obj.jumia_category_id is None:
            obj.jumia_category = category
            update_fields.append('jumia_category')
        obj.save(update_fields=list(dict.fromkeys(update_fields)))

        reviews_created = cls._upsert_reviews(obj, reviews_data)
        if reviews_data:
            new_count = max(obj.comments_count or 0, obj.reviews.count())
            if new_count != obj.comments_count:
                obj.comments_count = new_count
                obj.save(update_fields=['comments_count', 'updated_at'])

        rating_changed = cls._rating_value_changed(prev_rating, rating)
        count_changed = bool(rating_count and rating_count != prev_count)
        if reviews_created == 0 and not rating_changed and not count_changed:
            return 0, 0, 0, 1
        known_products[sku] = {
            'sku': sku,
            'rating_value': obj.rating_value,
            'rating_count': obj.rating_count,
            'comments_count': obj.comments_count,
            'jumia_category_id': obj.jumia_category_id,
        }
        return 0, 1, reviews_created, 0

    @classmethod
    def _fetch_reviews_safe(
        cls,
        scraper: JumiaScraper,
        sku: str,
        *,
        log: LogCallback | None = None,
    ) -> tuple[list, dict, int]:
        """Avis via endpoint SKU — sans ouvrir la fiche produit complète."""
        try:
            return scraper.fetch_reviews(sku, max_reviews=0, max_pages=0)
        except JumiaScraperError as exc:
            if log:
                log(f'        ↳ avis {sku[:16]} ignorés : {exc}')
            return [], {}, 0
        except Exception as exc:
            logger.warning('Avis SKU=%s : %s', sku, exc)
            if log:
                log(f'        ↳ avis {sku[:16]} erreur : {exc}')
            return [], {}, 0

    @staticmethod
    def _rating_value_changed(old_val, new_val) -> bool:
        if new_val is None:
            return False
        if old_val is None:
            return True
        try:
            return abs(float(old_val) - float(new_val)) >= 0.05
        except (TypeError, ValueError):
            return old_val != new_val

    @classmethod
    def _cache_needs_update(
        cls,
        cached: dict,
        card_rating,
        card_review_count: int,
    ) -> bool:
        if cls._rating_value_changed(cached.get('rating_value'), card_rating):
            return True
        known = max(
            int(cached.get('rating_count') or 0),
            int(cached.get('comments_count') or 0),
        )
        return card_review_count > known

    @classmethod
    def _needs_rating_or_reviews_update(
        cls,
        existing: JumiaProduct,
        *,
        card_rating,
        card_review_count: int,
    ) -> bool:
        if cls._rating_value_changed(existing.rating_value, card_rating):
            return True
        known = max(int(existing.rating_count or 0), int(existing.comments_count or 0))
        if card_review_count > known:
            return True
        return False

    @staticmethod
    def _upsert_reviews(product: JumiaProduct, reviews_data: list) -> int:
        reviews_created = 0
        for rev in reviews_data:
            text_for_hash = rev.comment_text or rev.title
            if not text_for_hash and rev.rating_stars is None:
                continue
            rh = JumiaReview.build_review_hash(
                title=rev.title,
                comment_text=rev.comment_text,
                author=rev.author,
                rating_stars=rev.rating_stars,
            )
            _, rev_created = JumiaReview.objects.get_or_create(
                product=product,
                review_hash=rh,
                defaults={
                    'rating_stars': rev.rating_stars,
                    'title': rev.title or '',
                    'comment_text': rev.comment_text or '',
                    'author': rev.author or '',
                    'review_date': rev.review_date,
                    'verified_purchase': bool(rev.verified_purchase),
                },
            )
            if rev_created:
                reviews_created += 1
        return reviews_created

    # ------------------------------------------------------------------ categories

    @classmethod
    def _upsert_category(
        cls,
        *,
        slug: str,
        path: str,
        parent: JumiaCategory | None,
        name: str = '',
    ) -> JumiaCategory:
        path = path if path.startswith('/') else f'/{path}'
        if not path.endswith('/'):
            path = f'{path}/'
        # Slug unique : dérivé du path pour éviter collisions smartphones multi-parents
        path_slug = slugify(path.strip('/').replace('/', '-')) or slug
        label = name or CATEGORY_LABELS.get(slug) or slug.replace('-', ' ').title()
        url = urljoin(BASE_URL, path)
        obj, _ = JumiaCategory.objects.update_or_create(
            path=path[:200],
            defaults={
                'slug': path_slug[:120],
                'name': label[:200],
                'url': url[:500],
                'parent': parent,
                'is_active': True,
            },
        )
        return obj

    @classmethod
    def _refresh_category_stats(cls, category: JumiaCategory) -> None:
        count = JumiaProduct.objects.filter(jumia_category=category).count()
        JumiaCategory.objects.filter(pk=category.pk).update(
            products_count=count,
            last_crawled_at=timezone.now(),
        )

    @classmethod
    def _discover_root_categories(cls, html: str) -> list[tuple[str, str]]:
        """
        Catégories marketplace racines uniquement — exclut marques (Adidas, Samsung…)
        et pages légales / compte.
        """
        if not html:
            return cls._dedupe_roots(FALLBACK_ROOT_CATEGORIES)

        tree = lxml_html.fromstring(html)
        found: dict[str, str] = {}
        for a in tree.xpath('//a[@href]'):
            href = (a.get('href') or '').strip()
            if not href:
                continue
            parsed = urlparse(urljoin(BASE_URL, href))
            if parsed.netloc and 'jumia' not in parsed.netloc:
                continue
            path = (parsed.path or '').strip('/')
            if not path or '/' in path:
                continue
            slug = slugify(path)
            if not slug or slug not in _KNOWN_ROOT_SLUGS:
                continue
            if any(slug.startswith(s) or slug == s for s in _SKIP_ROOT_SLUGS):
                continue
            label = re.sub(r'\s+', ' ', (a.text_content() or '').strip())[:200]
            if not label or len(label) < 2:
                label = CATEGORY_LABELS.get(slug, slug.replace('-', ' ').title())
            prev = found.get(slug, '')
            if slug not in found or len(label) > len(prev):
                found[slug] = label

        if not found:
            return cls._dedupe_roots(FALLBACK_ROOT_CATEGORIES)
        return cls._dedupe_roots([(s, n) for s, n in found.items()])

    @staticmethod
    def _dedupe_roots(roots: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Déduplique par slug en conservant le libellé le plus explicite."""
        merged: dict[str, str] = {}
        for slug, name in roots:
            prev = merged.get(slug, '')
            if slug not in merged or len(name) > len(prev):
                merged[slug] = name
        return sorted(merged.items(), key=lambda x: CATEGORY_LABELS.get(x[0], x[1]).lower())

    @classmethod
    def _discover_subcategories(
        cls, html: str, parent_slug: str,
    ) -> list[tuple[str, str, str]]:
        """Extrait les liens sous-catégorie sous le path parent (toutes)."""
        tree = lxml_html.fromstring(html)
        found: dict[str, tuple[str, str]] = {}
        parent_prefix = f'/{parent_slug}/'
        # Aussi accepter path parent complet si slug composé
        for a in tree.xpath('//a[@href]'):
            href = (a.get('href') or '').strip()
            if not href:
                continue
            parsed = urlparse(urljoin(BASE_URL, href))
            path = parsed.path or ''
            if parent_prefix not in path and not path.startswith(parent_prefix):
                # Essai : dernier segment du parent dans le path
                if f'/{parent_slug}/' not in path:
                    continue
            if not path.startswith('/'):
                continue
            parts = [p for p in path.strip('/').split('/') if p]
            if len(parts) < 2:
                continue
            # Enfant direct : parent est le préfixe
            try:
                idx = parts.index(parent_slug)
            except ValueError:
                continue
            if idx + 1 >= len(parts):
                continue
            # Un seul niveau sous le parent dans ce lien
            if len(parts) != idx + 2:
                continue
            child_slug = slugify(parts[idx + 1]) or parts[idx + 1]
            if child_slug == parent_slug:
                continue
            child_path = '/' + '/'.join(parts[: idx + 2]) + '/'
            label = (a.text_content() or '').strip() or CATEGORY_LABELS.get(
                child_slug, child_slug.replace('-', ' ').title(),
            )
            found[child_path] = (child_slug, label[:200])
        return [(slug, path, name) for path, (slug, name) in sorted(found.items())]

    @staticmethod
    def _normalize_slug(value: str) -> str:
        raw = (value or '').strip().strip('/')
        raw = re.sub(r'^https?://[^/]+/', '', raw)
        return slugify(raw.replace('/', '-')) or 'telephones-tablettes'

    @staticmethod
    def _report(progress: ProgressCallback | None, pct: int | None, message: str) -> None:
        if not progress:
            return
        try:
            if pct is None:
                progress(-1, message)
            else:
                progress(pct, message)
        except TypeError:
            progress(pct or 0, message)
