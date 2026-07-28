"""
Contrôleur de la page Import Master — opportunités d'importation du jour.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from intelligence.services.import_master_display_service import ImportMasterDisplayService


class ImportMasterPageController:
    """Page Import Master : décisions Acheter / Surveiller / Éviter par mot-clé."""

    def __init__(self, request):
        self.request = request

    def index(self):
        if self.request.method == 'POST' and self.request.POST.get('action') == 'recalculer':
            return self._handle_recalculate()

        context = ImportMasterDisplayService.build_context()
        return render(self.request, 'dashboard/intelligence/import_master.html', context)

    def _handle_recalculate(self):
        from intelligence.services.import_scoring_service import ImportScoringService

        try:
            result = ImportScoringService.refresh_opportunities()
        except Exception as exc:
            messages.error(self.request, f'Recalcul impossible : {exc}')
            return HttpResponseRedirect(reverse('intelligence:import_master'))

        if result['created']:
            messages.success(
                self.request,
                f'Import Master recalculé — {result["buy"]} Acheter, '
                f'{result["watch"]} Surveiller, {result["avoid"]} Éviter.',
            )
        else:
            messages.warning(
                self.request,
                'Aucun mot-clé actif dans Paramètres — ajoutez des mots-clés puis relancez.',
            )
        return HttpResponseRedirect(reverse('intelligence:import_master'))
