from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import redirect, render

from yayematy_project.forms.profile_forms import ProfileForm, ProfilePasswordChangeForm


class ProfileController:
    """Page profil — consultation et modification des informations personnelles."""

    def __init__(self, request):
        self.request = request

    def index(self):
        user = self.request.user
        profile_form = ProfileForm(instance=user)
        password_form = ProfilePasswordChangeForm(user=user)

        if self.request.method == 'POST':
            action = self.request.POST.get('action', 'profile')
            if action == 'profile':
                profile_form = ProfileForm(self.request.POST, instance=user)
                if profile_form.is_valid():
                    profile_form.save()
                    messages.success(
                        self.request,
                        'Vos informations personnelles ont été mises à jour.',
                    )
                    return redirect('profile')
                messages.error(
                    self.request,
                    'Corrigez les erreurs du formulaire profil.',
                )
            elif action == 'password':
                password_form = ProfilePasswordChangeForm(user=user, data=self.request.POST)
                if password_form.is_valid():
                    password_form.save()
                    update_session_auth_hash(self.request, user)
                    messages.success(
                        self.request,
                        'Votre mot de passe a été modifié avec succès.',
                    )
                    return redirect('profile')
                messages.error(
                    self.request,
                    'Impossible de modifier le mot de passe. Vérifiez les champs.',
                )

        display_name = user.get_full_name() or user.username
        member_since = user.date_joined.strftime('%d/%m/%Y') if user.date_joined else '—'

        context = {
            'profile_form': profile_form,
            'password_form': password_form,
            'display_name': display_name,
            'member_since': member_since,
            'user_role': 'Administrateur' if user.is_staff else 'Utilisateur',
        }
        return render(self.request, 'dashboard/profile/index.html', context)
