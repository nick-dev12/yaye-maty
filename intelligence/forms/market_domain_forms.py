from django import forms

from intelligence.constants import MAX_DOMAINS_PER_DISCOVERY, DEFAULT_REGION, DEFAULT_TIMEFRAME
from intelligence.models import DiscoveryConfig, MarketDomain
from intelligence.services.google_trends_category_service import GoogleTrendsCategoryService


class MarketDomainForm(forms.ModelForm):
    """Ajout d'un domaine : seul le nom est saisi, le reste est automatique."""

    class Meta:
        model = MarketDomain
        fields = ['label']
        widgets = {
            'label': forms.TextInput(attrs={
                'placeholder': 'Ex. appareils électronique, Téléphones et accessoires',
                'autocomplete': 'off',
            }),
        }
        labels = {
            'label': 'Nom du domaine',
        }
        help_texts = {
            'label': (
                'Nom libre (ex. « appareils électronique », « Teste »). '
                'Si une catégorie Google Trends correspond, elle est liée automatiquement ; '
                'sinon le domaine reste personnalisé (Trends sans filtre catégorie).'
            ),
        }

    def clean_label(self):
        label = self.cleaned_data['label'].strip()
        if not label:
            raise forms.ValidationError('Le nom du domaine est obligatoire.')

        cat_id, category_name, google_matched = (
            GoogleTrendsCategoryService.resolve_for_label(label)
        )
        self._resolved_cat_id = cat_id
        self._resolved_category_name = category_name
        self._google_matched = google_matched
        self._resolved_seed_keywords = GoogleTrendsCategoryService.generate_seed_keywords(label)
        return label

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.cat_id = self._resolved_cat_id
        instance.seed_keywords = self._resolved_seed_keywords
        if commit:
            instance.save()
        return instance

    @property
    def resolved_category_name(self) -> str:
        return getattr(self, '_resolved_category_name', '')

    @property
    def google_category_matched(self) -> bool:
        return getattr(self, '_google_matched', False)


class DiscoveryConfigForm(forms.Form):
    """Sauvegarde de la configuration de découverte."""

    TIMEFRAME_CHOICES = DiscoveryConfig.TIMEFRAME_CHOICES

    selected_domains = forms.ModelMultipleChoiceField(
        label='Domaines à utiliser pour la découverte',
        queryset=MarketDomain.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    timeframe = forms.ChoiceField(
        label='Période',
        choices=TIMEFRAME_CHOICES,
        initial=DEFAULT_TIMEFRAME,
        widget=forms.Select(attrs={'id': 'id_config_timeframe'}),
    )
    region = forms.CharField(
        label='Région (code pays)',
        max_length=5,
        initial=DEFAULT_REGION,
        widget=forms.TextInput(attrs={'placeholder': 'SN', 'id': 'id_config_region'}),
    )

    def clean_selected_domains(self):
        domains = self.cleaned_data['selected_domains']
        if len(domains) > MAX_DOMAINS_PER_DISCOVERY:
            raise forms.ValidationError(
                f'Google Trends limite les requêtes : sélectionnez au maximum '
                f'{MAX_DOMAINS_PER_DISCOVERY} domaine(s).'
            )
        return domains

    def clean_region(self):
        region = self.cleaned_data['region'].strip().upper()
        if not region:
            raise forms.ValidationError('La région est obligatoire.')
        return region
