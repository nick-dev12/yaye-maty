"""

Contrôleur de la page Paramètres.

"""



from django.contrib import messages

from django.http import HttpResponseRedirect

from django.shortcuts import get_object_or_404, render

from django.urls import reverse



from intelligence.constants import MAX_DOMAINS_PER_DISCOVERY

from intelligence.forms.market_search_forms import (
    MarketplaceKeywordForm,
    SocialMarketSearchKeywordForm,
)

from intelligence.forms.wolof_keyword_forms import WolofKeywordForm

from intelligence.models import DiscoveredQuery, MarketSearchKeyword, TrendRecord, WolofKeyword

from intelligence.services.discovery_config_service import DiscoveryConfigService

from intelligence.services.wolof_dictionary_service import WolofDictionaryService





class SettingsPageController:

    """Configuration des domaines, découverte et dictionnaire Wolof."""



    SECTIONS = [
        {'id': 'wolof', 'label': 'Dictionnaire Wolof', 'icon': 'wolof'},
        {'id': 'recherche', 'label': 'Mots-clés réseaux', 'icon': 'search'},
        {'id': 'marche', 'label': 'Mots-clés marketplace', 'icon': 'market'},
        {'id': 'sources', 'label': 'Sources de données', 'icon': 'sources'},
        {'id': 'compte', 'label': 'Compte', 'icon': 'account'},
    ]



    WOLOF_INTENT_LABELS = {

        WolofKeyword.Intent.PURCHASE: "Intention d'achat",

        WolofKeyword.Intent.INFO: "Demande d'information",

        WolofKeyword.Intent.COMPLAINT: 'Plainte',

    }



    def __init__(self, request):

        self.request = request



    def index(self):

        legacy_section = self.request.GET.get('section', '')
        if legacy_section == 'domaines':
            return HttpResponseRedirect(reverse('intelligence:domaines') + '#gestion')
        if legacy_section == 'decouverte':
            return HttpResponseRedirect(reverse('intelligence:domaines') + '#decouverte')

        if self.request.method == 'POST':
            action = self.request.POST.get('action', '')
            if action in ('add_domain', 'delete_domain', 'save_config', 'run_discovery'):
                messages.info(
                    self.request,
                    'La gestion des domaines a été déplacée vers Intelligence → Domaines.',
                )
                anchor = 'decouverte' if action in ('save_config', 'run_discovery') else 'gestion'
                return HttpResponseRedirect(reverse('intelligence:domaines') + f'#{anchor}')

            if action == 'add_wolof_keyword':

                return self._handle_add_wolof_keyword()

            if action == 'delete_wolof_keyword':

                return self._handle_delete_wolof_keyword()

            if action == 'toggle_wolof_keyword':

                return self._handle_toggle_wolof_keyword()

            if action == 'add_search_keyword':
                return self._handle_add_search_keyword()

            if action in ('add_jumia_keyword', 'add_jiji_keyword', 'add_marketplace_keyword'):
                return self._handle_add_marketplace_keyword()

            if action == 'delete_search_keyword':
                return self._handle_delete_search_keyword()

            if action == 'toggle_search_keyword':
                return self._handle_toggle_search_keyword()

            messages.error(self.request, 'Action non reconnue.')

            return self._render_page()



        return self._render_page()



    def _handle_add_wolof_keyword(self):

        form = WolofKeywordForm(self.request.POST)

        if not form.is_valid():

            messages.error(self.request, 'Corrigez les erreurs du formulaire Wolof.')

            return self._render_page(wolof_form=form, section='wolof', show_wolof_form=True)



        keyword = form.save()

        WolofDictionaryService.invalidate_cache()

        messages.success(

            self.request,

            f'Expression « {keyword.expression} » ajoutée au dictionnaire Wolof.',

        )

        return HttpResponseRedirect(reverse('settings') + '?section=wolof')



    def _handle_delete_wolof_keyword(self):

        keyword_id = self.request.POST.get('keyword_id')

        keyword = get_object_or_404(WolofKeyword, pk=keyword_id)

        expression = keyword.expression

        keyword.delete()

        WolofDictionaryService.invalidate_cache()

        messages.success(self.request, f'Expression « {expression} » supprimée.')

        return HttpResponseRedirect(reverse('settings') + '?section=wolof')



    def _handle_toggle_wolof_keyword(self):

        keyword_id = self.request.POST.get('keyword_id')

        keyword = get_object_or_404(WolofKeyword, pk=keyword_id)

        keyword.is_active = not keyword.is_active

        keyword.save(update_fields=['is_active', 'updated_at'])

        WolofDictionaryService.invalidate_cache()

        state = 'activée' if keyword.is_active else 'désactivée'

        messages.success(self.request, f'Expression « {keyword.expression} » {state}.')

        return HttpResponseRedirect(reverse('settings') + '?section=wolof')



    def _handle_add_search_keyword(self):
        form = SocialMarketSearchKeywordForm(self.request.POST)
        if not form.is_valid():
            messages.error(self.request, 'Corrigez les erreurs du formulaire réseaux.')
            return self._render_page(search_form=form, section='recherche', show_search_form=True)

        keyword = form.save()
        messages.success(
            self.request,
            f'Mot-clé réseau « {keyword.keyword} » ajouté ({keyword.get_platform_display()}).',
        )
        return HttpResponseRedirect(reverse('settings') + '?section=recherche')

    def _handle_add_marketplace_keyword(self):
        form = MarketplaceKeywordForm(self.request.POST, prefix='marketplace')
        if not form.is_valid():
            messages.error(self.request, 'Corrigez les erreurs du formulaire marketplace.')
            return self._render_page(
                marketplace_form=form,
                section='marche',
                show_marketplace_form=True,
            )

        keyword = form.save()
        messages.success(
            self.request,
            f'Mot-clé marketplace « {keyword.keyword} » — '
            f'{keyword.max_videos} résultat(s) par plateforme (Jumia + Jiji).',
        )
        return HttpResponseRedirect(reverse('settings') + '?section=marche')



    def _handle_delete_search_keyword(self):
        keyword_id = self.request.POST.get('keyword_id')
        keyword = get_object_or_404(MarketSearchKeyword, pk=keyword_id)
        label = keyword.keyword
        section = self._keyword_settings_section(keyword)
        keyword.delete()
        messages.success(self.request, f'Mot-clé « {label} » supprimé.')
        return HttpResponseRedirect(reverse('settings') + f'?section={section}')

    def _handle_toggle_search_keyword(self):
        keyword_id = self.request.POST.get('keyword_id')
        keyword = get_object_or_404(MarketSearchKeyword, pk=keyword_id)
        keyword.is_active = not keyword.is_active
        keyword.save(update_fields=['is_active', 'updated_at'])
        state = 'activé' if keyword.is_active else 'désactivé'
        section = self._keyword_settings_section(keyword)
        messages.success(self.request, f'Mot-clé « {keyword.keyword} » {state}.')
        return HttpResponseRedirect(reverse('settings') + f'?section={section}')

    @staticmethod
    def _keyword_settings_section(keyword: MarketSearchKeyword) -> str:
        if keyword.is_marketplace:
            return 'marche'
        return 'recherche'



    def _render_page(
        self,
        wolof_form=None,
        search_form=None,
        marketplace_form=None,
        section='wolof',
        show_wolof_form=False,
        show_search_form=False,
        show_marketplace_form=False,
    ):
        if wolof_form is None:
            wolof_form = WolofKeywordForm()
        if search_form is None:
            search_form = SocialMarketSearchKeywordForm()
        if marketplace_form is None:
            marketplace_form = MarketplaceKeywordForm(prefix='marketplace')



        active_section = self.request.GET.get('section', section)
        if active_section in ('domaines', 'decouverte'):
            active_section = 'wolof'

        if self.request.GET.get('show_wolof_form') == '1':

            show_wolof_form = True

        if self.request.GET.get('show_search_form') == '1':
            show_search_form = True
        if self.request.GET.get('show_marketplace_form') == '1':
            show_marketplace_form = True
        if self.request.GET.get('show_jumia_form') == '1':
            show_marketplace_form = True
        if self.request.GET.get('show_jiji_form') == '1':
            show_marketplace_form = True

        wolof_grouped = WolofDictionaryService.get_all_grouped()
        wolof_sections = [
            {
                'intent': intent,
                'label': self.WOLOF_INTENT_LABELS[intent],
                'keywords': wolof_grouped.get(intent, []),
            }
            for intent in WolofKeyword.Intent.values
        ]

        social_keywords = MarketSearchKeyword.objects.filter(
            platform__in=(
                MarketSearchKeyword.Platform.TIKTOK,
                MarketSearchKeyword.Platform.FACEBOOK,
            ),
        ).order_by('-is_active', 'keyword')
        from intelligence.services.active_keyword_service import ActiveKeywordService

        marketplace_keywords = MarketSearchKeyword.objects.filter(
            platform__in=ActiveKeywordService.MARKETPLACE_PLATFORMS,
        ).order_by('-is_active', 'keyword')

        search_stats = {
            'total': social_keywords.count(),
            'active': social_keywords.filter(is_active=True).count(),
        }
        marketplace_active = ActiveKeywordService.count_marketplace()
        market_stats = {
            'marketplace_total': marketplace_keywords.count(),
            'marketplace_active': marketplace_active,
            'jumia_total': marketplace_active,
            'jumia_active': marketplace_active,
            'jiji_total': marketplace_active,
            'jiji_active': marketplace_active,
        }

        context = {
            'sections': self.SECTIONS,
            'active_section': active_section,
            'wolof_form': wolof_form,
            'search_form': search_form,
            'marketplace_form': marketplace_form,
            'show_wolof_form': show_wolof_form,
            'show_search_form': show_search_form,
            'show_marketplace_form': show_marketplace_form,
            'market_domains': DiscoveryConfigService.get_active_domains(),
            'max_domains': MAX_DOMAINS_PER_DISCOVERY,
            'trend_count': TrendRecord.objects.count(),
            'discovered_count': DiscoveredQuery.objects.count(),
            'wolof_stats': WolofDictionaryService.get_stats(),
            'wolof_sections': wolof_sections,
            'wolof_intent_labels': self.WOLOF_INTENT_LABELS,
            'search_keywords': social_keywords,
            'search_stats': search_stats,
            'marketplace_keywords': marketplace_keywords,
            'market_stats': market_stats,
            'data_sources': self._get_data_sources(),
            'user': self.request.user,
        }

        return render(self.request, 'dashboard/settings/index.html', context)



    def _get_data_sources(self):

        return [

            {

                'name': 'Google Trends',

                'tool': 'pytrends',

                'status': 'active',

                'status_label': 'Actif',

                'description': 'Scores de recherche 0-100 pour le Sénégal (SN).',

            },

            {

                'name': 'Découverte par domaine',

                'tool': 'pytrends related_queries',

                'status': 'active',

                'status_label': 'Actif',

                'description': 'Domaines configurables en base (catégories Google).',

            },

            {

                'name': 'Réseaux sociaux',

                'tool': 'Playwright Stealth',

                'status': 'active',

                'status_label': 'Configuré',

                'description': 'Scraping Top-Down TikTok (recherche par mot-clé) + pipeline NLP hybride.',

            },

            {

                'name': 'NLP hybride Wolof + CamemBERT',

                'tool': 'Celery + filtres locaux',

                'status': 'active',

                'status_label': 'Configuré',

                'description': 'Dictionnaire Wolof configurable ci-dessous, puis CamemBERT sur le VPS.',

            },

        ]


