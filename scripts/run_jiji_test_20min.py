"""Test Jiji mode test — durée max 20 minutes."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')

import django

django.setup()

from intelligence.collection_config import TEST_MODE_OVERRIDES
from intelligence.models import JijiListing, MarketSearchKeyword, TestJijiListing
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.jiji_collection_service import JijiCollectionService
from intelligence.services.test_data_purge_service import TestDataPurgeService

MAX_SECONDS = int(TEST_MODE_OVERRIDES.get('TEST_SESSION_MINUTES', 20)) * 60


def main() -> int:
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    print('=== TEST JIJI — mode test (max 20 min) ===')
    print(f'Début : {datetime.now().isoformat(timespec="seconds")}')
    print('Mots-clés :', list(
        MarketSearchKeyword.objects.filter(is_active=True).values_list('keyword', 'max_videos')
    ))
    prod_before = JijiListing.objects.count()
    TestDataPurgeService.purge_all()

    def should_cancel() -> bool:
        return time.monotonic() >= deadline

    def progress(pct: int, message: str, phase: str = 'collecte') -> None:
        print(f'[{time.monotonic() - started:5.1f}s] {pct:3d}% {message}')

    token = set_collection_context(CollectionRunContext.test())
    try:
        result = JijiCollectionService.run(
            progress=progress,
            should_cancel=should_cancel,
            test_mode=True,
        )
    finally:
        reset_collection_context(token)

    report = {
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'result': {
            'success': result.get('success'),
            'message': result.get('message'),
            'listings_created': result.get('listings_created'),
            'keywords': result.get('keywords'),
            'errors': result.get('errors'),
            'requests': result.get('requests'),
        },
        'isolation': {
            'prod_before': prod_before,
            'prod_after': JijiListing.objects.count(),
            'prod_unchanged': prod_before == JijiListing.objects.count(),
            'test_listings': TestJijiListing.objects.count(),
        },
        'sample': list(TestJijiListing.objects.values(
            'title', 'price_xof', 'condition', 'location_area',
            'views_count', 'seller_name', 'search_keyword', 'is_negotiable',
        )[:12]),
    }
    out = os.path.join(os.path.dirname(__file__), 'jiji_test_report.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print('Rapport :', out)
    return 0 if result.get('success') or report['isolation']['test_listings'] > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
