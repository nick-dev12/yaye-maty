"""
Analyse comparative Import Master via DeepSeek-v4-flash.
Compare les analyses Trade Intelligence déjà passées (tous domaines),
recherche web les meilleures opportunités + prix potentiels (Alibaba, AliExpress, Amazon).
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from django.db import models
from django.utils import timezone
from openai import OpenAI

from intelligence.models import MarketResearchSession
from intelligence.services.deepseek_analysis_service import DeepSeekAnalysisService

logger = logging.getLogger(__name__)

COMPARE_SYSTEM = """Tu es un analyste import senior pour YAYEMATY MARKET (Sénégal, XOF).
Tu produis UNIQUEMENT du JSON valide, sans markdown.
Mission :
1) Comparer les résultats d'analyse Trade Intelligence DÉJÀ PASSÉS (domaines + Top produits).
2) Identifier les meilleures opportunités d'importation tous domaines confondus.
3) Estimer les prix potentiels d'achat (Alibaba, AliExpress, Amazon) et la marge vs marché SN (Jumia/Jiji).
4) Rédiger des commentaires d'analyste professionnels, concrets et actionnables.

Recommandations EXACTES :
« Bon, je vous le recommande » | « Peut faire l'affaire mais moyen » | « À éviter »
Commentaires : 2–4 phrases max chacun, ton expert, chiffres si disponibles.
"""

COMPARE_USER = """Analyse comparative d'importation YAYEMATY.

=== ANALYSES TRADE INTELLIGENCE DÉJÀ PASSÉES (par domaine) ===
{domains_json}

=== RECHERCHE WEB (meilleures opportunités + prix Alibaba / AliExpress / Amazon) ===
{web_context}

Consignes :
- Chaque domaine inclut jusqu'à 2 analyses récentes (dernière + précédente) : repère les tendances (produits qui montent, notes qui évoluent).
- Compare les domaines entre eux à partir des notes, reco et synthèses fournies.
- Tous domaines confondus : classe les meilleurs produits du Top à importer.
- Pour chaque produit prioritaire : prix potentiels Alibaba / AliExpress / Amazon + prix SN si connu + marge estimée XOF.
- Ajoute des commentaires d'analyste détaillés (pourquoi cette opportunité, risques, action).

