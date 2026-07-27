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
    sources: tuple[str, ...] = ('social', 'jiji'),
) -> int:
    """Un cycle : fetch → analyse locale → envoi (réseaux + Jiji)."""
    total_updated = 0

    if 'social' in sources:
        posts = client.fetch_raw_posts(limit=limit)
        if posts:
            results = analyzer.analyze_batch(posts)
            payload = analyzer.to_api_payload(results)
            for item in results[:3]:
                logger.info(
                    'Post #%s | %s | %s',
                    item.post_id, item.category, item.sentiment,
                )
            if not dry_run:
                response = client.submit_analysis(payload)
                total_updated += int(response.get('stats', {}).get('updated', 0))
            else:
                total_updated += len(results)
        else:
            logger.info('Aucune publication sociale en attente.')

    if 'jiji' in sources:
        listings = client.fetch_raw_jiji_listings(limit=limit)
        if listings:
            jiji_results = analyzer.analyze_jiji_batch(listings)
            jiji_payload = analyzer.to_jiji_api_payload(jiji_results)
            for item in jiji_results[:3]:
                logger.info(
                    'Jiji #%s | %s | pertinence %.0f%% | agricole=%s',
                    item.listing_id,
                    item.nlp_category,
                    item.relevance_score * 100,
                    item.is_agricultural,
                )
            if not dry_run:
                response = client.submit_jiji_analysis(jiji_payload)
                total_updated += int(response.get('stats', {}).get('updated', 0))
            else:
                total_updated += len(jiji_results)
        else:
            logger.info('Aucune annonce Jiji en attente NLP.')

    if dry_run and total_updated:
        logger.warning('Mode dry-run : résultats NON envoyés au VPS.')

    return total_updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Client NLP local YAYEMATY — analyse sur Ryzen 7, sync VPS.',
    )
    parser.add_argument('--once', action='store_true', help='Un seul cycle puis quitte.')
    parser.add_argument('--watch', action='store_true', help='Boucle continue.')
    parser.add_argument('--interval', type=int, default=300, help='Secondes entre cycles (défaut: 300).')
    parser.add_argument('--limit', type=int, default=None, help='Max publications par cycle.')
    parser.add_argument('--dry-run', action='store_true', help='Analyse sans envoi au VPS.')
    parser.add_argument(
        '--sources',
        default='social,jiji',
        help='Sources à traiter : social, jiji (défaut: social,jiji).',
    )
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

    sources = tuple(s.strip() for s in args.sources.split(',') if s.strip())

    logger.info('Connexion VPS : %s', config.base_url)

    if not client.health_check():
        logger.error('API inaccessible. Vérifiez YAYEMATY_API_URL et INTELLIGENCE_API_KEY.')
        return 1

    logger.info('API OK — démarrage analyse locale (Ryzen 7).')

    if args.watch:
        while True:
            try:
                run_cycle(
                    client=client,
                    analyzer=analyzer,
                    limit=limit,
                    dry_run=args.dry_run,
                    sources=sources,
                )
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
