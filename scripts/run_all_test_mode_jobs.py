"""
Lance tous les jobs mode test (équivalent UI) via Celery et audite l'isolation.
Usage: python scripts/run_all_test_mode_jobs.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')
django.setup()

from django.conf import settings

from intelligence.models import (
    MarketSearchKeyword,
    SocialPost,
    TestDiscoveredQuery,
    TestSocialComment,
    TestSocialPost,
    TestTopPurchaseRecommendation,
    TopPurchaseRecommendation,
)
from intelligence.services.collection_run_context import CollectionRunContext, set_collection_context
from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService
from intelligence.services.test_data_purge_service import TestDataPurgeService
from intelligence.tasks import lancer_collecte_manuelle, ping_celery

JOB_TIMEOUT_SECONDS = 21 * 60  # 20 min session + marge

JOBS = [
    ('google', 'Google Trends'),
    ('social', 'Réseaux sociaux'),
    ('nlp', 'Analyse NLP'),
    ('keyword', 'Mot-clé TikTok'),
    ('full', 'Pipeline complet'),
]


def check_redis() -> None:
    import redis

    client = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=5)
    if not client.ping():
        raise RuntimeError('Redis ne répond pas')


def check_worker() -> None:
    result = ping_celery.delay()
    payload = result.get(timeout=30)
    print(f'Worker Celery OK: {payload}')


def prod_snapshot() -> dict:
    return {
        'posts': SocialPost.objects.count(),
        'top10': TopPurchaseRecommendation.objects.count(),
    }


def test_snapshot() -> dict:
    return {
        'posts': TestSocialPost.objects.count(),
        'comments': TestSocialComment.objects.count(),
        'discovered': TestDiscoveredQuery.objects.count(),
        'top10': TestTopPurchaseRecommendation.objects.count(),
    }


def run_job(job: str, *, keyword_id: int | None = None) -> dict:
    print(f'\n--- Job: {job} (test_mode=True) ---')
    print(f'Heure: {datetime.now().strftime("%H:%M:%S")}')
    prod_before = prod_snapshot()
    TestDataPurgeService.purge_all()

    started = time.monotonic()
    async_result = lancer_collecte_manuelle.delay(
        job=job,
        keyword_id=keyword_id,
        test_mode=True,
    )
    print(f'Task ID: {async_result.id}')

    try:
        payload = async_result.get(timeout=JOB_TIMEOUT_SECONDS)
    except Exception as exc:
        elapsed = time.monotonic() - started
        return {
            'job': job,
            'ok': False,
            'error': str(exc),
            'elapsed_s': round(elapsed, 1),
            'task_id': async_result.id,
        }

    elapsed = time.monotonic() - started
    prod_after = prod_snapshot()
    test_after = test_snapshot()

    isolation_ok = prod_before == prod_after
    return {
        'job': job,
        'ok': True,
        'elapsed_s': round(elapsed, 1),
        'elapsed_min': round(elapsed / 60, 1),
        'task_id': async_result.id,
        'result': payload,
        'prod_unchanged': isolation_ok,
        'prod_before': prod_before,
        'prod_after': prod_after,
        'test_data': test_after,
    }


def main() -> int:
    print('=== Test E2E — tous les jobs mode test ===')
    check_redis()
    print('Redis OK')
    check_worker()

    keyword = MarketSearchKeyword.objects.filter(is_active=True).order_by('keyword').first()
    if not keyword:
        print('WARN: aucun mot-clé actif — job keyword ignoré')
        keyword_id = None
    else:
        keyword_id = keyword.pk
        print(f'Mot-clé test: {keyword.keyword} (id={keyword_id})')

    results = []
    total_start = time.monotonic()

    for job_id, label in JOBS:
        if job_id == 'keyword' and not keyword_id:
            results.append({'job': job_id, 'ok': False, 'error': 'Pas de mot-clé actif'})
            continue
        kw = keyword_id if job_id == 'keyword' else None
        print(f'\n>>> Lancement: {label}')
        result = run_job(job_id, keyword_id=kw)
        results.append(result)
        status = 'OK' if result.get('ok') else 'ECHEC'
        print(f'<<< {label}: {status} ({result.get("elapsed_min", "?")} min)')
        if result.get('ok'):
            print(f'    Prod inchangé: {result.get("prod_unchanged")}')
            print(f'    Données test: {result.get("test_data")}')
        else:
            print(f'    Erreur: {result.get("error")}')

    total_elapsed = time.monotonic() - total_start

    # Audit final page Données test (contexte test)
    token = set_collection_context(CollectionRunContext.test())
    try:
        top_display = PurchaseRecommendationService.get_top_for_display(limit=10)
    finally:
        from intelligence.services.collection_run_context import reset_collection_context
        reset_collection_context(token)

    summary = {
        'total_elapsed_min': round(total_elapsed / 60, 1),
        'jobs': results,
        'final_test_tables': test_snapshot(),
        'final_prod': prod_snapshot(),
        'top10_test_display_count': len(top_display),
    }

    print('\n=== RÉSUMÉ FINAL ===')
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    failed = [r for r in results if not r.get('ok')]
    if failed:
        print(f'\n{len(failed)} job(s) en échec.')
        return 1

    if not all(r.get('prod_unchanged') for r in results if r.get('ok')):
        print('\nWARN: pollution prod détectée sur au moins un job.')
        return 1

    print('\nTous les jobs mode test terminés avec succès.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
