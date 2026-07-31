from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User


class ProfileForm(forms.ModelForm):
    """Formulaire de mise à jour des informations personnelles."""

    email = forms.EmailField(
        required=True,
        label='Adresse e-mail',
        widget=forms.EmailInput(attrs={
            'placeholder': 'votre@email.com',
            'autocomplete': 'email',
        }),
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'username')
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'email': 'Adresse e-mail',
            'username': "Nom d'utilisateur",
        }
        widgets = {
            'first_name': forms.TextInput(attrs={
                'placeholder': 'Prénom',
                'autocomplete': 'given-name',
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Nom',
                'autocomplete': 'family-name',
            }),
            'username': forms.TextInput(attrs={
                'placeholder': "Nom d'utilisateur",
                'autocomplete': 'username',
            }),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Cette adresse e-mail est déjà utilisée.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return username


class ProfilePasswordChangeForm(PasswordChangeForm):
    """Changement de mot de passe avec libellés en français."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'Mot de passe actuel'
        self.fields['new_password1'].label = 'Nouveau mot de passe'
        self.fields['new_password2'].label = 'Confirmer le nouveau mot de passe'
        for field in self.fields.values():
            field.widget.attrs.setdefault('placeholder', field.label)
            field.help_text = ''
