"""Formulaires — dictionnaire Wolof."""

from django import forms

from intelligence.models import WolofKeyword


class WolofKeywordForm(forms.ModelForm):
    """Ajout d'une expression au dictionnaire Wolof."""

    class Meta:
        model = WolofKeyword
        fields = ['expression', 'intent', 'note']
        widgets = {
            'expression': forms.TextInput(attrs={
                'class': 'settings-input',
                'placeholder': 'Ex. : ñaata la, begg jënd, prix bi',
                'autocomplete': 'off',
            }),
            'intent': forms.Select(attrs={'class': 'settings-input'}),
            'note': forms.TextInput(attrs={
                'class': 'settings-input',
                'placeholder': 'Ex. : combien coûte (optionnel)',
            }),
        }
        labels = {
            'expression': 'Expression Wolof',
            'intent': 'Intention détectée',
            'note': 'Signification',
        }

    def clean_expression(self):
        expression = self.cleaned_data['expression'].strip()
        if len(expression) < 2:
            raise forms.ValidationError('L\'expression doit contenir au moins 2 caractères.')
        return expression
