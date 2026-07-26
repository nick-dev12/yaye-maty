"""
API REST Intelligence — échange VPS ↔ machine locale NLP.
"""

from __future__ import annotations

from django.http import JsonResponse

from intelligence.api_auth import parse_json_body
from intelligence.models import SocialPost
from intelligence.scrapers.tiktok_scrape_schema import serialize_post_for_nlp
from intelligence.services.social_post_service import SocialPostService


class SocialApiController:
    """Endpoints pour l'analyse NLP distante."""

    DEFAULT_LIMIT = 50

    def raw_data(self, request) -> JsonResponse:
        """
        GET /api/intelligence/raw-data/

        Retourne les publications en attente d'analyse NLP (structure TikTok spec).
        """
        try:
            limit = min(int(request.GET.get('limit', self.DEFAULT_LIMIT)), 200)
        except (TypeError, ValueError):
            limit = self.DEFAULT_LIMIT

        posts = SocialPostService.get_pending_for_nlp(limit=limit)
        post_ids = [post.pk for post in posts]
        SocialPostService.mark_processing(post_ids)

        serialized = [serialize_post_for_nlp(post) for post in posts]

        payload = {
            'count': len(posts),
            'schema_version': 'tiktok_v1',
            'posts': serialized,
        }
        return JsonResponse(payload)

    def analyzed_data(self, request) -> JsonResponse:
        """
        POST /api/intelligence/analyzed-data/

        Body: {"results": [{"id": 1, "category": "...", "sentiment": "...", "keywords": []}]}
        """
        body = parse_json_body(request)
        if body is None:
            return JsonResponse({'error': 'JSON invalide.'}, status=400)

        results = body.get('results') if isinstance(body, dict) else body
        if not isinstance(results, list):
            return JsonResponse({'error': 'Le champ "results" (liste) est requis.'}, status=400)

        stats = SocialPostService.apply_analysis_results(results)
        return JsonResponse({'success': True, 'stats': stats})

    def social_posts(self, request) -> JsonResponse:
        """GET /api/intelligence/social-posts/ — liste filtrable."""
        status = request.GET.get('status', '')
        platform = request.GET.get('platform', '')

        queryset = SocialPost.objects.all().order_by('-scraped_at')

        if status in SocialPost.AnalysisStatus.values:
            queryset = queryset.filter(analysis_status=status)
        if platform in SocialPost.Platform.values:
            queryset = queryset.filter(platform=platform)

        try:
            limit = min(int(request.GET.get('limit', 30)), 100)
        except (TypeError, ValueError):
            limit = 30

        posts = queryset[:limit]
        return JsonResponse({
            'count': len(posts),
            'overview': SocialPostService.get_overview_stats(),
            'posts': [serialize_post_for_nlp(post) for post in posts],
        })

    def keywords(self, request) -> JsonResponse:
        """GET /api/intelligence/keywords/ — requêtes Google Trends découvertes."""
        from intelligence.models import DiscoveredQuery

        domain = request.GET.get('domain', '')
        queryset = DiscoveredQuery.objects.all().order_by('-discovered_at')

        if domain:
            queryset = queryset.filter(domain=domain)

        try:
            limit = min(int(request.GET.get('limit', 50)), 200)
        except (TypeError, ValueError):
            limit = 50

        rows = queryset[:limit]
        return JsonResponse({
            'count': len(rows),
            'queries': [
                {
                    'domain': row.domain,
                    'query': row.query,
                    'query_type': row.query_type,
                    'region': row.region,
                    'discovered_at': row.discovered_at.isoformat(),
                }
                for row in rows
            ],
        })

    def raw_jumia_reviews(self, request) -> JsonResponse:
        """
        GET /api/raw-jumia-reviews/

        Avis Jumia non analysés — à traiter sur la machine locale (CamemBERT).
        """
        from intelligence.services.jumia_nlp_analysis_service import JumiaNlpAnalysisService

        try:
            limit = min(int(request.GET.get('limit', self.DEFAULT_LIMIT)), 200)
        except (TypeError, ValueError):
            limit = self.DEFAULT_LIMIT

        reviews = JumiaNlpAnalysisService.get_pending_for_nlp(limit=limit)
        return JsonResponse({
            'count': len(reviews),
            'schema_version': 'jumia_review_v1',
            'reviews': [JumiaNlpAnalysisService.serialize_for_nlp(r) for r in reviews],
        })

    def analyzed_jumia_reviews(self, request) -> JsonResponse:
        """
        POST /api/analyzed-jumia-reviews/

        Body: {"results": [{"id": 1, "sentiment": "negative", "aspects": {...}, ...}]}
        """
        from intelligence.services.jumia_nlp_analysis_service import JumiaNlpAnalysisService

        body = parse_json_body(request)
        if body is None:
            return JsonResponse({'error': 'JSON invalide.'}, status=400)

        results = body.get('results') if isinstance(body, dict) else body
        if not isinstance(results, list):
            return JsonResponse({'error': 'Le champ "results" (liste) est requis.'}, status=400)

        stats = JumiaNlpAnalysisService.apply_analysis_results(results)
        return JsonResponse({'success': True, 'stats': stats})
