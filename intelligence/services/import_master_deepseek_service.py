"""
Analyse comparative Import Master via DeepSeek-v4-flash.
Compare les analyses Trade Intelligence déjà passées (tous domaines),
recherche web marché SN (min/max) + sourcing Alibaba/AliExpress/Amazon.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models import Avg, Max, Min, Q
from django.utils import timezone
from openai import OpenAI

from intelligence.models import JijiListing, JumiaProduct, MarketResearchSession
from intelligence.services.deepseek_analysis_service import DeepSeekAnalysisService

logger = logging.getLogger(__name__)

TOP_PRODUCTS_IMPORT = 10
TOP_OPPORTUNITIES = 5
WEB_CONTEXT_MAX_CHARS = 16000
DOMAINS_JSON_MAX_CHARS = 16000
USER_WEB_CONTEXT_MAX_CHARS = 12000

COMPARE_SYSTEM = """Tu es un analyste import senior pour YAYEMATY MARKET (Sénégal, XOF).
Tu produis UNIQUEMENT du JSON valide, sans markdown.
Mission :
1) Comparer les résultats d'analyse Trade Intelligence DÉJÀ PASSÉS (domaines + Top produits).
2) Identifier EXACTEMENT 5 meilleures opportunités d'importation (Top 5).
3) Pour CHAQUE produit Top 10 : fourchette MARCHÉ SN (prix_sn_min_xof / prix_sn_max_xof)
   via le marché sénégalais (annonces locales, marketplaces, réseaux — web ouvert).
4) Estimer prix sourcing international ($) + coût landed XOF
   (plateformes type gros Chine / wholesale — Import Master uniquement).
5) Calculer marges cohérentes : marge ≈ prix_SN − prix_landed_xof (pas de marge inventée).
6) Classer domaines et produits selon demande réelle, marge et risque stock.

Règles prix ABSOLUES :
- SOURCE DE VÉRITÉ = section RECHERCHE WEB ci-dessous (pas les chiffres des analyses TI).
- Les notes/synthèses Trade Intelligence sont des HYPOTHÈSES à confirmer ou infirmer via le web.
- Ne jamais recopier un prix TI sans confirmation web ; si contradiction → prix web + note plus basse.
- prix_sn_min_xof ≤ prix_sn_max_xof (entiers XOF) — fourchette confirmée par le web uniquement.
- marge_pct entre 5 et 70 si données web crédibles ; sinon baisser la note et alerter.
- Cohérence obligatoire : prix sourcing ($) × taux + fret/douane ≈ landed XOF ; marge = SN − landed.
- Pas de fourchettes fantaisistes (ex. sac engrais 50 kg à $380 si le marché local est ~20 000 XOF).
- Fourchettes sourcing « $min – $max » UNIQUEMENT si trouvées sur le web ; sinon "".
- Si aucun prix fiable : champs vides, fiabilite_prix = "estime" ou "faible", note plafonnée.

Réflexion (thinking) avant JSON :
1) Croiser web vs hypothèses TI pour chaque produit Top.
2) Vérifier unités (sac/kg/pièce) et ordres de grandeur SN vs international.
3) Rejeter ou corriger tout chiffre incohérent avant de produire le JSON.

Commentaires (synthese, commentaire_analyste, commentaire opportunités) :
- Ton décideur : concret, convaincant, réaliste (saisonnalité, rotation, risque stock, marge %).
- INTERDIT de citer des noms de sites / plateformes (pas Jumia, Jiji, Alibaba, TikTok, etc.).
  Dire « marché local », « annonces en ligne », « sourcing gros », « revente Dakar ».
- 1–2 phrases max, chiffres utiles (prix SN min–max, marge %) quand disponibles.

Recommandations EXACTES :
« Bon, je vous le recommande » | « Peut faire l'affaire mais moyen » | « À éviter »
JSON compact obligatoire (évite troncature) : pas de blabla, listes ≤ 4 items.
"""

COMPARE_USER = """Analyse comparative d'importation YAYEMATY.

=== ANALYSES TRADE INTELLIGENCE (contexte produits / notes — PAS source de prix) ===
{domains_json}

=== RECHERCHE WEB — SOURCE DE VÉRITÉ (prix marché SN + sourcing à vérifier) ===
{web_context}

Consignes :
- Les prix et marges DOIVENT provenir de la RECHERCHE WEB ; croiser plusieurs résultats web.
- Si le web contredit une synthèse TI : suivre le web, baisser la note, alerter dans commentaire_prix.
- Chaque domaine inclut la dernière analyse TI récente : Top 5 produits (sans recopier leurs prix).
- Compare les domaines : demande réelle, marge après vérification web, risque stock, concurrence.
- EXACTEMENT 10 produits dans produits_import (Top 10), triés par note décroissante.
- EXACTEMENT 5 meilleures_opportunites (Top 5), alignées sur les meilleurs produits vérifiés.
- Fourchettes « $min – $max » seulement si trouvées sur le web ; sinon "".
- fiabilite_prix : "web" (confirmé web), "estime" (peu de sources), "faible" (incohérent / non trouvé).
- resume / commentaires : convaincants, réalistes, SANS nommer de sites web.

