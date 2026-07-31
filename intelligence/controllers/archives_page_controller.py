"""
Page Archives — historique des recherches Trade Intelligence (max 40).
"""

from __future__ import annotations

from django.shortcuts import render
from django.urls import reverse

from intelligence.services.trade_research_archive_service import TradeResearchArchiveService


class ArchivesPageController:
    """Historique des analyses marché sauvegardées."""

    def __init__(self, request):
        self.request = request

    def index(self):
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
