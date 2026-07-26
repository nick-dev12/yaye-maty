from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    """Formulaire d'inscription avec adresse e-mail."""

    email = forms.EmailField(
        required=True,
        label='Adresse e-mail',
        widget=forms.EmailInput(attrs={'placeholder': 'votre@email.com'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'placeholder': "Nom d'utilisateur"})
        self.fields['password1'].widget.attrs.update({'placeholder': 'Mot de passe'})
        self.fields['password2'].widget.attrs.update({'placeholder': 'Confirmer le mot de passe'})
        for field_name in ('username', 'password1', 'password2'):
            self.fields[field_name].help_text = ''

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_staff = True
        if commit:
            user.save()
        return user
