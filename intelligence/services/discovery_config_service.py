from typing import Callable

from intelligence.constants import MAX_DOMAINS_PER_DISCOVERY
from intelligence.controllers.domain_discovery_controller import DomainDiscoveryController
from intelligence.models import DiscoveryConfig, MarketDomain

ShouldCancelCallback = Callable[[], bool]
ProgressHook = Callable[[str], None]


class DiscoveryConfigService:
    """Gestion de la configuration et lancement de la découverte."""

    @classmethod
    def get_config(cls) -> DiscoveryConfig:
        return DiscoveryConfig.get_config()

    @classmethod
    def get_active_domains(cls):
        return MarketDomain.objects.filter(is_active=True).order_by('label')

    @classmethod
    def save_config(cls, *, selected_domains, timeframe: str, region: str) -> DiscoveryConfig:
        config = cls.get_config()
        config.timeframe = timeframe
        config.region = region
        config.save()
        config.selected_domains.set(selected_domains)
        return config

    @classmethod
    def get_selected_domain_slugs(cls) -> list[str]:
        config = cls.get_config()
        return list(
            config.selected_domains.filter(is_active=True)
            .values_list('slug', flat=True)
        )

    @classmethod
    def run_discovery(
        cls,
        *,
        should_cancel: ShouldCancelCallback | None = None,
        on_progress: ProgressHook | None = None,
    ) -> dict:
        """
        Lance la découverte selon la configuration enregistrée.

        Raises:
            RuntimeError: Si aucun domaine n'est configuré.
            DomainDiscoveryCancelled: Si l'utilisateur demande l'arrêt.
        """
        config = cls.get_config()
        domains = list(config.selected_domains.filter(is_active=True))

        if not domains:
            raise RuntimeError(
                'Aucun domaine sélectionné. Configurez les domaines dans Intelligence → Domaines.'
            )

        if len(domains) > MAX_DOMAINS_PER_DISCOVERY:
            domains = domains[:MAX_DOMAINS_PER_DISCOVERY]

        slugs = [d.slug for d in domains]
        return DomainDiscoveryController(
            should_cancel=should_cancel,
            on_progress=on_progress,
        ).discover_domains(
            slugs,
            timeframe=config.timeframe,
            region=config.region,
        )

    @classmethod
    def get_domain_map(cls) -> dict[str, MarketDomain]:
        return {d.slug: d for d in MarketDomain.objects.filter(is_active=True)}
