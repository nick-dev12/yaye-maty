"""
Test Jumia mode test — durée max 20 minutes (aligné page Collecte test), rapport détaillé.

Volume par mot-clé = max_videos / max_comments définis dans Paramètres → Recherche.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')

import django

django.setup()

from intelligence.collection_config import TEST_MODE_OVERRIDES, get_effective_collection_config
from intelligence.models import (
    JumiaProduct,
    JumiaReview,
    MarketSearchKeyword,
    TestJumiaProduct,
    TestJumiaReview,
)
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.jumia_collection_service import JumiaCollectionService
from intelligence.services.test_data_purge_service import TestDataPurgeService

MAX_SECONDS = int(TEST_MODE_OVERRIDES.get('TEST_SESSION_MINUTES', 20)) * 60


def main() -> int:
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    config = get_effective_collection_config(test_mode=True)

    print('=== TEST JUMIA — mode test (max 20 min) ===')
    print(f'Début : {datetime.now().isoformat(timespec="seconds")}')
    print(f'Session : {MAX_SECONDS // 60} min · plafond session vidéos/produits = '
          f'{config.get("MAX_VIDEOS_PER_KEYWORD_SESSION")}')

    active_kw = list(
        MarketSearchKeyword.objects.filter(is_active=True).values(
            'keyword', 'max_videos', 'max_comments',
        )
    )
    print(f'Mots-clés actifs Paramètres : {active_kw}')

    prod_before = {
        'products': JumiaProduct.objects.count(),
        'reviews': JumiaReview.objects.count(),
    }
    print(f'Prod avant : {prod_before}')

    purged = TestDataPurgeService.purge_all()
    print(f'Purge tables test : {purged}')

    cancelled_flag = {'value': False}

    def should_cancel() -> bool:
        if time.monotonic() >= deadline:
            cancelled_flag['value'] = True
            return True
        return False

    def progress(pct: int, message: str, phase: str = 'collecte') -> None:
        elapsed = time.monotonic() - started
        print(f'[{elapsed:5.1f}s] {pct:3d}% ({phase}) {message}')

    token = set_collection_context(CollectionRunContext.test())
    try:
        result = JumiaCollectionService.run(
            progress=progress,
            should_cancel=should_cancel,
            test_mode=True,
        )
    finally:
        reset_collection_context(token)

    elapsed = time.monotonic() - started
    test_products = list(
        TestJumiaProduct.objects.all().values(
            'sku', 'name', 'search_keyword', 'price_xof',
            'rating_value', 'rating_count', 'comments_count',
            'category', 'seller_name', 'availability', 'brand',
            'discount_percent', 'stock_status',
        )
    )
    test_reviews = list(
        TestJumiaReview.objects.select_related('product').all()[:25]
    )
    reviews_sample = [
        {
            'stars': r.rating_stars,
            'title': r.title,
            'text': (r.comment_text or '')[:160],
            'author': r.author,
            'date': str(r.review_date) if r.review_date else None,
            'verified': r.verified_purchase,
            'product': r.product.name[:60] if r.product_id else None,
            'keyword': r.product.search_keyword if r.product_id else None,
        }
        for r in test_reviews
    ]

    prod_after = {
        'products': JumiaProduct.objects.count(),
        'reviews': JumiaReview.objects.count(),
    }

    by_kw = {}
    for p in TestJumiaProduct.objects.all():
        by_kw.setdefault(p.search_keyword or '—', {'products': 0, 'reviews': 0})
        by_kw[p.search_keyword or '—']['products'] += 1
    for r in TestJumiaReview.objects.select_related('product'):
        k = r.product.search_keyword if r.product_id else '—'
        by_kw.setdefault(k or '—', {'products': 0, 'reviews': 0})
        by_kw[k or '—']['reviews'] += 1

    report = {
        'elapsed_seconds': round(elapsed, 1),
        'time_limit_hit': cancelled_flag['value'],
        'session_minutes': MAX_SECONDS // 60,
        'job_result': {
            'success': result.get('success'),
            'message': result.get('message'),
            'nouvelles_donnees': result.get('nouvelles_donnees'),
            'products_created': result.get('products_created'),
            'products_updated': result.get('products_updated'),
            'reviews_created': result.get('reviews_created'),
            'keywords': result.get('keywords'),
            'errors': result.get('errors'),
            'requests': result.get('requests'),
        },
        'isolation': {
            'prod_before': prod_before,
            'prod_after': prod_after,
            'prod_unchanged': prod_before == prod_after,
            'test_products_count': TestJumiaProduct.objects.count(),
            'test_reviews_count': TestJumiaReview.objects.count(),
        },
        'by_keyword': by_kw,
        'products_sample': [
            {
                'sku': p['sku'],
                'name': (p['name'] or '')[:80],
                'keyword': p['search_keyword'],
                'brand': p.get('brand'),
                'price': str(p['price_xof']) if p['price_xof'] is not None else None,
                'discount': p.get('discount_percent'),
                'stock': p.get('stock_status'),
                'rating': p['rating_value'],
                'rating_count': p['rating_count'],
            }
            for p in test_products[:15]
        ],
        'reviews_sample': reviews_sample,
        'ratings_coverage': {
            'products_with_rating': TestJumiaProduct.objects.exclude(rating_value__isnull=True).count(),
            'reviews_with_stars': TestJumiaReview.objects.exclude(rating_stars__isnull=True).count(),
            'verified_reviews': TestJumiaReview.objects.filter(verified_purchase=True).count(),
        },
    }

    out_path = os.path.join(os.path.dirname(__file__), 'jumia_test_report.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print('\n=== RAPPORT ===')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'\nRapport écrit : {out_path}')
    print(f'Durée : {elapsed:.1f}s / {MAX_SECONDS}s')
    return 0 if result.get('success') or report['isolation']['test_products_count'] > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
