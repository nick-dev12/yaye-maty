from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from yayematy_project.forms import RegistrationForm


class AuthController:
    """Contrôleur d'authentification et d'inscription."""

    def __init__(self, request):
        self.request = request

    def register(self):
        """Inscription d'un nouvel utilisateur administrateur."""
        if self.request.user.is_authenticated:
            return redirect('dashboard')

        if self.request.method == 'POST':
            form = RegistrationForm(self.request.POST)
            if form.is_valid():
                user = form.save()
                login(self.request, user)
                messages.success(
                    self.request,
                    'Compte créé avec succès. Bienvenue !',
                )
                return redirect('dashboard')
        else:
            form = RegistrationForm()

        return render(self.request, 'accounts/register.html', {'form': form})
