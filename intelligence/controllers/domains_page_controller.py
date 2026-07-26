"""
Contrôleur page Domaines — gestion Google Trends + configuration découverte.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from intelligence.constants import MAX_DOMAINS_PER_DISCOVERY
from intelligence.forms.market_domain_forms import DiscoveryConfigForm, MarketDomainForm
from intelligence.models import MarketDomain
from intelligence.services.discovery_config_service import DiscoveryConfigService
from intelligence.services.domains_display_service import DomainsDisplayService


class DomainsPageController:
    """Page dédiée domaines de recherche (ex-Paramètres domaines + découverte)."""

    def __init__(self, request):
        self.request = request

    def index(self):
        if self.request.method == 'POST':
            action = self.request.POST.get('action', '')
            if action == 'add_domain':
                return self._handle_add_domain()
            if action == 'delete_domain':
                return self._handle_delete_domain()
            if action == 'save_config':
                return self._handle_save_config()
            if action == 'run_discovery':
                return self._handle_run_discovery()
            messages.error(self.request, 'Action non reconnue.')
        return self._render_page()

    def _redirect(self, anchor: str = '') -> HttpResponseRedirect:
        url = reverse('intelligence:domaines')
        if anchor:
            url += f'#{anchor}'
        return HttpResponseRedirect(url)

    def _handle_add_domain(self):
        form = MarketDomainForm(self.request.POST)
        if not form.is_valid():
            messages.error(self.request, 'Corrigez les erreurs du formulaire domaine.')
            return self._render_page(domain_form=form, show_add_form=True, anchor='gestion')

        domain = form.save()
        category_name = form.resolved_category_name or f'cat. {domain.cat_id}'
        messages.success(
            self.request,
            f'Domaine « {domain.label} » ajouté (Google Trends : {category_name}).',
        )
        return self._redirect('gestion')

    def _handle_delete_domain(self):
        domain = get_object_or_404(MarketDomain, pk=self.request.POST.get('domain_id'))
        label = domain.label
        domain.delete()
        messages.success(self.request, f'Domaine « {label} » supprimé.')
        return self._redirect('gestion')

    def _handle_save_config(self):
        config_form = DiscoveryConfigForm(self.request.POST)
        if not config_form.is_valid():
            messages.error(self.request, 'Corrigez les erreurs de configuration.')
            return self._render_page(config_form=config_form, anchor='decouverte')

        DiscoveryConfigService.save_config(
            selected_domains=config_form.cleaned_data['selected_domains'],
            timeframe=config_form.cleaned_data['timeframe'],
            region=config_form.cleaned_data['region'],
        )
        messages.success(
            self.request,
            'Configuration enregistrée. Vous pouvez lancer une découverte ci-dessous.',
        )
        return self._redirect('decouverte')

    def _handle_run_discovery(self):
        try:
            stats = DiscoveryConfigService.run_discovery()
        except (ValueError, RuntimeError) as exc:
            messages.error(self.request, str(exc))
            return self._redirect('decouverte')

        messages.success(
            self.request,
            f'Découverte réussie — {stats["total"]} requête(s) enregistrée(s).',
        )
        return HttpResponseRedirect(reverse('intelligence:index') + '#decouvertes')

    def _render_page(
        self,
        domain_form=None,
        config_form=None,
        show_add_form=False,
        anchor='',
    ):
        if domain_form is None:
            domain_form = MarketDomainForm()
        if config_form is None:
            config = DiscoveryConfigService.get_config()
            config_form = DiscoveryConfigForm(initial={
                'timeframe': config.timeframe,
                'region': config.region,
                'selected_domains': config.selected_domains.all(),
            })

        if self.request.GET.get('show_form') == '1':
            show_add_form = True

        domain_data = DomainsDisplayService.build_context()
        context = {
            **domain_data,
            'domain_form': domain_form,
            'config_form': config_form,
            'show_add_form': show_add_form,
            'market_domains': DiscoveryConfigService.get_active_domains(),
            'max_domains': MAX_DOMAINS_PER_DISCOVERY,
            'active_anchor': self.request.GET.get('section') or anchor,
            'user': self.request.user,
        }
        return render(self.request, 'dashboard/intelligence/domains.html', context)
