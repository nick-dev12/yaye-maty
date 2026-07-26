"""Formulaires — mots-clés Paramètres (réseaux sociaux, Jumia, Jiji)."""

from django import forms

from intelligence.models import MarketSearchKeyword
from intelligence.scrapers.tiktok_scrape_schema import (
    MAX_COMMENTS_PER_VIDEO,
    MIN_COMMENTS_PER_VIDEO,
)

MIN_VIDEOS_PER_SEARCH = 5
MAX_VIDEOS_PER_SEARCH = 50
MIN_PRODUCTS_JUMIA = 3
MAX_PRODUCTS_JUMIA = 30
MIN_LISTINGS_JIJI = 3
MAX_LISTINGS_JIJI = 40
MIN_MARKETPLACE_ITEMS = 3
MAX_MARKETPLACE_ITEMS = 40


class _BaseMarketKeywordForm(forms.ModelForm):
    """Champs communs — mot-clé, catégorie produit, libellé."""

    class Meta:
        model = MarketSearchKeyword
        fields = ['keyword', 'label', 'product_category', 'max_videos', 'max_comments']
        widgets = {
            'keyword': forms.TextInput(attrs={
                'class': 'settings-input',
                'placeholder': 'Ex. : motopompe, tracteur agricole',
            }),
            'label': forms.TextInput(attrs={
                'class': 'settings-input',
                'placeholder': 'Libellé affiché (optionnel)',
            }),
            'product_category': forms.TextInput(attrs={
                'class': 'settings-input',
                'placeholder': 'Ex. : irrigation (optionnel)',
            }),
        }

    def clean_keyword(self):
        keyword = self.cleaned_data['keyword'].strip()
        if len(keyword) < 3:
            raise forms.ValidationError('Le mot-clé doit contenir au moins 3 caractères.')
        return keyword


class SocialMarketSearchKeywordForm(_BaseMarketKeywordForm):
    """Mots-clés TikTok / Facebook."""

    class Meta(_BaseMarketKeywordForm.Meta):
        fields = ['keyword', 'label', 'platform', 'product_category', 'max_videos', 'max_comments']
        widgets = {
            **_BaseMarketKeywordForm.Meta.widgets,
            'platform': forms.Select(attrs={'class': 'settings-input'}),
            'max_videos': forms.NumberInput(attrs={
                'class': 'settings-input',
                'min': MIN_VIDEOS_PER_SEARCH,
                'max': MAX_VIDEOS_PER_SEARCH,
            }),
            'max_comments': forms.NumberInput(attrs={
                'class': 'settings-input',
                'min': MIN_COMMENTS_PER_VIDEO,
                'max': MAX_COMMENTS_PER_VIDEO,
            }),
        }
        labels = {
            'keyword': 'Mot-clé de recherche',
            'label': 'Libellé',
            'platform': 'Réseau social',
            'product_category': 'Catégorie produit (optionnel)',
            'max_videos': 'Max vidéos / posts par collecte',
            'max_comments': 'Commentaires par vidéo (10–20)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['platform'].choices = [
            (MarketSearchKeyword.Platform.TIKTOK, 'TikTok'),
            (MarketSearchKeyword.Platform.FACEBOOK, 'Facebook'),
        ]
        if not self.initial.get('platform'):
            self.initial['platform'] = MarketSearchKeyword.Platform.TIKTOK

    def clean_platform(self):
        platform = self.cleaned_data['platform']
        if platform not in (
            MarketSearchKeyword.Platform.TIKTOK,
            MarketSearchKeyword.Platform.FACEBOOK,
        ):
            raise forms.ValidationError('Plateforme réseau invalide.')
        return platform

    def clean_max_videos(self):
        value = self.cleaned_data.get('max_videos') or 15
        if value < MIN_VIDEOS_PER_SEARCH or value > MAX_VIDEOS_PER_SEARCH:
            raise forms.ValidationError(
                f'Indiquez entre {MIN_VIDEOS_PER_SEARCH} et {MAX_VIDEOS_PER_SEARCH} vidéos.'
            )
        return value

    def clean_max_comments(self):
        value = self.cleaned_data.get('max_comments') or MAX_COMMENTS_PER_VIDEO
        if value < MIN_COMMENTS_PER_VIDEO or value > MAX_COMMENTS_PER_VIDEO:
            raise forms.ValidationError(
                f'Entre {MIN_COMMENTS_PER_VIDEO} et {MAX_COMMENTS_PER_VIDEO} commentaires.'
            )
        return value


