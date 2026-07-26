"""
Commande Django : découverte Bottom-Up par domaine Google Trends.

Usage :
    python manage.py discover_domains
    python manage.py discover_domains --domains agriculture elevage
"""

from django.core.management.base import BaseCommand, CommandError

from intelligence.constants import DEFAULT_REGION, DEFAULT_TIMEFRAME
from intelligence.controllers.domain_discovery_controller import DomainDiscoveryController
from intelligence.models import MarketDomain
from intelligence.services.discovery_config_service import DiscoveryConfigService


class Command(BaseCommand):
    help = 'Découvre les requêtes populaires par domaine via Google Trends.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--domains',
            nargs='+',
            default=None,
            help='Slugs des domaines (défaut : configuration enregistrée).',
        )
        parser.add_argument(
            '--timeframe',
            default=None,
            help='Période Google Trends (défaut : configuration enregistrée).',
        )
        parser.add_argument(
            '--region',
            default=None,
            help='Code pays ISO (défaut : configuration enregistrée).',
        )

    def handle(self, *args, **options):
        config = DiscoveryConfigService.get_config()
        slugs = options['domains']
        timeframe = options['timeframe'] or config.timeframe
        region = options['region'] or config.region

        if not slugs:
            slugs = DiscoveryConfigService.get_selected_domain_slugs()

        if not slugs:
            raise CommandError(
                'Aucun domaine configuré. Ajoutez des domaines dans Intelligence → Domaines.'
            )

        labels = list(
            MarketDomain.objects.filter(slug__in=slugs).values_list('label', flat=True)
        )
        self.stdout.write(
            self.style.NOTICE(
                f'Découverte — {len(slugs)} domaine(s), région {region}, période {timeframe}'
            )
        )
        self.stdout.write(f'Domaines : {", ".join(labels)}')

        try:
            stats = DomainDiscoveryController().discover_domains(
                slugs,
                timeframe=timeframe,
                region=region,
            )
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f'Terminé — {stats["total"]} requête(s), '
                f'{stats["created"]} nouvelle(s), {stats["updated"]} mise(s) à jour.'
            )
        )
