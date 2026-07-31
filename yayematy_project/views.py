"""
Vues fines (couche HTTP) — délèguent la logique aux contrôleurs.

Architecture MVC adaptée à Django :
- models/     → données
- controllers/ → logique métier
- views.py    → routage HTTP (équivalent MVC "View" template + point d'entrée)
- templates/  → présentation
"""

from django.contrib.auth.decorators import login_required

from yayematy_project.controllers import AuthController, DashboardController, ProfileController


def register_view(request):
    """Point d'entrée HTTP — inscription."""
    return AuthController(request).register()


@login_required
def dashboard_view(request):
    """Point d'entrée HTTP — tableau de bord."""
    return DashboardController(request).index()


@login_required
def settings_view(request):
    """Ancienne page Paramètres — redirige vers Trade Intelligence."""
    from django.shortcuts import redirect
    return redirect('intelligence:index')


@login_required
def profile_view(request):
    """Point d'entrée HTTP — profil utilisateur."""
    return ProfileController(request).index()
