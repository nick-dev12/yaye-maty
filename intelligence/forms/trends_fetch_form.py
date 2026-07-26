from django import forms

from intelligence.controllers.google_trends_controller import DEFAULT_REGION, DEFAULT_TIMEFRAME


class TrendsFetchForm(forms.Form):
    """Formulaire de lancement d'une collecte Google Trends."""

    TIMEFRAME_CHOICES = [
        ('today 3-m', '3 derniers mois'),
        ('today 12-m', '12 derniers mois'),
        ('today 5-y', '5 dernières années'),
        ('now 7-d', '7 derniers jours'),
    ]

    keywords = forms.CharField(
        label='Mots-clés à rechercher',
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'tracteur, engrais, pompe solaire, semence, irrigation',
        }),
        help_text='Séparez les mots-clés par des virgules (max 5 par requête, lots automatiques).',
    )
    timeframe = forms.ChoiceField(
        label='Période',
        choices=TIMEFRAME_CHOICES,
        initial=DEFAULT_TIMEFRAME,
    )
    region = forms.CharField(
        label='Région (code pays)',
        max_length=5,
        initial=DEFAULT_REGION,
        widget=forms.TextInput(attrs={'placeholder': 'SN'}),
    )

    def clean_keywords(self):
        raw = self.cleaned_data['keywords']
        keywords = [
            kw.strip()
            for kw in raw.replace('\n', ',').split(',')
            if kw.strip()
        ]
        if not keywords:
            raise forms.ValidationError('Veuillez saisir au moins un mot-clé.')
        if len(keywords) > 25:
            raise forms.ValidationError('Maximum 25 mots-clés par collecte.')
        return keywords

    def clean_region(self):
        region = self.cleaned_data['region'].strip().upper()
        if not region:
            raise forms.ValidationError('La région est obligatoire.')
        return region
