"""
Contexte UI Import Master — rapport DeepSeek comparaison domaines uniquement.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from intelligence.services.import_master_deepseek_service import ImportMasterDeepSeekService


class ImportMasterDisplayService:
    """Prépare le contexte du rapport Import Master (analyses domaines)."""

    @classmethod
    def expire_stuck_analyses(cls, *, max_age_minutes: int = 15) -> int:
        """Marque pending/running trop anciennes comme échouées (worker mort)."""
        from intelligence.models import ImportMasterDomainAnalysis

        cutoff = timezone.now() - timedelta(minutes=max(1, max_age_minutes))
        qs = ImportMasterDomainAnalysis.objects.filter(
            status__in=(
                ImportMasterDomainAnalysis.Status.PENDING,
                ImportMasterDomainAnalysis.Status.RUNNING,
            ),
            created_at__lt=cutoff,
        )
        return int(qs.update(
            status=ImportMasterDomainAnalysis.Status.FAILED,
            progress_message='Expirée — aucune progression (Celery inactif ou bloqué).',
            error_message='Timeout sans avancement.',
            completed_at=timezone.now(),
            progress_percent=0,
        ))

    @classmethod
    def build_context(cls) -> dict:
        cls.expire_stuck_analyses(max_age_minutes=15)
        return cls.get_domain_analysis_block()

    @classmethod
    def get_domain_analysis_block(cls) -> dict:
        """Dernière analyse comparative domaines DeepSeek + méta UI."""
        from intelligence.models import ImportMasterDomainAnalysis

        latest = ImportMasterDomainAnalysis.objects.order_by('-created_at').first()
        snapshots = ImportMasterDeepSeekService.collect_domain_snapshots()
        sessions_total = sum(s.get('sessions_count') or 1 for s in snapshots)
        running = latest and latest.status in (
            ImportMasterDomainAnalysis.Status.PENDING,
            ImportMasterDomainAnalysis.Status.RUNNING,
        )
        result = (latest.analysis_result or {}) if latest else {}
        if not isinstance(result, dict):
            result = {}

        reco_counts = {'buy': 0, 'watch': 0, 'avoid': 0}
        for row in result.get('produits_import') or []:
            text = str((row or {}).get('recommandation') or '').lower()
            if 'éviter' in text or 'eviter' in text:
                reco_counts['avoid'] += 1
            elif 'moyen' in text or 'affaire' in text:
                reco_counts['watch'] += 1
            elif text:
                reco_counts['buy'] += 1

        return {
            'im_domain_analysis': latest,
            'im_domain_running': bool(running),
            'im_domain_result': result,
            'im_domain_has_result': bool(
                latest
                and latest.status == ImportMasterDomainAnalysis.Status.DONE
                and (
                    result.get('classement_domaines')
                    or result.get('produits_import')
                    or result.get('resume')
                )
            ),
            'im_domains_available': len(snapshots),
            'im_sessions_available': sessions_total,
            'im_domain_snapshots': snapshots,
            'im_reco_counts': reco_counts,
            'im_failed': bool(
                latest and latest.status == ImportMasterDomainAnalysis.Status.FAILED
            ),
            'im_stopped': bool(
                latest and latest.status == ImportMasterDomainAnalysis.Status.STOPPED
            ),
        }

    @classmethod
    def get_home_preview(cls, *, limit: int = 3) -> list[dict]:
        """Aperçu accueil : top opportunités / produits du dernier rapport."""
        block = cls.get_domain_analysis_block()
        result = block.get('im_domain_result') or {}
        opps = list(result.get('meilleures_opportunites') or [])
        source = opps if opps else list(result.get('produits_import') or [])

        preview = []
        for o in source[:limit]:
            reco = str(o.get('recommandation') or '')
            preview.append({
                'rank': o.get('rang'),
                'product_name': o.get('produit') or o.get('titre') or '—',
                'keyword': o.get('domaine') or '',
                'score': int(round(float(o.get('note') or 0) * 10)),
                'decision_label': reco,
                'decision_tone': (
                    'gris' if 'éviter' in reco.lower()
                    else 'jaune' if 'moyen' in reco.lower() or 'affaire' in reco.lower()
                    else 'orange'
                ),
                'decision_hint': (
                    o.get('commentaire')
                    or o.get('commentaire_analyste')
                    or o.get('synthese')
                    or ''
                )[:160],
                'reasons': [],
                'demand_score': 0,
                'trend_score': 0,
                'competition_score': 0,
                'price_score': 0,
                'subscores': [],
                'price_min': None,
                'price_avg': None,
                'price_max': None,
                'suggested_price': None,
                'jumia_sellers': 0,
                'jiji_listings': 0,
                'purchase_intents': 0,
                'total_views': 0,
                'stock_alert': '',
            })
        return preview
