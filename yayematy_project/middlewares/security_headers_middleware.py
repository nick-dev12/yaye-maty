"""
Middleware de sécurité — en-têtes HTTP de protection.
"""


class SecurityHeadersMiddleware:
    """Ajoute des en-têtes de sécurité à chaque réponse HTTP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
