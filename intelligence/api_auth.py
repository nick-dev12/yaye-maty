"""
Authentification API pour la machine locale (Cerveau NLP).
"""

import json
import os
from functools import wraps

from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    """Vérifie le header X-API-Key pour les endpoints REST."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        expected = getattr(settings, 'INTELLIGENCE_API_KEY', '') or os.getenv('INTELLIGENCE_API_KEY', '')
        if not expected:
            return JsonResponse(
                {'error': 'INTELLIGENCE_API_KEY non configurée sur le serveur.'},
                status=503,
            )

        provided = request.headers.get('X-API-Key', '')
        if provided != expected:
            return JsonResponse({'error': 'Clé API invalide.'}, status=401)

        return view_func(request, *args, **kwargs)

    return wrapper


def parse_json_body(request) -> dict | list | None:
    try:
        if not request.body:
            return {}
        return json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return None
