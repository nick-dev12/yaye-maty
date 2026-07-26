"""
Contrôleur de la page Archives Intelligence — réutilise le même tableau de bord.
"""

from intelligence.controllers.intelligence_page_controller import IntelligencePageController


class ArchivesPageController:
    """Historique complet — même UI que /intelligence/, données différentes."""

    def __init__(self, request):
        self.request = request

    def index(self):
        return IntelligencePageController(self.request).archives()
