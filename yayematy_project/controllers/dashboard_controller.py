from django.shortcuts import render
from django.utils import timezone

from intelligence.services.dashboard_data_service import DashboardDataService


class DashboardController:
    """Tableau de bord — lecture marché simplifiée (réseaux + Jumia + Jiji)."""

    def __init__(self, request):
        self.request = request

    def index(self):
        """Affiche le home avec KPI, demande sociale, marché et actions."""
        user = self.request.user
        display_name = user.get_full_name() or user.username
        first_name = display_name.split()[0] if display_name else user.username

        data = DashboardDataService.build_context()
        context = {
            'display_name': display_name,
            'first_name': first_name,
            'greeting': self._get_greeting(),
            'date_range': self._get_date_range(),
            'user_role': 'Administrateur',
            **data,
        }
        return render(self.request, 'dashboard/index.html', context)

    def _get_greeting(self):
        hour = timezone.localtime().hour
        if hour < 12:
            return 'Bonjour'
        if hour < 18:
            return 'Bon après-midi'
        return 'Bonsoir'

    def _get_date_range(self):
        from datetime import timedelta

        today = timezone.localdate()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        months = (
            'jan', 'fév', 'mar', 'avr', 'mai', 'jun',
            'jul', 'aoû', 'sep', 'oct', 'nov', 'déc',
        )
        start_label = f'{start.day} {months[start.month - 1]}'
        end_label = f'{end.day} {months[end.month - 1]} {end.year}'
        return f'{start_label} – {end_label}'
