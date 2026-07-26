"""
Page dédiée aux sessions de test de collecte (diagnostic 20 min).
"""

from __future__ import annotations

from django.shortcuts import render

from intelligence.services.collection_task_session_service import CollectionTaskSessionService
from intelligence.services.manual_collection_service import ManualCollectionService


class CollectionTestController:
    """Interface de lancement des collectes en mode test."""

    def __init__(self, request):
        self.request = request

    def index(self):
        context = ManualCollectionService.get_page_context(for_test_page=True)
        context['user'] = self.request.user
        context['active_tasks'] = CollectionTaskSessionService.get_resumable(self.request)

        from intelligence.services.celery_ui_launch_service import CeleryUiLaunchService

        context.update(CeleryUiLaunchService.get_ui_context())
        return render(self.request, 'dashboard/intelligence/collection_test.html', context)
