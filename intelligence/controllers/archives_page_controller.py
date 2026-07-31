"""
Page Archives — historique des recherches Trade Intelligence (max 40).
"""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from intelligence.services.trade_research_archive_service import TradeResearchArchiveService


class ArchivesPageController:
    """Historique des analyses marché sauvegardées."""

    def __init__(self, request):
        self.request = request

    def index(self):
        if self.request.method == 'POST' and self.request.POST.get('action') == 'delete_archive':
            return self._handle_delete()

        TradeResearchArchiveService.prune_to_limit()
        sessions = TradeResearchArchiveService.list_sessions()
        cards = []
        for session in sessions:
            card = TradeResearchArchiveService.session_card(session)
            card['view_url'] = reverse('intelligence:index') + f'?session={session.pk}'
            cards.append(card)

        context = {
            'user': self.request.user,
            'archive_cards': cards,
            'archive_count': len(cards),
            'archive_max': TradeResearchArchiveService.MAX,
        }
        return render(self.request, 'dashboard/intelligence/archives.html', context)

    def _handle_delete(self) -> HttpResponseRedirect:
        raw_id = self.request.POST.get('session_id', '').strip()
        try:
            session_id = int(raw_id)
        except (TypeError, ValueError):
            messages.error(self.request, 'Archive invalide.')
            return HttpResponseRedirect(reverse('intelligence:archives'))

        deleted = TradeResearchArchiveService.delete_session(session_id)
        if deleted:
            messages.success(self.request, 'Archive supprimée.')
        else:
            messages.error(self.request, 'Archive introuvable ou déjà supprimée.')
        return HttpResponseRedirect(reverse('intelligence:archives'))
