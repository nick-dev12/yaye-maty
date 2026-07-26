"""
Vues fines (couche HTTP) — délèguent la logique aux contrôleurs.

Architecture MVC adaptée à Django :
- models/     → données
- controllers/ → logique métier
- views.py    → routage HTTP (équivalent MVC "View" template + point d'entrée)
- templates/  → présentation
"""

from django.contrib.auth.decorators import login_required

from yayematy_project.controllers import AuthController, DashboardController, SettingsPageController


def register_view(request):
    """Point d'entrée HTTP — inscription."""
    return AuthController(request).register()


@login_required
def dashboard_view(request):
    """Point d'entrée HTTP — tableau de bord."""
    return DashboardController(request).index()


@login_required
def settings_view(request):
    """Point d'entrée HTTP — page Paramètres."""
    return SettingsPageController(request).index()