class MarketplaceKeywordForm(_BaseMarketKeywordForm):
    """Mot-clé marketplace — partagé entre Jumia et Jiji."""

    class Meta(_BaseMarketKeywordForm.Meta):
        fields = ['keyword', 'product_category', 'max_videos', 'max_comments']
        widgets = {
            **_BaseMarketKeywordForm.Meta.widgets,
            'max_videos': forms.NumberInput(attrs={
                'class': 'settings-input',
                'min': MIN_MARKETPLACE_ITEMS,
                'max': MAX_MARKETPLACE_ITEMS,
            }),
            'max_comments': forms.NumberInput(attrs={
                'class': 'settings-input',
                'min': MIN_COMMENTS_PER_VIDEO,
                'max': MAX_COMMENTS_PER_VIDEO,
            }),
        }
        labels = {
            'keyword': 'Mot-clé marketplace',
            'product_category': 'Catégorie catalogue (optionnel)',
            'max_videos': 'Produits Jumia / annonces Jiji par collecte',
            'max_comments': 'Avis max par produit Jumia',
        }
        help_texts = {
            'keyword': 'Utilisé pour Jumia.sn et Jiji.sn (même mot-clé, deux collectes).',
            'product_category': (
                'Aide le scraper à cibler la bonne rubrique Jumia/Jiji '
                '(ex. irrigation, tracteurs_machinisme). Laissez vide si le mot-clé suffit.'
            ),
            'max_videos': (
                f'Entre {MIN_MARKETPLACE_ITEMS} et {MAX_MARKETPLACE_ITEMS} '
                'résultats par plateforme et par mot-clé.'
            ),
            'max_comments': 'Nombre d’avis récupérés par produit Jumia pour l’analyse NLP.',
        }

    def clean_max_videos(self):
        value = self.cleaned_data.get('max_videos') or 10
        if value < MIN_MARKETPLACE_ITEMS or value > MAX_MARKETPLACE_ITEMS:
            raise forms.ValidationError(
                f'Indiquez entre {MIN_MARKETPLACE_ITEMS} et {MAX_MARKETPLACE_ITEMS} résultats.'
            )
        return value

    def clean_max_comments(self):
        value = self.cleaned_data.get('max_comments') or 15
        if value < MIN_COMMENTS_PER_VIDEO or value > MAX_COMMENTS_PER_VIDEO:
            raise forms.ValidationError(
                f'Entre {MIN_COMMENTS_PER_VIDEO} et {MAX_COMMENTS_PER_VIDEO} avis.'
            )
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.platform = MarketSearchKeyword.Platform.MARKETPLACE
        if commit:
            instance.save()
        return instance


class JumiaMarketKeywordForm(MarketplaceKeywordForm):
    """Alias rétrocompatibilité — mot-clé marketplace partagé."""

    def save(self, commit=True):
        return MarketplaceKeywordForm.save(self, commit=commit)


class JijiMarketKeywordForm(MarketplaceKeywordForm):
    """Alias rétrocompatibilité — mot-clé marketplace partagé."""

    def save(self, commit=True):
        return MarketplaceKeywordForm.save(self, commit=commit)


# Alias rétrocompatibilité
MarketSearchKeywordForm = SocialMarketSearchKeywordForm
