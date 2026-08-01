"""Smoke test : seed catalogue Jumia + parcours analyse 100×3."""

import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from decimal import Decimal  # noqa: E402

from intelligence.models import JumiaProduct, JumiaReview  # noqa: E402
from intelligence.services.jumia_catalog_crawl_service import JumiaCatalogCrawlService  # noqa: E402
from intelligence.services.trade_research_collection_service import (  # noqa: E402
    TradeResearchCollectionService,
)


def main() -> int:
    cat = JumiaCatalogCrawlService._upsert_category(
        slug='telephones-tablettes',
        path='/telephones-tablettes/',
        parent=None,
        name='Téléphones & Tablettes',
    )
    print('category', cat.pk, cat.slug, cat.path)

    JumiaProduct.objects.filter(sku__startswith='SKU-SEED-CAT-').delete()
    for i in range(120):
        JumiaProduct.objects.create(
            sku=f'SKU-SEED-CAT-{i:04d}',
            product_url=f'https://www.jumia.sn/seed-iphone-{i}/',
            name=f'iPhone 15 Seed {i}',
            brand='Apple',
            category='Smartphones',
            jumia_category=cat,
            price_xof=Decimal('400000') + i * 1000,
            old_price_xof=Decimal('450000'),
            discount_percent=11.0,
            rating_value=4.2,
            rating_count=20 + i,
            seller_name='Official Store',
        )
    top = JumiaProduct.objects.get(sku='SKU-SEED-CAT-0119')
    JumiaReview.objects.update_or_create(
        product=top,
        review_hash='seed-rev-1',
        defaults={
            'rating_stars': 4,
            'title': 'Bien',
            'comment_text': 'Bon téléphone seed catalogue.',
            'author': 'Test',
            'verified_purchase': True,
        },
    )
    JumiaCatalogCrawlService._refresh_category_stats(cat)
    cat.refresh_from_db()
    print('products_count', cat.products_count)

    tours = []
    for i in range(3):
        r = TradeResearchCollectionService.collect_jumia('iphone', tour_index=i)
        tours.append(r)
        print(
            f"tour {i}: source={r.get('source')} count={r.get('products_count')} "
            f"total={r.get('total_matching')} has_more={r.get('has_more')}"
        )
        assert r.get('source') == 'catalog', r
        assert r.get('products_count', 0) <= 100

    r3 = TradeResearchCollectionService.collect_jumia_from_catalog(
        'iphone', tour_index=3, limit=100,
    )
    print('tour3_count', r3['products_count'])
    assert r3['products_count'] == 0

    payload = TradeResearchCollectionService.aggregate_payload(
        'iphone',
        collect_results={'jumia': tours[-1], 'jumia_tours': tours},
    )
    print('payload_source', payload['jumia']['source'])
    print('payload_tours', payload['jumia']['tours_used'])
    print('payload_scanned', payload['jumia']['products_scanned'])
    print('payload_products', len(payload['jumia']['products']))
    print('payload_reviews', len(payload['jumia']['reviews_sample']))
    assert payload['jumia']['source'] == 'catalog'
    assert payload['jumia']['tours_used'] == 3
    assert payload['jumia']['products_scanned'] == 120
    assert payload['jumia']['reviews_sample']
    print('OK_ANALYSE_CATALOGUE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
