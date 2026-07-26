#!/usr/bin/env python
"""
Boucle d'analyse NLP locale — YAYEMATY MARKET.

Usage :
    python -m local_nlp.runner --once
    python -m local_nlp.runner --watch --interval 300
    python -m local_nlp.runner --dry-run --limit 5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from local_nlp.analyzer import AgriculturalAnalyzer
from local_nlp.api_client import IntelligenceApiClient
from local_nlp.config import ClientConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('local_nlp')


def run_cycle(
    *,
    client: IntelligenceApiClient,
    analyzer: AgriculturalAnalyzer,
    limit: int,
    dry_run: bool = False,
) -> int:
    """Un cycle : fetch → analyse locale → envoi."""
    posts = client.fetch_raw_posts(limit=limit)

    if not posts:
        logger.info('Aucune publication en attente.')
        return 0

    results = analyzer.analyze_batch(posts)
    payload = analyzer.to_api_payload(results)

    for item in results[:5]:
        logger.info(
            'Post #%s | %s | %s | mots-clés: %s',
            item.post_id,
            item.category,
            item.sentiment,
            ', '.join(item.keywords[:4]) or '-',
        )

    if len(results) > 5:
        logger.info('… et %s autre(s) publication(s).', len(results) - 5)

    if dry_run:
        logger.warning('Mode dry-run : résultats NON envoyés au VPS.')
        return len(results)

    response = client.submit_analysis(payload)
    updated = response.get('stats', {}).get('updated', 0)
    logger.info('%s publication(s) analysée(s) et synchronisée(s).', updated)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Client NLP local YAYEMATY — analyse sur Ryzen 7, sync VPS.',
    )
    parser.add_argument('--once', action='store_true', help='Un seul cycle puis quitte.')
    parser.add_argument('--watch', action='store_true', help='Boucle continue.')
    parser.add_argument('--interval', type=int, default=300, help='Secondes entre cycles (défaut: 300).')
    parser.add_argument('--limit', type=int, default=None, help='Max publications par cycle.')
    parser.add_argument('--dry-run', action='store_true', help='Analyse sans envoi au VPS.')
    args = parser.parse_args(argv)

    if not args.once and not args.watch:
        args.once = True

    try:
        config = ClientConfig.from_env()
    except ValueError as exc:
        logger.error(str(exc))
        return 1

    client = IntelligenceApiClient(config)
    analyzer = AgriculturalAnalyzer()
    limit = args.limit or config.batch_limit

    logger.info('Connexion VPS : %s', config.base_url)

    if not client.health_check():
        logger.error('API inaccessible. Vérifiez YAYEMATY_API_URL et INTELLIGENCE_API_KEY.')
        return 1

    logger.info('API OK — démarrage analyse locale (Ryzen 7).')

    if args.watch:
        while True:
            try:
                run_cycle(client=client, analyzer=analyzer, limit=limit, dry_run=args.dry_run)
            except Exception as exc:
                logger.exception('Erreur cycle : %s', exc)
            logger.info('Prochain cycle dans %ss…', args.interval)
            time.sleep(args.interval)
    else:
        try:
            run_cycle(client=client, analyzer=analyzer, limit=limit, dry_run=args.dry_run)
        except Exception as exc:
            logger.exception('Erreur : %s', exc)
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