Réponds avec ce JSON exact :
{{
  "resume": "Synthèse 3–5 phrases avec fourchettes SN et marges % des priorités.",
  "commentaire_global": "Commentaire analyste (marché SN, sourcing, timing).",
  "methodologie": "TI (contexte) + vérification web SN ouvert + sourcing international confirmé.",
  "classement_domaines": [
    {{
      "rang": 1,
      "domaine": "...",
      "note_globale": 8.5,
      "recommandation": "Bon, je vous le recommande",
      "synthese": "Pourquoi ce domaine…",
      "commentaire_analyste": "Lecture détaillée avec prix/marges…",
      "points_forts": ["...", "..."],
      "risques": ["..."],
      "opportunites_cles": ["Produit…"]
    }}
  ],
  "comparaison": [
    {{
      "domaine_a": "...",
      "domaine_b": "...",
      "verdict": "A vs B…",
      "critere": "demande|marge|concurrence|prix_import",
      "commentaire": "Face-à-face chiffré…"
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
      "commentaire": "Pourquoi — citer prix SN min–max et marge %…",
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
      "commentaire_analyste": "Analyse prix + demande + risque…",
      "commentaire_prix": "Lecture prix SN min–max vs landed…",
      "prix_sn_min_xof": 22000,
      "prix_sn_max_xof": 25000,
      "prix_sn_median_xof": 23500,
      "prix_sn_xof": "22 000 – 25 000 XOF",
      "prix_alibaba_usd": "$18 – $22",
      "prix_alibaba_usd_min": 18,
      "prix_alibaba_usd_max": 22,
      "prix_aliexpress_usd": "$20 – $28 ou \"\" si non trouvé",
      "prix_amazon_usd": "$25 – $35 ou \"\" si non trouvé",
      "prix_made_in_china_usd": "",
      "prix_potentiel_achat_xof": "15 000 XOF",
      "prix_landed_xof": 15000,
      "marge_min_xof": 7000,
      "marge_max_xof": 10000,
      "marge_pct": 32,
      "marge_estimee_xof": "7 000 – 10 000 XOF (~32%)",
      "fiabilite_prix": "web|estime|faible",
      "sources_prix": ["jumia.sn", "jiji.sn", "alibaba.com", "made-in-china.com"]
    }}
  ],
  "alertes": ["Risque ou point de vigilance…"]
}}
"""


class ImportMasterDeepSeekService:
    """Compare domaines déjà analysés + opportunités / prix web via DeepSeek."""

    SESSIONS_PER_DOMAIN = 1
    TOP_PRODUCTS_PER_SESSION = 5
    MAX_SESSION_AGE_DAYS = 90

    # Prioritaires Import Master — sourcing international UNIQUEMENT ici (pas TI).
    # Recherche API = web ouvert : d'autres sites marché SN / sourcing restent autorisés.
    IMPORT_WEB_PREFERRED_DOMAINS = (
        # Marché Sénégal
        'jumia.sn',
        'jiji.sn',
        'promo.sn',
        'expat-dakar.com',
        'sn.coinafrique.com',
        'jemba.sn',
        'dakarcenter.com',
        'occasiondakar.com',
        'taftaf.sn',
        'facebook.com',
        'instagram.com',
        'tiktok.com',
        # Sourcing / import (hors Trade Intelligence)
        'alibaba.com',
        'aliexpress.com',
        'amazon.com',
        'made-in-china.com',
        '1688.com',
        'dhgate.com',
        'globalsources.com',
        'yiwugo.com',
        'hktdc.com',
    )

    IMPORT_WEB_SITES_NOTE = (
        'Marché SN : commence par les sites prioritaires sénégalais, puis élargis '
        'à TOUT autre site web pertinent pour les prix au Sénégal. '
        'Sourcing international : Alibaba, AliExpress, Amazon, Made-in-China, '
        '1688, DHgate, Global Sources, Yiwugo, HKTDC '
        '(ces plateformes d’import sont réservées à Import Master). '
        'La recherche reste ouverte hors de cette liste.'
    )

    WEB_FOCUSES = (
        'vérification croisée prix SN : confirmer ou infirmer chaque produit Top '
        'via plusieurs sources web (min/max XOF, écarter chiffres non confirmés)',
        'prix les plus bas marché Sénégal : annonces en ligne + web ouvert '
        '(prix min XOF par modèle, unité claire sac/kg/pièce)',
        'prix les plus hauts / premium marché Sénégal : web ouvert '
        '(prix max XOF par modèle)',
        'prix gros sourcing international ($) + coût landed XOF '
        '(fret + douane — cohérent avec le produit et l’unité)',
        'prix retail/wholesale AliExpress Amazon vs revente marché SN vérifiée',
        'marges revendeur Sénégal réalistes après vérification web '
        '(prix SN confirmé − landed) — rejeter les marges >70% non crédibles',
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
        domain_slugs: list[str] | None = None,
    ) -> list[dict]:
        """
        Dernière session DONE/STOPPED par domaine (défaut : 1 analyse, Top 5).
        ``domain_slugs`` : filtre optionnel (sélection UI).
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
        selected = {
            str(s).strip() for s in (domain_slugs or []) if str(s).strip()
        }

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
        if selected:
            base_qs = base_qs.filter(domain_slug__in=selected)
        all_slugs = sorted(set(
            base_qs.values_list('domain_slug', flat=True)
        ))
        # Conserve l’ordre de sélection UI si fourni
        if selected:
            ordered_selected = [s for s in domain_slugs if s in selected and s in all_slugs]
            for s in all_slugs:
                if s not in ordered_selected:
                    ordered_selected.append(s)
            slug_list = ordered_selected
        else:
            slug_list = all_slugs
        ordered_qs = base_qs.order_by('-completed_at', '-id')

        snapshots = []
        for slug in slug_list:
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

    # ------------------------------------------------------------------ prix locaux BDD

    @staticmethod
    def _query_tokens(name: str) -> list[str]:
        stop = {
            'et', 'de', 'du', 'la', 'le', 'les', 'des', 'un', 'une', 'pour',
            'avec', 'au', 'en', 'kg', 'sac', 'pack', 'set',
        }
        return [
            t for t in re.findall(r'[a-z0-9]+', (name or '').lower())
            if len(t) >= 2 and t not in stop
        ][:6]

    @classmethod
    def _price_stats_from_values(cls, prices: list) -> dict | None:
        if not prices:
            return None
        nums = []
        for p in prices:
            try:
                nums.append(float(p))
            except (TypeError, ValueError):
                continue
        if not nums:
            return None
        nums.sort()
        mid = nums[len(nums) // 2]
        return {
            'min_xof': int(round(nums[0])),
            'max_xof': int(round(nums[-1])),
            'avg_xof': int(round(sum(nums) / len(nums))),
            'median_xof': int(round(mid)),
            'n': len(nums),
        }

    @classmethod
    def _lookup_jumia_prices(cls, tokens: list[str]) -> dict | None:
        if not tokens:
            return None
        q = Q()
        for t in tokens[:4]:
            q &= Q(name__icontains=t)
        qs = JumiaProduct.objects.filter(q).exclude(price_xof__isnull=True)
        agg = qs.aggregate(mn=Min('price_xof'), mx=Max('price_xof'), av=Avg('price_xof'))
        if agg['mn'] is None:
            # Fallback OR plus large
            q_or = Q()
            for t in tokens[:3]:
                q_or |= Q(name__icontains=t)
            qs = JumiaProduct.objects.filter(q_or).exclude(price_xof__isnull=True)[:40]
            prices = list(qs.values_list('price_xof', flat=True))
            stats = cls._price_stats_from_values(prices)
            if stats:
                stats['source'] = 'jumia'
            return stats
        return {
            'min_xof': int(round(float(agg['mn']))),
            'max_xof': int(round(float(agg['mx']))),
            'avg_xof': int(round(float(agg['av'] or 0))),
            'median_xof': int(round(float(agg['av'] or 0))),
            'n': qs.count(),
            'source': 'jumia',
        }

    @classmethod
    def _lookup_jiji_prices(cls, tokens: list[str]) -> dict | None:
        if not tokens:
            return None
        q = Q()
        for t in tokens[:4]:
            q &= Q(title__icontains=t)
        qs = JijiListing.objects.filter(q).exclude(price_xof__isnull=True)
        agg = qs.aggregate(mn=Min('price_xof'), mx=Max('price_xof'), av=Avg('price_xof'))
        if agg['mn'] is None:
            q_or = Q()
            for t in tokens[:3]:
                q_or |= Q(title__icontains=t)
            qs = JijiListing.objects.filter(q_or).exclude(price_xof__isnull=True)[:40]
            prices = list(qs.values_list('price_xof', flat=True))
            stats = cls._price_stats_from_values(prices)
            if stats:
                stats['source'] = 'jiji'
            return stats
        return {
            'min_xof': int(round(float(agg['mn']))),
            'max_xof': int(round(float(agg['mx']))),
            'avg_xof': int(round(float(agg['av'] or 0))),
            'median_xof': int(round(float(agg['av'] or 0))),
            'n': qs.count(),
            'source': 'jiji',
        }

    @classmethod
    def enrich_snapshots_with_local_prices(cls, snapshots: list[dict]) -> list[dict]:
        """
        Injecte ``prix_locaux_bdd`` (min/avg/max) Jumia+Jiji
        pour chaque produit candidat — prioritaire pour DeepSeek.
        """
        for snap in snapshots:
            local_prices: list[dict] = []
            for item in cls._iter_snapshot_products(snap):
                name = (item.get('produit') or '').strip()
                if not name:
                    continue
                tokens = cls._query_tokens(name)
                jumia = cls._lookup_jumia_prices(tokens)
                jiji = cls._lookup_jiji_prices(tokens)
                if not jumia and not jiji:
                    continue
                mins, maxs, avgs = [], [], []
                sources = []
                for block in (jumia, jiji):
                    if not block:
                        continue
                    mins.append(block['min_xof'])
                    maxs.append(block['max_xof'])
                    avgs.append(block['avg_xof'])
                    sources.append(block.get('source', ''))
                entry = {
                    'produit': name[:200],
                    'min_xof': min(mins),
                    'max_xof': max(maxs),
                    'avg_xof': int(round(sum(avgs) / len(avgs))),
                    'sources': [s for s in sources if s],
                    'jumia': jumia,
                    'jiji': jiji,
                }
                local_prices.append(entry)
                item['prix_locaux_bdd'] = {
                    'min_xof': entry['min_xof'],
                    'max_xof': entry['max_xof'],
                    'avg_xof': entry['avg_xof'],
                    'sources': entry['sources'],
                }
            snap['prix_locaux_bdd'] = local_prices[:20]
        return snapshots

    @classmethod
    def _snapshots_for_ai_prompt(cls, snapshots: list[dict]) -> list[dict]:
        """
        Payload envoyé à DeepSeek : contexte TI uniquement (pas de prix BDD locale).
        Les prix doivent être vérifiés via la recherche web, pas injectés depuis PostgreSQL.
        """
        cleaned: list[dict] = []
        for snap in snapshots:
            if not isinstance(snap, dict):
                continue
            entry = {
                k: v for k, v in snap.items()
                if k not in ('prix_locaux_bdd',)
            }
            sessions_out = []
            for session in entry.get('sessions') or []:
                if not isinstance(session, dict):
                    continue
                sess = dict(session)
                tops = []
                for item in sess.get('top_produits') or []:
                    if not isinstance(item, dict):
                        continue
                    prod = {
                        k: v for k, v in item.items()
                        if k != 'prix_locaux_bdd'
                    }
                    tops.append(prod)
                sess['top_produits'] = tops
                sessions_out.append(sess)
            entry['sessions'] = sessions_out
            if entry.get('top_produits'):
                entry['top_produits'] = [
                    {k: v for k, v in item.items() if k != 'prix_locaux_bdd'}
                    for item in entry['top_produits']
                    if isinstance(item, dict)
                ]
            cleaned.append(entry)
        return cleaned

    # ------------------------------------------------------------------ web

    @classmethod
    def fetch_sourcing_web_context(
        cls,
        snapshots: list[dict],
        *,
        should_cancel=None,
        progress=None,
    ) -> str:
        """Recherches web : marché SN min/max + sourcing international."""
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
                f'Produits Top : {product_hint}. Domaines : {domains}. '
                f'Vérifie et croise les prix (min/max XOF marché Sénégal + sourcing $) '
                f'pour chaque produit — plusieurs sources web, unités claires, '
                f'rejette les chiffres incohérents ou non confirmés.',
                domain_label='Import multi-domaines YAYEMATY',
                focus_hint=focus,
                preferred_domains=list(cls.IMPORT_WEB_PREFERRED_DOMAINS),
                open_search=True,
                extra_sites_note=cls.IMPORT_WEB_SITES_NOTE,
            )
            if chunk:
                chunks.append(f'--- {focus} ---\n{chunk}')
        return '\n\n'.join(chunks)[:WEB_CONTEXT_MAX_CHARS]

    # ------------------------------------------------------------------ parse / format prix

    @staticmethod
    def _parse_number(value) -> int | None:
        if value is None or value == '':
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float, Decimal)):
            n = int(round(float(value)))
            return n if n >= 0 else None
        text = str(value).strip().lower().replace('\u00a0', ' ').replace(',', '.')
        if not text:
            return None
        # "22 000", "22000", "22k", "95–120k" → premier nombre utile
        mult = 1
        if re.search(r'\bk\b', text) or text.endswith('k'):
            mult = 1000
        m = re.search(r'(\d+(?:\.\d+)?)', text.replace(' ', ''))
        if not m:
            m = re.search(r'(\d+(?:\.\d+)?)', text)
        if not m:
            return None
        try:
            n = float(m.group(1)) * mult
            # Si "95-120k" et on a lu 95 avec mult 1000 → 95000 OK
            if 'k' in text and n < 1000:
                n *= 1000
            return int(round(n))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_range_from_text(text: str) -> tuple[int | None, int | None]:
        raw = (text or '').strip().lower().replace('\u00a0', ' ')
        if not raw:
            return None, None
        # Ignore devises pour parser $18 – $22 / 18–22 USD
        raw = re.sub(r'[$€£]', '', raw)
        # 22 000 - 25 000 | 95–120k | 22000–25000
        pattern = re.compile(
            r'(\d[\d\s.]*)\s*(k)?\s*[-–—àa]+\s*(\d[\d\s.]*)\s*(k)?',
            re.I,
        )
        m = pattern.search(raw.replace(',', '.'))
        if not m:
            single = ImportMasterDeepSeekService._parse_number(raw)
            return single, single
        a = float(re.sub(r'\s+', '', m.group(1)))
        b = float(re.sub(r'\s+', '', m.group(3)))
        if m.group(2) or m.group(4) or 'k' in raw:
            if a < 1000:
                a *= 1000
            if b < 1000:
                b *= 1000
        lo, hi = int(round(a)), int(round(b))
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    @staticmethod
    def _format_xof(n: int | None) -> str:
        if n is None:
            return ''
        return f'{n:,}'.replace(',', ' ') + ' XOF'

    @staticmethod
    def _is_blank_price_label(text: str) -> bool:
        t = (text or '').strip().lower().replace('\u00a0', ' ')
        if not t or t in ('—', '-', '…', '...', 'n/a', 'na', 'nd', 'n.d.'):
            return True
        markers = (
            'non pertinent', 'non applicable', 'indisponible', 'sans objet',
            'pas pertinent', 'not relevant', 'unavailable', 'aucun prix',
        )
        return any(m in t for m in markers)

    @staticmethod
    def _format_usd_amount(n: float | int) -> str:
        value = float(n)
        if abs(value - round(value)) < 0.05:
            return f'${int(round(value))}'
        return f'${value:.2f}'.rstrip('0').rstrip('.')

    @classmethod
    def _format_usd_range(cls, lo: float | int | None, hi: float | int | None) -> str:
        if lo is None and hi is None:
            return ''
        if lo is None:
            return cls._format_usd_amount(hi)
        if hi is None or float(lo) == float(hi):
            return cls._format_usd_amount(lo)
        a, b = float(lo), float(hi)
        if a > b:
            a, b = b, a
        return f'{cls._format_usd_amount(a)} – {cls._format_usd_amount(b)}'

    @classmethod
    def _coerce_usd_display(
        cls,
        text: str | None,
        *,
        lo: float | int | None = None,
        hi: float | int | None = None,
        allow_numeric_fallback: bool = True,
    ) -> str:
        """
        Fourchette display « $18 – $22 ».
        Retourne '' si aucun prix réel (pas d’estimation inventée).
        """
        raw = str(text or '').strip()
        if cls._is_blank_price_label(raw):
            if allow_numeric_fallback and (lo is not None or hi is not None):
                return cls._format_usd_range(lo, hi)
            return ''
        t_lo, t_hi = cls._parse_range_from_text(raw)
        if t_lo is not None or t_hi is not None:
            return cls._format_usd_range(t_lo, t_hi)
        if allow_numeric_fallback and (lo is not None or hi is not None):
            return cls._format_usd_range(lo, hi)
        cleaned = re.sub(r'\bUSD\b', '', raw, flags=re.I).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned)
        if cleaned.startswith('$') and re.search(r'\d', cleaned):
            return cleaned[:80]
        if re.search(r'\d', cleaned):
            return f'${cleaned}'[:80]
        return ''

    @classmethod
    def _resolve_platform_price(cls, text: str | None) -> str:
        """Prix plateforme uniquement s’il est présent et chiffré — sinon masqué."""
        return cls._coerce_usd_display(text, allow_numeric_fallback=False)

    @classmethod
    def _format_sn_range(cls, lo: int | None, hi: int | None) -> str:
        if lo is None and hi is None:
            return ''
        if lo is None:
            return cls._format_xof(hi)
        if hi is None or lo == hi:
            return cls._format_xof(lo)
        a = f'{lo:,}'.replace(',', ' ')
        b = f'{hi:,}'.replace(',', ' ')
        return f'{a} – {b} XOF'

    @classmethod
    def _format_marge_display(
        cls,
        marge_min: int | None,
        marge_max: int | None,
        marge_pct: float | None,
    ) -> str:
        parts = []
        if marge_min is not None and marge_max is not None:
            if marge_min == marge_max:
                parts.append(cls._format_xof(marge_min))
            else:
                a = f'{marge_min:,}'.replace(',', ' ')
                b = f'{marge_max:,}'.replace(',', ' ')
                parts.append(f'{a} – {b} XOF')
        elif marge_min is not None:
            parts.append(cls._format_xof(marge_min))
        elif marge_max is not None:
            parts.append(cls._format_xof(marge_max))
        if marge_pct is not None:
            parts.append(f'~{marge_pct:.0f}%')
        return ' · '.join(parts) if parts else ''

    @classmethod
    def _normalize_product_prices(cls, row: dict) -> dict:
        """Parse / coerce fourchettes SN + marges ; génère libellés display."""
        sn_min = cls._parse_number(row.get('prix_sn_min_xof'))
        sn_max = cls._parse_number(row.get('prix_sn_max_xof'))
        sn_med = cls._parse_number(row.get('prix_sn_median_xof'))
        if sn_min is None or sn_max is None:
            t_lo, t_hi = cls._parse_range_from_text(str(row.get('prix_sn_xof') or ''))
            sn_min = sn_min if sn_min is not None else t_lo
            sn_max = sn_max if sn_max is not None else t_hi
        if sn_min is not None and sn_max is not None and sn_min > sn_max:
            sn_min, sn_max = sn_max, sn_min
        if sn_med is None and sn_min is not None and sn_max is not None:
            sn_med = int(round((sn_min + sn_max) / 2))

        landed = cls._parse_number(
            row.get('prix_landed_xof') or row.get('prix_potentiel_achat_xof'),
        )
        if landed is None:
            t_lo, t_hi = cls._parse_range_from_text(
                str(row.get('prix_potentiel_achat_xof') or ''),
            )
            if t_lo is not None and t_hi is not None:
                landed = int(round((t_lo + t_hi) / 2))
            else:
                landed = t_lo or t_hi

        marge_min = cls._parse_number(row.get('marge_min_xof'))
        marge_max = cls._parse_number(row.get('marge_max_xof'))
        try:
            marge_pct = float(row.get('marge_pct')) if row.get('marge_pct') not in (None, '') else None
        except (TypeError, ValueError):
            marge_pct = None

        # Recalcul marge si absurde / manquante
        alert = ''
        if sn_min is not None and sn_max is not None and landed is not None and landed > 0:
            calc_min = sn_min - landed
            calc_max = sn_max - landed
            mid_sn = sn_med if sn_med is not None else int(round((sn_min + sn_max) / 2))
            calc_pct = ((mid_sn - landed) / mid_sn * 100) if mid_sn > 0 else None
            incoherent = (
                marge_min is None
                or marge_max is None
                or marge_min < 0
                or (marge_pct is not None and (marge_pct < 0 or marge_pct > 80))
            )
            if incoherent and calc_max > 0:
                marge_min = max(0, calc_min)
                marge_max = max(marge_min, calc_max)
                marge_pct = round(max(0.0, min(80.0, calc_pct or 0.0)), 1)
                alert = 'marge_recalculee'
            elif calc_max <= 0:
                alert = 'marge_negative_estimee'
                if marge_pct is None:
                    marge_pct = 0.0
                marge_min = marge_min if marge_min is not None else 0
                marge_max = marge_max if marge_max is not None else 0

        fiabilite = str(row.get('fiabilite_prix') or '').strip().lower()
        if fiabilite in ('bdd', 'mixte'):
            fiabilite = 'web'
        if fiabilite not in ('web', 'estime', 'faible'):
            sources = ' '.join(str(s) for s in (row.get('sources_prix') or [])).lower()
            if sources and sn_min is not None:
                fiabilite = 'web'
            elif sn_min is not None:
                fiabilite = 'estime'
            else:
                fiabilite = 'faible'

        prix_sn_xof = str(row.get('prix_sn_xof') or '').strip()
        if not prix_sn_xof or sn_min is not None:
            generated = cls._format_sn_range(sn_min, sn_max)
            if generated:
                prix_sn_xof = generated

        marge_display = cls._format_marge_display(marge_min, marge_max, marge_pct)
        if not marge_display:
            marge_display = str(row.get('marge_estimee_xof') or '')[:80]

        prix_achat = str(row.get('prix_potentiel_achat_xof') or '').strip()
        if landed is not None and (not prix_achat or prix_achat.isdigit()):
            prix_achat = cls._format_xof(landed)

        return {
            'prix_sn_min_xof': sn_min,
            'prix_sn_max_xof': sn_max,
            'prix_sn_median_xof': sn_med,
            'prix_sn_xof': prix_sn_xof[:80],
            'prix_landed_xof': landed,
            'prix_potentiel_achat_xof': prix_achat[:80],
            'marge_min_xof': marge_min,
            'marge_max_xof': marge_max,
            'marge_pct': marge_pct,
            'marge_estimee_xof': marge_display[:80],
            'fiabilite_prix': fiabilite,
            '_price_alert': alert,
        }

    @classmethod
    def _adjust_domain_notes(cls, ranking: list[dict], products: list[dict]) -> list[dict]:
        """Légère pondération : domaines sans prix SN fiables légèrement rétrogradés."""
        by_domain: dict[str, list[dict]] = {}
        for p in products:
            d = (p.get('domaine') or '').strip().lower()
            if d:
                by_domain.setdefault(d, []).append(p)

        for row in ranking:
            key = (row.get('domaine') or '').strip().lower()
            prods = by_domain.get(key) or []
            note = float(row.get('note_globale') or 0)
            if not prods:
                row['note_globale'] = round(max(0.0, note - 0.3), 1)
                continue
            reliable = sum(
                1 for p in prods
                if p.get('fiabilite_prix') in ('web', 'estime')
                and p.get('prix_sn_min_xof') is not None
            )
            pcts = [
                float(p['marge_pct'])
                for p in prods
                if p.get('marge_pct') is not None
            ]
            avg_marge = sum(pcts) / len(pcts) if pcts else None
            if reliable == 0:
                note -= 0.5
            elif reliable >= 2 and avg_marge is not None and 15 <= avg_marge <= 55:
                note += 0.2
            elif avg_marge is not None and (avg_marge < 5 or avg_marge > 75):
                note -= 0.4
            row['note_globale'] = round(max(0.0, min(10.0, note)), 1)
            row['recommandation'] = DeepSeekAnalysisService._recommendation_for_note(
                row['note_globale'], row.get('recommandation') or '',
            )
        ranking.sort(key=lambda x: x['note_globale'], reverse=True)
        for i, row in enumerate(ranking, start=1):
            row['rang'] = i
        return ranking

    # ------------------------------------------------------------------ analyse / normalize

    @classmethod
    def analyze(cls, snapshots: list[dict], web_context: str) -> dict:
        """Appel deepseek-v4-flash — comparaison + opportunités + prix."""
        cfg = DeepSeekAnalysisService._config()
        api_key = cfg.get('API_KEY', '')
        if not api_key:
            raise RuntimeError('DEEPSEEK_API_KEY non configurée.')

        client = OpenAI(api_key=api_key, base_url=cfg.get('BASE_URL', 'https://api.deepseek.com'))
        prompt_snapshots = cls._snapshots_for_ai_prompt(snapshots)
        domains_json = json.dumps(
            prompt_snapshots, ensure_ascii=False, separators=(',', ':'),
        )[:DOMAINS_JSON_MAX_CHARS]
        web_max = DeepSeekAnalysisService._char_limit(
            'ANALYSIS_WEB_CONTEXT_MAX_CHARS', USER_WEB_CONTEXT_MAX_CHARS,
        )
        user_content = COMPARE_USER.format(
            domains_json=domains_json,
            web_context=(web_context or 'Aucun contexte web — ne pas inventer de prix.')[:web_max],
        )
        max_tokens = max(8192, min(int(cfg.get('MAX_TOKENS', 8192)), 16384))
        timeout = float(cfg.get('TIMEOUT_SECONDS', 120))
        extra_think = DeepSeekAnalysisService._chat_extra_body(
            cfg, for_import_master=True,
        )
        extra_plain = {'thinking': {'type': 'disabled'}}
        model = cfg.get('MODEL', 'deepseek-v4-flash')

        def _call(messages: list[dict], *, extra_body: dict | None = None) -> tuple[str, str]:
            body = extra_body if extra_body is not None else extra_think
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={'type': 'json_object'},
                max_tokens=max_tokens,
                timeout=timeout,
                extra_body=body,
            )
            choice = response.choices[0]
            finish = getattr(choice, 'finish_reason', '') or ''
            raw = DeepSeekAnalysisService._extract_completion_content(choice.message)
            return raw, finish

        messages = [
            {'role': 'system', 'content': COMPARE_SYSTEM},
            {'role': 'user', 'content': user_content},
        ]
        raw, finish = _call(messages)
        if not raw.strip():
            logger.warning(
                'Import Master : réponse vide (thinking) — retry sans thinking.',
            )
            raw, finish = _call(messages, extra_body=extra_plain)
        if finish == 'length':
            logger.warning(
                'Import Master : réponse DeepSeek tronquée (finish_reason=length, '
                '%s chars) — réparation / retry.',
                len(raw),
            )
        try:
            parsed = DeepSeekAnalysisService._parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as first_exc:
            # Retry compact : JSON plus court (commentaires ≤ 1 phrase)
            logger.warning('Import Master JSON invalide (%s) — retry compact.', first_exc)
            retry_messages = messages + [
                {'role': 'assistant', 'content': raw[:12000]},
                {
                    'role': 'user',
                    'content': (
                        'Le JSON précédent est INCOMPLET/INVALIDE. '
                        'Renvoie UNIQUEMENT un JSON COMPLET et VALIDE, plus compact : '
                        'commentaires ≤ 1 phrase, listes ≤ 3 items, '
                        'EXACTEMENT 10 produits_import avec fourchettes prix. '
                        'Pas de markdown.'
                    ),
                },
            ]
            raw2, finish2 = _call(retry_messages, extra_body=extra_plain)
            if finish2 == 'length':
                logger.warning('Import Master retry encore tronqué (%s chars).', len(raw2))
            try:
                parsed = DeepSeekAnalysisService._parse_json_response(raw2)
            except (ValueError, json.JSONDecodeError):
                # Dernier recours : réparer la 1ʳᵉ réponse partielle
                repaired = DeepSeekAnalysisService._repair_truncated_json(
                    DeepSeekAnalysisService._strip_json_fences(raw),
                )
                if repaired is None:
                    raise first_exc
                parsed = repaired
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
                'synthese': cls._sanitize_public_comment(row.get('synthese') or '')[:360],
                'commentaire_analyste': cls._sanitize_public_comment(
                    row.get('commentaire_analyste') or row.get('synthese') or '',
                )[:500],
                'points_forts': [
                    cls._sanitize_public_comment(x)[:140]
                    for x in (row.get('points_forts') or [])[:5]
                ],
                'risques': [
                    cls._sanitize_public_comment(x)[:140]
                    for x in (row.get('risques') or [])[:5]
                ],
                'opportunites_cles': [
                    cls._sanitize_public_comment(x)[:160]
                    for x in (row.get('opportunites_cles') or [])[:5]
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
                synth = cls._default_domain_comment(snap['domaine'], avg, i)
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
                'commentaire': cls._sanitize_public_comment(row.get('commentaire') or '')[:450],
                'action': str(row.get('action') or '')[:120],
            })

        products = []
        price_alerts: list[str] = []
        for i, row in enumerate(data.get('produits_import') or [], start=1):
            if not isinstance(row, dict):
                continue
            try:
                note = float(row.get('note') or 0)
            except (TypeError, ValueError):
                note = 0.0
            note = max(0.0, min(10.0, note))
            price_fields = cls._normalize_product_prices(row)
            alert = price_fields.pop('_price_alert', '')
            if alert:
                pname = str(row.get('produit') or '')[:80]
                if alert == 'marge_recalculee':
                    price_alerts.append(f'Marge recalculée pour « {pname} » (cohérence SN − landed).')
                elif alert == 'marge_negative_estimee':
                    price_alerts.append(
                        f'Marge faible/négative estimée pour « {pname} » — vérifier les prix.'
                    )
                    note = min(note, 5.5)
            usd_min = cls._parse_number(row.get('prix_alibaba_usd_min'))
            usd_max = cls._parse_number(row.get('prix_alibaba_usd_max'))
            alibaba_raw = str(row.get('prix_alibaba_usd') or '')
            if usd_min is None or usd_max is None:
                a_lo, a_hi = cls._parse_range_from_text(alibaba_raw)
                usd_min = usd_min if usd_min is not None else a_lo
                usd_max = usd_max if usd_max is not None else a_hi
            # Uniquement les prix réellement trouvés — pas d’estimation croisée
            alibaba = cls._resolve_platform_price(alibaba_raw)
            if not alibaba and usd_min is not None and not alibaba_raw.strip():
                alibaba = cls._format_usd_range(usd_min, usd_max)
            aliexpress = cls._resolve_platform_price(row.get('prix_aliexpress_usd'))
            amazon = cls._resolve_platform_price(row.get('prix_amazon_usd'))
            products.append({
                'rang': int(row.get('rang') or i),
                'produit': str(row.get('produit') or '')[:200],
                'domaine': str(row.get('domaine') or '')[:120],
                'note': round(note, 1),
                'recommandation': reco_for(note, str(row.get('recommandation') or '')),
                'synthese': cls._sanitize_public_comment(row.get('synthese') or '')[:360],
                'commentaire_analyste': cls._sanitize_public_comment(
                    row.get('commentaire_analyste') or row.get('synthese') or '',
                )[:500],
                'prix_alibaba_usd': alibaba[:80],
                'prix_alibaba_usd_min': usd_min if alibaba else None,
                'prix_alibaba_usd_max': usd_max if alibaba else None,
                'prix_aliexpress_usd': aliexpress[:80],
                'prix_amazon_usd': amazon[:80],
                'show_alibaba': bool(alibaba),
                'show_aliexpress': bool(aliexpress),
                'show_amazon': bool(amazon),
                'sources_prix': [
                    str(s) for s in (row.get('sources_prix') or []) if s
                ][:8],
                **price_fields,
            })

        # Fallback produits depuis snapshots TI (sans prix BDD — web requis)
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
            for i, (n, domaine, item) in enumerate(flat[:TOP_PRODUCTS_IMPORT], start=1):
                price_fields = cls._normalize_product_prices({
                    'fiabilite_prix': 'faible',
                })
                price_fields.pop('_price_alert', None)
                products.append({
                    'rang': i,
                    'produit': str(item.get('produit'))[:200],
                    'domaine': domaine,
                    'note': round(max(0.0, min(10.0, n)), 1),
                    'recommandation': reco_for(n, str(item.get('recommandation') or '')),
                    'synthese': str(item.get('synthese') or '')[:360],
                    'commentaire_analyste': str(item.get('synthese') or '')[:500],
                    'prix_alibaba_usd': '',
                    'prix_alibaba_usd_min': None,
                    'prix_alibaba_usd_max': None,
                    'prix_aliexpress_usd': '',
                    'prix_amazon_usd': '',
                    'show_alibaba': False,
                    'show_aliexpress': False,
                    'show_amazon': False,
                    'sources_prix': [],
                    **price_fields,
                })

        # Top 10 + re-tri par note
        products.sort(key=lambda x: x.get('note') or 0, reverse=True)
        products = products[:TOP_PRODUCTS_IMPORT]
        for i, row in enumerate(products, start=1):
            row['rang'] = i
            row['recommandation'] = reco_for(
                float(row.get('note') or 0), row.get('recommandation') or '',
            )

        # Opportunités = Top 5 uniquement
        if products:
            opportunities.sort(key=lambda x: x.get('note') or 0, reverse=True)
            if len(opportunities) < min(TOP_OPPORTUNITIES, len(products)):
                opportunities = []
                for p in products[:TOP_OPPORTUNITIES]:
                    opportunities.append({
                        'rang': p['rang'],
                        'titre': f"{p['produit'][:80]}",
                        'domaine': p.get('domaine') or '',
                        'produit': p.get('produit') or '',
                        'note': p.get('note') or 0,
                        'recommandation': p.get('recommandation') or '',
                        'commentaire': cls._default_opportunity_comment(p),
                        'action': 'Importer / tester stock / surveiller',
                    })
            else:
                opportunities = opportunities[:TOP_OPPORTUNITIES]
                for i, row in enumerate(opportunities, start=1):
                    row['rang'] = i
                    row['commentaire'] = cls._sanitize_public_comment(
                        row.get('commentaire') or '',
                    )[:450]

        ranking = cls._adjust_domain_notes(ranking, products)

        comparisons = []
        for row in data.get('comparaison') or []:
            if isinstance(row, dict) and (row.get('domaine_a') or row.get('verdict')):
                comparisons.append({
                    'domaine_a': str(row.get('domaine_a') or '')[:120],
                    'domaine_b': str(row.get('domaine_b') or '')[:120],
                    'verdict': cls._sanitize_public_comment(row.get('verdict') or '')[:320],
                    'critere': str(row.get('critere') or '')[:60],
                    'commentaire': cls._sanitize_public_comment(
                        row.get('commentaire') or row.get('verdict') or '',
                    )[:400],
                })

        resume = cls._sanitize_public_comment(data.get('resume') or '')[:700]
        commentaire_global = cls._sanitize_public_comment(
            data.get('commentaire_global') or resume,
        )[:700]
        if not resume and ranking:
            top_d = ranking[0]
            top_p = products[0] if products else None
            extra = ''
            if top_p and top_p.get('prix_sn_xof'):
                extra = (
                    f' Produit phare : {top_p["produit"]} '
                    f'(SN {top_p["prix_sn_xof"]}'
                    + (f', marge {top_p["marge_estimee_xof"]}' if top_p.get('marge_estimee_xof') else '')
                    + ').'
                )
            resume = (
                f'Domaine prioritaire : {top_d["domaine"]} '
                f'({top_d["note_globale"]}/10 — {top_d["recommandation"]}).'
                f'{extra}'
            )
            commentaire_global = resume

        alertes = [str(a)[:220] for a in (data.get('alertes') or [])[:8]]
        for a in price_alerts[:4]:
            if a not in alertes:
                alertes.append(a[:220])

        return {
            'resume': resume,
            'commentaire_global': commentaire_global,
            'methodologie': cls._sanitize_public_comment(data.get('methodologie') or (
                'Contexte Trade Intelligence + vérification web marché SN (min/max) '
                'et sourcing international confirmé avant chiffrage.'
            ))[:400],
            'classement_domaines': ranking[:12],
            'comparaison': comparisons[:12],
            'meilleures_opportunites': opportunities[:TOP_OPPORTUNITIES],
            'produits_import': products[:TOP_PRODUCTS_IMPORT],
            'alertes': [cls._sanitize_public_comment(a)[:220] for a in alertes[:10]],
            'domains_count': len(snapshots),
            'generated_at': timezone.now().isoformat(),
        }

    _SITE_NAME_RE = re.compile(
        r'\b('
        r'jumia(?:\.sn)?|jiji(?:\.sn)?|promo\.sn|coinafrique|expat[- ]?dakar|'
        r'jemba|dakarcenter|occasiondakar|taftaf|'
        r'alibaba|aliexpress|amazon|made[- ]?in[- ]?china|1688|dhgate|'
        r'global\s*sources|yiwugo|hktdc|tiktok|instagram|facebook|facebook\s*marketplace'
        r')\b',
        re.I,
    )

    @classmethod
    def _sanitize_public_comment(cls, text) -> str:
        """Retire les noms de sites ; garde un ton marché local / sourcing générique."""
        raw = str(text or '').strip()
        if not raw:
            return ''
        cleaned = cls._SITE_NAME_RE.sub('marché local', raw)
        cleaned = re.sub(
            r'\b(signaux|sur|via|chez|sur le|sur la)\s+marché local(?:\s*/\s*marché local)?',
            'sur le marché local',
            cleaned,
            flags=re.I,
        )
        cleaned = re.sub(r'marché local\s*/\s*marché local', 'marché local', cleaned, flags=re.I)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(' -·,;')
        return cleaned

    @classmethod
    def _default_domain_comment(cls, domaine: str, note: float, rang: int) -> str:
        name = (domaine or 'Ce domaine').strip()[:80]
        if note >= 7.5:
            return (
                f'«{name}» se démarque ({note}/10) : demande locale solide et '
                f'rotation crédible — un bon candidat pour engager du stock ciblé.'
            )
        if note >= 5.0:
            return (
                f'«{name}» reste moyen ({note}/10) : l’opportunité existe mais '
                f'marge ou concurrence freinent. Testez un petit volume avant d’élargir.'
            )
        return (
            f'«{name}» ({note}/10) : signaux trop faibles pour immobiliser du capital. '
            f'Mieux vaut surveiller avant d’importer.'
        )

    @classmethod
    def _default_opportunity_comment(cls, product: dict) -> str:
        name = str(product.get('produit') or 'Ce produit')[:80]
        sn = product.get('prix_sn_xof') or ''
        marge = product.get('marge_estimee_xof') or ''
        note = product.get('note')
        parts = [f'«{name}» offre une fenêtre d’import crédible']
        if note is not None:
            parts[0] += f' ({note}/10)'
        parts[0] += '.'
        if sn:
            parts.append(f'Prix marché local {sn}.')
        if marge and 'n/d' not in str(marge).lower():
            parts.append(f'Marge estimée {marge}.')
        else:
            parts.append('Validez le coût landed avant d’engager le stock.')
        return cls._sanitize_public_comment(' '.join(parts))[:450]

    @classmethod
    def polish_result_for_display(cls, result: dict) -> dict:
        """Nettoie prix USD + commentaires (rapports déjà stockés inclus)."""
        if not isinstance(result, dict):
            return {}

        for key in ('resume', 'commentaire_global', 'methodologie'):
            if result.get(key):
                result[key] = cls._sanitize_public_comment(result.get(key))[:700]

        for row in result.get('classement_domaines') or []:
            if not isinstance(row, dict):
                continue
            for k in ('synthese', 'commentaire_analyste'):
                if row.get(k):
                    row[k] = cls._sanitize_public_comment(row.get(k))[:500]
            for list_key in ('points_forts', 'risques', 'opportunites_cles'):
                items = row.get(list_key)
                if isinstance(items, list):
                    row[list_key] = [
                        cls._sanitize_public_comment(x)[:160] for x in items if x
                    ]

        for row in result.get('meilleures_opportunites') or []:
            if isinstance(row, dict) and row.get('commentaire'):
                row['commentaire'] = cls._sanitize_public_comment(row.get('commentaire'))[:450]

        for row in result.get('comparaison') or []:
            if not isinstance(row, dict):
                continue
            for k in ('verdict', 'commentaire'):
                if row.get(k):
                    row[k] = cls._sanitize_public_comment(row.get(k))[:400]

        # Top 5 opportunités à l’affichage (rapports anciens)
        opps = result.get('meilleures_opportunites')
        if isinstance(opps, list):
            result['meilleures_opportunites'] = opps[:TOP_OPPORTUNITIES]
            for i, row in enumerate(result['meilleures_opportunites'], start=1):
                if isinstance(row, dict):
                    row['rang'] = i

        products = result.get('produits_import')
        if not isinstance(products, list):
            return result
        for row in products:
            if not isinstance(row, dict):
                continue
            row.pop('commentaire_prix', None)
            row.pop('sources_prix', None)
            row.pop('prix_made_in_china_usd', None)

            alibaba_raw = str(row.get('prix_alibaba_usd') or '')
            usd_min = cls._parse_number(row.get('prix_alibaba_usd_min'))
            usd_max = cls._parse_number(row.get('prix_alibaba_usd_max'))
            alibaba = cls._resolve_platform_price(alibaba_raw)
            if not alibaba and usd_min is not None and not alibaba_raw.strip():
                alibaba = cls._format_usd_range(usd_min, usd_max)
            # Anciens rapports : « Non pertinent » / inventé → masquer
            if cls._is_blank_price_label(alibaba_raw) and alibaba_raw.strip():
                alibaba = ''
            aliexpress = cls._resolve_platform_price(row.get('prix_aliexpress_usd'))
            amazon = cls._resolve_platform_price(row.get('prix_amazon_usd'))

            row['prix_alibaba_usd'] = alibaba[:80]
            row['prix_aliexpress_usd'] = aliexpress[:80]
            row['prix_amazon_usd'] = amazon[:80]
            row['show_alibaba'] = bool(alibaba)
            row['show_aliexpress'] = bool(aliexpress)
            row['show_amazon'] = bool(amazon)
            if not alibaba:
                row['prix_alibaba_usd_min'] = None
                row['prix_alibaba_usd_max'] = None
        return result

    @classmethod
    def _selected_slugs_from_analysis(cls, analysis) -> list[str] | None:
        """Lit le filtre domaines stocké avant l’écrasement par les snapshots complets."""
        raw = getattr(analysis, 'domains_snapshot', None) or []
        if not raw:
            return None
        if isinstance(raw, list) and raw and all(isinstance(x, str) for x in raw):
            return [x.strip() for x in raw if x.strip()]
        if isinstance(raw, list) and raw and all(isinstance(x, dict) for x in raw):
            # Placeholder UI : [{'domain_slug': '...'}] sans sessions
            if all('sessions' not in x for x in raw):
                slugs = [
                    str(x.get('domain_slug') or '').strip()
                    for x in raw
                    if x.get('domain_slug')
                ]
                return slugs or None
        return None

    @classmethod
    def run_analysis(
        cls,
        *,
        progress: Any = None,
        analysis_id: int | None = None,
        should_cancel=None,
        domain_slugs: list[str] | None = None,
    ) -> dict:
        """Pipeline : snapshots domaines → prix BDD → web → DeepSeek → persist."""
        from intelligence.models import ImportMasterDomainAnalysis

        def report(pct: int, msg: str) -> None:
            if should_cancel and should_cancel():
                raise RuntimeError('Analyse annulée par l’utilisateur.')
            if analysis_id:
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

        selected = list(domain_slugs or [])
        if not selected and analysis:
            selected = cls._selected_slugs_from_analysis(analysis) or []

        report(5, 'Chargement de la dernière analyse TI (Top 5) par domaine…')
        snapshots = cls.collect_domain_snapshots(
            domain_slugs=selected or None,
            per_session_top=cls.TOP_PRODUCTS_PER_SESSION,
            sessions_per_domain=cls.SESSIONS_PER_DOMAIN,
        )
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

        report(12, 'Préparation contexte TI (prix via recherche web uniquement)…')

        report(
            18,
            f'{len(snapshots)} domaine(s) · {sessions_total} analyse(s) — '
            f'verification web prix SN & sourcing…',
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

        report(55, 'Analyse IA (thinking) — vérification web, Top 10 et marges…')
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
