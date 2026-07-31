"""
Page Session test — tests individuels Google / Jumia / Jiji / TikTok
via le même pipeline Trade Intelligence (domaine + mot-clé + durée).
"""

from __future__ import annotations

import json

from django.shortcuts import render

from intelligence.models import MarketResearchSession
from intelligence.services.trade_domain_catalog import DURATION_OPTIONS, TradeDomainCatalog
from intelligence.services.trade_intelligence_display_service import TradeIntelligenceDisplayService


class CollectionTestController:
    """Interface de test par source (Trade Intelligence)."""

    SOURCE_BUTTONS = (
        {'id': 'google', 'label': 'Tester Google Trends', 'desc': 'pytrends · geo SN'},
        {'id': 'jumia', 'label': 'Tester Jumia', 'desc': 'Listings + prix Jumia.sn'},
        {'id': 'jiji', 'label': 'Tester Jiji', 'desc': 'Annonces Jiji.sn'},
        {'id': 'tiktok', 'label': 'Tester TikTok', 'desc': 'Recherche Top-Down TikTok'},
    )

    def __init__(self, request):
        self.request = request

    def index(self):
        session = None
        session_id = self.request.GET.get('session')
        if session_id:
            session = MarketResearchSession.objects.filter(pk=session_id).first()
        else:
            session = (
                MarketResearchSession.objects.filter(
                    status=MarketResearchSession.Status.DONE,
                )
                .order_by('-completed_at')
                .first()
            )

        domains = TradeDomainCatalog.list_domains()
        context = TradeIntelligenceDisplayService.build_page_context(session=session)
        context['user'] = self.request.user
        context['domains'] = domains
        context['domains_json'] = json.dumps(domains, ensure_ascii=False)
        context['duration_options'] = DURATION_OPTIONS
        context['source_buttons'] = self.SOURCE_BUTTONS
        context['is_session_test'] = True

        active = None
        if session and session.celery_task_id and session.status not in (
            MarketResearchSession.Status.DONE,
            MarketResearchSession.Status.FAILED,
        ):
            active = {
                'task_id': session.celery_task_id,
                'session_id': session.pk,
                'status': session.status,
                'duration_minutes': session.duration_minutes,
            }
        context['active_task'] = active
        if session:
            context['selected_domain_slug'] = session.domain_slug
            context['selected_keyword'] = session.keyword
            context['selected_duration'] = session.duration_minutes

        from intelligence.services.celery_ui_launch_service import CeleryUiLaunchService
        context.update(CeleryUiLaunchService.get_ui_context())

        return render(self.request, 'dashboard/intelligence/collection_test.html', context)
