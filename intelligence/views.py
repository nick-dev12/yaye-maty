from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from intelligence.api_auth import require_api_key
from intelligence.controllers import (
    CollectionControlController,
    CollectionTestController,
    DomainsPageController,
    IntelligencePageController,
)
from intelligence.controllers.social_api_controller import SocialApiController


@login_required
def intelligence_domains_view(request):
    """Page Domaines — gestion et découverte Google Trends."""
    return DomainsPageController(request).index()


@login_required
def intelligence_index_view(request):
    """Point d'entrée HTTP — page Intelligence de marché."""
    return IntelligencePageController(request).index()


@login_required
def intelligence_archives_view(request):
    """Page Archives — même UI que Intelligence, données historiques."""
    return IntelligencePageController(request).archives()


@login_required
def collecte_view(request):
    """Page Collecte manuelle — lancement Celery avec suivi."""
    return CollectionControlController(request).index()


@login_required
def collecte_test_view(request):
    """Page Session de test — diagnostic et lancement mode test."""
    return CollectionTestController(request).index()


@login_required
def collecte_test_donnees_view(request):
    """Page Données test — même UI que Intelligence, fenêtre session test."""
    return IntelligencePageController(request).test_results()


@login_required
def collecte_api_lancer_view(request):
    """API — démarre une collecte manuelle."""
    return CollectionControlController.api_lancer(request)


@login_required
def collecte_api_statut_view(request, task_id):
    """API — état d'une tâche Celery."""
    return CollectionControlController.api_statut(request, task_id)


@login_required
def collecte_api_arreter_view(request):
    """API — arrêt coopératif + enchaînement NLP."""
    return CollectionControlController.api_arreter(request)


@login_required
def collecte_api_reset_session_view(request):
    """API — libère une session test bloquée."""
    return CollectionControlController.api_reset_session(request)


@login_required
def collecte_api_celery_status_view(request):
    """API — état worker / beat (lancement UI dev)."""
    return CollectionControlController.api_celery_status(request)


@login_required
def collecte_api_celery_start_view(request):
    """API — démarre worker ou beat Celery."""
    return CollectionControlController.api_celery_start(request)


@login_required
def collecte_api_celery_stop_view(request):
    """API — arrête worker ou beat lancé depuis l'UI."""
    return CollectionControlController.api_celery_stop(request)


_api = SocialApiController()


@csrf_exempt
@require_api_key
def api_raw_data_view(request):
    return _api.raw_data(request)


@csrf_exempt
@require_api_key
@require_http_methods(['POST'])
def api_analyzed_data_view(request):
    return _api.analyzed_data(request)


@csrf_exempt
@require_api_key
def api_social_posts_view(request):
    return _api.social_posts(request)


@csrf_exempt
@require_api_key
def api_keywords_view(request):
    return _api.keywords(request)


@csrf_exempt
@require_api_key
def api_raw_jumia_reviews_view(request):
    return _api.raw_jumia_reviews(request)


@csrf_exempt
@require_api_key
@require_http_methods(['POST'])
def api_analyzed_jumia_reviews_view(request):
    return _api.analyzed_jumia_reviews(request)
