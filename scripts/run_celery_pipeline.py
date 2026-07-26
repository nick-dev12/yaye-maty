"""Invoke Celery pipeline steps and wait for results."""
import json
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')

import django

django.setup()

from intelligence.models import MarketSearchKeyword
from intelligence.tasks import (
    analyze_pending_social_nlp,
    generate_top_purchase_recommendations,
    ping_celery,
    scrape_market_search_keywords,
)


def main():
    print('Ping Celery...')
    ping = ping_celery.delay()
    print('  ', ping.get(timeout=30))

    keywords = list(MarketSearchKeyword.objects.filter(is_active=True).order_by('keyword')[:2])
    for kw in keywords:
        kw.max_videos = 5
        kw.save(update_fields=['max_videos', 'updated_at'])

    for kw in keywords:
        print(f'Scrape Celery keyword_id={kw.pk} ({kw.keyword})...')
        task = scrape_market_search_keywords.delay(keyword_id=kw.pk)
        result = task.get(timeout=1800)
        print(json.dumps(result, indent=2, ensure_ascii=True))

    print('NLP Celery...')
    nlp = analyze_pending_social_nlp.delay(comment_limit=200, post_limit=100)
    print(json.dumps(nlp.get(timeout=900), indent=2, ensure_ascii=True, default=str))

    print('Top 10 Celery...')
    top = generate_top_purchase_recommendations.delay(window_days=7)
    print(json.dumps(top.get(timeout=120), indent=2, ensure_ascii=True, default=str))

    print('DONE')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