Réponds avec ce JSON exact :
{{
  "resume": "Synthèse exécutive 3–5 phrases : où importer en priorité et pourquoi.",
  "commentaire_global": "Commentaire d'analyste global (marché SN, sourcing, timing).",
  "methodologie": "1–2 phrases sur la méthode (TI + web Alibaba/AliExpress/Amazon).",
  "classement_domaines": [
    {{
      "rang": 1,
      "domaine": "...",
      "note_globale": 8.5,
      "recommandation": "Bon, je vous le recommande",
      "synthese": "Pourquoi ce domaine…",
      "commentaire_analyste": "Lecture détaillée…",
      "points_forts": ["...", "..."],
      "risques": ["..."],
      "opportunites_cles": ["Produit ou angle d'import…"]
    }}
  ],
  "comparaison": [
    {{
      "domaine_a": "...",
      "domaine_b": "...",
      "verdict": "A vs B…",
      "critere": "demande|marge|concurrence|prix_import",
      "commentaire": "Détail du face-à-face…"
    }}
  ],
  "meilleures_opportunites": [
    {{
      "rang": 1,
      "titre": "Opportunité courte",
      "domaine": "...",
      "produit": "Modèle précis",
      "note": 8.7,
      "recommandation": "Bon, je vous le recommande",
      "commentaire": "Pourquoi c'est la meilleure opportunité web + TI…",
      "action": "Importer / tester stock / surveiller"
    }}
  ],
  "produits_import": [
    {{
      "rang": 1,
      "produit": "Modèle précis",
      "domaine": "...",
      "note": 8.8,
      "recommandation": "Bon, je vous le recommande",
      "synthese": "Pourquoi importer…",
      "commentaire_analyste": "Analyse prix + demande + risque stock…",
      "commentaire_prix": "Lecture des prix sourcing vs SN…",
      "prix_sn_xof": "ex. 95–120k XOF",
      "prix_alibaba_usd": "ex. 45–60 USD",
      "prix_aliexpress_usd": "...",
      "prix_amazon_usd": "...",
      "prix_potentiel_achat_xof": "équivalent XOF estimé",
      "marge_estimee_xof": "ex. ~25k XOF / unité",
      "sources_prix": ["alibaba", "aliexpress", "amazon", "jumia", "jiji"]
    }}
  ],
  "alertes": ["Risque ou point de vigilance…"]
}}
"""


class ImportMasterDeepSeekService:
    """Compare domaines déjà analysés + opportunités / prix web via DeepSeek."""

    # Fenêtre de données : N dernières sessions TI par domaine
    SESSIONS_PER_DOMAIN = 2
    TOP_PRODUCTS_PER_SESSION = 8
    MAX_SESSION_AGE_DAYS = 90

    WEB_FOCUSES = (
        'meilleures opportunités import Sénégal à partir des modèles listés',
        'prix gros Alibaba (USD) pour chaque modèle prioritaire',
        'prix AliExpress wholesale vs revente Jumia.sn Jiji.sn',
        'prix Amazon et coûts logistique Afrique de l’Ouest XOF',
        'marge potentielle revendeur Sénégal tous domaines confondus',
    )

    @classmethod
    def _session_payload(cls, session: MarketResearchSession, *, per_top: int) -> dict | None:
        """Extrait Top produits + highlights d'une session TI."""
        analysis = session.analysis_result or {}
        if not isinstance(analysis, dict):
            return None
        top = list(analysis.get('top_investissement') or [])[:per_top]
        if not top:
            return None
        highlights = analysis.get('highlights') or {}
        return {
            'session_id': session.pk,
            'completed_at': (
                session.completed_at.isoformat() if session.completed_at else ''
            ),
            'mot_cle': session.keyword or '',
            'top_produits': [
                {
                    'rang': item.get('rang'),
                    'produit': item.get('produit'),
                    'note': item.get('note'),
                    'recommandation': item.get('recommandation'),
                    'synthese': (item.get('synthese') or '')[:280],
                }
                for item in top
                if isinstance(item, dict)
            ],
            'highlights': {
                'top_pick': highlights.get('top_pick'),
                'meilleure_marge': highlights.get('meilleure_marge'),
                'forte_croissance': highlights.get('forte_croissance'),
            },
        }

    @classmethod
    def _iter_snapshot_products(cls, snap: dict):
        """Produits d'un domaine (dernière session + sessions historiques)."""
        seen: set[str] = set()
        for item in snap.get('top_produits') or []:
            if not isinstance(item, dict):
                continue
            name = (item.get('produit') or '').strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                yield item
        for session in snap.get('sessions') or []:
            if not isinstance(session, dict):
                continue
            for item in session.get('top_produits') or []:
                if not isinstance(item, dict):
                    continue
                name = (item.get('produit') or '').strip()
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    yield item

    @classmethod
    def collect_domain_snapshots(
        cls,
        *,
        sessions_per_domain: int | None = None,
        per_session_top: int | None = None,
        max_age_days: int | None = None,
    ) -> list[dict]:
        """
        Dernières sessions DONE/STOPPED par domaine (défaut : 2 analyses récentes).

        Volume maîtrisé pour l'IA : tous les domaines actifs, sans tout l'historique.
        """
        n_sessions = max(1, int(
            sessions_per_domain if sessions_per_domain is not None
            else cls.SESSIONS_PER_DOMAIN
        ))
        per_top = max(3, int(
            per_session_top if per_session_top is not None
            else cls.TOP_PRODUCTS_PER_SESSION
        ))
        age_days = max(
            1,
            int(max_age_days if max_age_days is not None else cls.MAX_SESSION_AGE_DAYS),
        )
        cutoff = timezone.now() - timedelta(days=age_days)

        done_statuses = (
            MarketResearchSession.Status.DONE,
            MarketResearchSession.Status.STOPPED,
        )
        base_qs = (
            MarketResearchSession.objects.filter(
                status__in=done_statuses,
                analysis_result__isnull=False,
            )
            .exclude(domain_slug='')
            .filter(
                models.Q(completed_at__gte=cutoff)
                | models.Q(completed_at__isnull=True, created_at__gte=cutoff)
            )
        )
        domain_slugs = sorted(set(
            base_qs.values_list('domain_slug', flat=True)
        ))
        ordered_qs = base_qs.order_by('-completed_at', '-id')

        snapshots = []
        for slug in domain_slugs:
            sessions = list(ordered_qs.filter(domain_slug=slug)[:n_sessions])
            if not sessions:
                continue
            session_payloads = []
            for session in sessions:
                payload = cls._session_payload(session, per_top=per_top)
                if payload:
                    session_payloads.append(payload)
            if not session_payloads:
                continue
            latest = sessions[0]
            snapshots.append({
                'domaine': latest.domain_label,
                'domain_slug': latest.domain_slug,
                'sessions_count': len(session_payloads),
                'sessions': session_payloads,
                # Rétrocompat UI — dernière analyse
                'mot_cle': latest.keyword or '',
                'session_id': latest.pk,
                'completed_at': (
                    latest.completed_at.isoformat() if latest.completed_at else ''
                ),
                'top_produits': session_payloads[0]['top_produits'],
                'highlights': session_payloads[0]['highlights'],
            })
        snapshots.sort(key=lambda s: s['domaine'].lower())
        return snapshots

    @classmethod
    def fetch_sourcing_web_context(
        cls,
        snapshots: list[dict],
        *,
        should_cancel=None,
        progress=None,
    ) -> str:
        """Recherches web : opportunités + prix Alibaba / AliExpress / Amazon."""
        if not DeepSeekAnalysisService.is_enabled():
            return ''
        domains = ', '.join(s['domaine'] for s in snapshots[:10]) or 'e-commerce Sénégal'
        products: list[str] = []
        for snap in snapshots:
            for item in cls._iter_snapshot_products(snap):
                name = (item.get('produit') or '').strip()
                if name and name not in products:
                    products.append(name)
                if len(products) >= 18:
                    break
            if len(products) >= 18:
                break
        product_hint = ', '.join(products[:15]) if products else domains
        chunks: list[str] = []
        total = len(cls.WEB_FOCUSES)
        for idx, focus in enumerate(cls.WEB_FOCUSES, start=1):
            if should_cancel and should_cancel():
                raise RuntimeError('Analyse annulée par l’utilisateur.')
            if progress:
                progress(
                    20 + int(30 * idx / max(total, 1)),
                    f'Recherche web {idx}/{total} — {focus[:48]}…',
                )
            chunk = DeepSeekAnalysisService.fetch_web_context(
                f'Produits Top : {product_hint}. Domaines : {domains}.',
                domain_label='Import multi-domaines YAYEMATY',
                focus_hint=focus,
            )
            if chunk:
                chunks.append(f'--- {focus} ---\n{chunk}')
        return '\n\n'.join(chunks)[:16000]

    @classmethod
    def analyze(cls, snapshots: list[dict], web_context: str) -> dict:
        """Appel deepseek-v4-flash — comparaison + opportunités + prix."""
        cfg = DeepSeekAnalysisService._config()
        api_key = cfg.get('API_KEY', '')
        if not api_key:
            raise RuntimeError('DEEPSEEK_API_KEY non configurée.')

        client = OpenAI(api_key=api_key, base_url=cfg.get('BASE_URL', 'https://api.deepseek.com'))
        domains_json = json.dumps(snapshots, ensure_ascii=False, indent=2)[:16000]
        user_content = COMPARE_USER.format(
            domains_json=domains_json,
            web_context=(web_context or 'Aucun contexte web.')[:8000],
        )
        response = client.chat.completions.create(
            model=cfg.get('MODEL', 'deepseek-v4-flash'),
            messages=[
                {'role': 'system', 'content': COMPARE_SYSTEM},
                {'role': 'user', 'content': user_content},
            ],
            response_format={'type': 'json_object'},
            max_tokens=min(int(cfg.get('MAX_TOKENS', 8192)), 8192),
            timeout=float(cfg.get('TIMEOUT_SECONDS', 120)),
            extra_body=DeepSeekAnalysisService._chat_extra_body(cfg),
        )
        raw = (response.choices[0].message.content or '').strip()
        parsed = DeepSeekAnalysisService._parse_json_response(raw)
        return cls.normalize_result(parsed, snapshots)

    @classmethod
    def normalize_result(cls, data: dict, snapshots: list[dict]) -> dict:
        if not isinstance(data, dict):
            data = {}

        def reco_for(note: float, current: str = '') -> str:
            return DeepSeekAnalysisService._recommendation_for_note(note, current)

        ranking = []
        for i, row in enumerate(data.get('classement_domaines') or [], start=1):
            if not isinstance(row, dict):
                continue
            try:
                note = float(row.get('note_globale') or 0)
            except (TypeError, ValueError):
                note = 0.0
            note = max(0.0, min(10.0, note))
            ranking.append({
                'rang': int(row.get('rang') or i),
                'domaine': str(row.get('domaine') or '')[:120],
                'note_globale': round(note, 1),
                'recommandation': reco_for(note, str(row.get('recommandation') or '')),
                'synthese': str(row.get('synthese') or '')[:360],
                'commentaire_analyste': str(
                    row.get('commentaire_analyste') or row.get('synthese') or ''
                )[:500],
                'points_forts': [str(x)[:140] for x in (row.get('points_forts') or [])[:5]],
                'risques': [str(x)[:140] for x in (row.get('risques') or [])[:5]],
                'opportunites_cles': [
                    str(x)[:160] for x in (row.get('opportunites_cles') or [])[:5]
                ],
            })

        if not ranking and snapshots:
            for i, snap in enumerate(snapshots, start=1):
                notes = []
                for p in cls._iter_snapshot_products(snap):
                    if p.get('note') is not None:
                        try:
                            notes.append(float(p.get('note') or 0))
                        except (TypeError, ValueError):
                            pass
                avg = round(sum(notes) / len(notes), 1) if notes else 5.0
                synth = DeepSeekAnalysisService._default_synthese(snap['domaine'], avg, i)
                ranking.append({
                    'rang': i,
                    'domaine': snap['domaine'],
                    'note_globale': avg,
                    'recommandation': reco_for(avg),
                    'synthese': synth,
                    'commentaire_analyste': synth,
                    'points_forts': [],
                    'risques': [],
                    'opportunites_cles': [
                        p.get('produit') for p in (snap.get('top_produits') or [])[:3]
                        if p.get('produit')
                    ],
                })
            ranking.sort(key=lambda x: x['note_globale'], reverse=True)
            for i, row in enumerate(ranking, start=1):
                row['rang'] = i

        opportunities = []
        for i, row in enumerate(data.get('meilleures_opportunites') or [], start=1):
            if not isinstance(row, dict):
                continue
            try:
                note = float(row.get('note') or 0)
            except (TypeError, ValueError):
                note = 0.0
            note = max(0.0, min(10.0, note))
            opportunities.append({
                'rang': int(row.get('rang') or i),
                'titre': str(row.get('titre') or row.get('produit') or '')[:160],
                'domaine': str(row.get('domaine') or '')[:120],
                'produit': str(row.get('produit') or '')[:200],
                'note': round(note, 1),
                'recommandation': reco_for(note, str(row.get('recommandation') or '')),
                'commentaire': str(row.get('commentaire') or '')[:450],
                'action': str(row.get('action') or '')[:120],
            })

        products = []
        for i, row in enumerate(data.get('produits_import') or [], start=1):
            if not isinstance(row, dict):
                continue
            try:
                note = float(row.get('note') or 0)
            except (TypeError, ValueError):
                note = 0.0
            note = max(0.0, min(10.0, note))
            products.append({
                'rang': int(row.get('rang') or i),
                'produit': str(row.get('produit') or '')[:200],
                'domaine': str(row.get('domaine') or '')[:120],
                'note': round(note, 1),
                'recommandation': reco_for(note, str(row.get('recommandation') or '')),
                'synthese': str(row.get('synthese') or '')[:360],
                'commentaire_analyste': str(
                    row.get('commentaire_analyste') or row.get('synthese') or ''
                )[:500],
                'commentaire_prix': str(row.get('commentaire_prix') or '')[:360],
                'prix_sn_xof': str(row.get('prix_sn_xof') or '')[:80],
                'prix_alibaba_usd': str(row.get('prix_alibaba_usd') or '')[:80],
                'prix_aliexpress_usd': str(row.get('prix_aliexpress_usd') or '')[:80],
                'prix_amazon_usd': str(row.get('prix_amazon_usd') or '')[:80],
                'prix_potentiel_achat_xof': str(
                    row.get('prix_potentiel_achat_xof') or ''
                )[:80],
                'marge_estimee_xof': str(row.get('marge_estimee_xof') or '')[:80],
                'sources_prix': [
                    str(s) for s in (row.get('sources_prix') or []) if s
                ][:6],
            })

        # Fallback produits depuis snapshots si DeepSeek n'en a pas renvoyé
        if not products and snapshots:
            flat = []
            for snap in snapshots:
                for item in cls._iter_snapshot_products(snap):
                    if not item.get('produit'):
                        continue
                    try:
                        n = float(item.get('note') or 0)
                    except (TypeError, ValueError):
                        n = 0.0
                    flat.append((n, snap['domaine'], item))
            flat.sort(key=lambda x: x[0], reverse=True)
            for i, (n, domaine, item) in enumerate(flat[:15], start=1):
                products.append({
                    'rang': i,
                    'produit': str(item.get('produit'))[:200],
                    'domaine': domaine,
                    'note': round(max(0.0, min(10.0, n)), 1),
                    'recommandation': reco_for(n, str(item.get('recommandation') or '')),
                    'synthese': str(item.get('synthese') or '')[:360],
                    'commentaire_analyste': str(item.get('synthese') or '')[:500],
                    'commentaire_prix': (
                        'Prix sourcing web non disponibles — relancez l’analyse comparative.'
                    ),
                    'prix_sn_xof': '',
                    'prix_alibaba_usd': '',
                    'prix_aliexpress_usd': '',
                    'prix_amazon_usd': '',
                    'prix_potentiel_achat_xof': '',
                    'marge_estimee_xof': '',
                    'sources_prix': [],
                })

        comparisons = []
        for row in data.get('comparaison') or []:
            if isinstance(row, dict) and (row.get('domaine_a') or row.get('verdict')):
                comparisons.append({
                    'domaine_a': str(row.get('domaine_a') or '')[:120],
                    'domaine_b': str(row.get('domaine_b') or '')[:120],
                    'verdict': str(row.get('verdict') or '')[:320],
                    'critere': str(row.get('critere') or '')[:60],
                    'commentaire': str(row.get('commentaire') or row.get('verdict') or '')[:400],
                })

        resume = str(data.get('resume') or '')[:700]
        commentaire_global = str(data.get('commentaire_global') or resume)[:700]
        if not resume and ranking:
            top_d = ranking[0]
            resume = (
                f'Domaine prioritaire : {top_d["domaine"]} '
                f'({top_d["note_globale"]}/10 — {top_d["recommandation"]}).'
            )
            commentaire_global = resume

        return {
            'resume': resume,
            'commentaire_global': commentaire_global,
            'methodologie': str(data.get('methodologie') or (
                'Comparaison des 2 dernières sessions Trade Intelligence par domaine '
                '(90 jours max), enrichie par recherches web Alibaba / AliExpress / Amazon.'
            ))[:400],
            'classement_domaines': ranking[:12],
            'comparaison': comparisons[:12],
            'meilleures_opportunites': opportunities[:10],
            'produits_import': products[:15],
            'alertes': [str(a)[:220] for a in (data.get('alertes') or [])[:8]],
            'domains_count': len(snapshots),
            'generated_at': timezone.now().isoformat(),
        }

    @classmethod
    def run_analysis(
        cls,
        *,
        progress: Any = None,
        analysis_id: int | None = None,
        should_cancel=None,
    ) -> dict:
        """Pipeline : snapshots domaines → web → DeepSeek → persist."""
        from intelligence.models import ImportMasterDomainAnalysis

        def report(pct: int, msg: str) -> None:
            if should_cancel and should_cancel():
                raise RuntimeError('Analyse annulée par l’utilisateur.')
            if analysis_id:
                # Ne pas écraser un STOPPED
                updated = ImportMasterDomainAnalysis.objects.filter(
                    pk=analysis_id,
                ).exclude(
                    status=ImportMasterDomainAnalysis.Status.STOPPED,
                ).update(
                    progress_percent=pct,
                    progress_message=msg[:300],
                )
                if not updated and analysis_id:
                    current = ImportMasterDomainAnalysis.objects.filter(
                        pk=analysis_id,
                    ).values_list('status', flat=True).first()
                    if current == ImportMasterDomainAnalysis.Status.STOPPED:
                        raise RuntimeError('Analyse annulée par l’utilisateur.')
            if progress:
                progress(pct, msg)

        analysis = None
        if analysis_id:
            analysis = ImportMasterDomainAnalysis.objects.filter(pk=analysis_id).first()
            if analysis and analysis.status == ImportMasterDomainAnalysis.Status.STOPPED:
                raise RuntimeError('Analyse annulée par l’utilisateur.')

        report(5, 'Chargement des 2 dernières analyses TI par domaine…')
        snapshots = cls.collect_domain_snapshots()
        sessions_total = sum(s.get('sessions_count') or 1 for s in snapshots)
        if not snapshots:
            result = {
                'resume': (
                    'Aucune session Trade Intelligence terminée. '
                    'Lancez d’abord des analyses par domaine sur /intelligence/.'
                ),
                'commentaire_global': (
                    'Sans analyses domaines préalables, la comparaison multi-domaines '
                    'et le pricing sourcing ne peuvent pas être construits.'
                ),
                'methodologie': '',
                'classement_domaines': [],
                'comparaison': [],
                'meilleures_opportunites': [],
                'produits_import': [],
                'alertes': ['Pas de données domaine à comparer.'],
                'domains_count': 0,
                'generated_at': timezone.now().isoformat(),
            }
            if analysis and analysis.status != ImportMasterDomainAnalysis.Status.STOPPED:
                analysis.status = ImportMasterDomainAnalysis.Status.DONE
                analysis.analysis_result = result
                analysis.completed_at = timezone.now()
                analysis.progress_percent = 100
                analysis.progress_message = 'Aucune donnée domaine.'
                analysis.save()
            return result

        report(
            20,
            f'{len(snapshots)} domaine(s) · {sessions_total} analyse(s) récente(s) — '
            f'recherche web opportunités & prix…',
        )
        web_context = ''
        try:
            web_context = cls.fetch_sourcing_web_context(
                snapshots,
                should_cancel=should_cancel,
                progress=report,
            )
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning('Web sourcing Import Master : %s', exc)

        if analysis and analysis.status != ImportMasterDomainAnalysis.Status.STOPPED:
            analysis.web_context = web_context
            analysis.domains_snapshot = snapshots
            analysis.save(update_fields=['web_context', 'domains_snapshot'])

        report(55, 'Analyse IA — comparaison, opportunités et prix…')
        try:
            if DeepSeekAnalysisService.is_enabled():
                result = cls.analyze(snapshots, web_context)
            else:
                result = cls.normalize_result({}, snapshots)
                result['resume'] = (
                    'Analyse IA désactivée — classement basique sur notes Trade Intelligence. '
                    'Configurez la clé API pour opportunités web et prix sourcing.'
                )
                result['commentaire_global'] = result['resume']
                result['alertes'] = ['Analyse IA désactivée ou clé absente.']
        except Exception as exc:
            logger.exception('Analyse Import Master IA échouée')
            result = cls.normalize_result({}, snapshots)
            result['resume'] = f'Analyse partielle — erreur moteur IA : {exc}'
            result['commentaire_global'] = result['resume']
            result['alertes'] = [str(exc)[:200]]
            if analysis:
                analysis.error_message = str(exc)[:2000]

        if should_cancel and should_cancel():
            raise RuntimeError('Analyse annulée par l’utilisateur.')

        report(95, 'Enregistrement du rapport…')
        if analysis and analysis.status != ImportMasterDomainAnalysis.Status.STOPPED:
            # Recharger pour éviter d’écraser un STOP pendant l’analyse
            analysis.refresh_from_db()
            if analysis.status == ImportMasterDomainAnalysis.Status.STOPPED:
                raise RuntimeError('Analyse annulée par l’utilisateur.')
            analysis.analysis_result = result
            analysis.status = ImportMasterDomainAnalysis.Status.DONE
            analysis.completed_at = timezone.now()
            analysis.progress_percent = 100
            analysis.progress_message = 'Rapport comparative terminé.'
            analysis.save()

        report(100, 'Rapport comparative terminé.')
        return result
