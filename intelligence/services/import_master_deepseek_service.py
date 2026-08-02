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
WEB_CONTEXT_MAX_CHARS = 16000
DOMAINS_JSON_MAX_CHARS = 16000
USER_WEB_CONTEXT_MAX_CHARS = 12000

COMPARE_SYSTEM = """Tu es un analyste import senior pour YAYEMATY MARKET (Sénégal, XOF).
Tu produis UNIQUEMENT du JSON valide, sans markdown.
Mission :
1) Comparer les résultats d'analyse Trade Intelligence DÉJÀ PASSÉS (domaines + Top produits).
2) Identifier les meilleures opportunités d'importation tous domaines confondus (Top 10 produits).
3) Pour CHAQUE produit Top 10 : fourchette MARCHÉ SN (prix_sn_min_xof / prix_sn_max_xof)
   via sites SN prioritaires (Jumia.sn, Jiji.sn, promo.sn, sn.coinafrique.com, expat-dakar.com,
   Facebook) ET tout autre site web pertinent pour le marché sénégalais (web ouvert).
4) Estimer prix sourcing Alibaba / AliExpress / Amazon / Made-in-China / 1688 / DHgate /
   Global Sources / Yiwugo / HKTDC (USD) + coût landed XOF.
   Ces plateformes d’import sont réservées à Import Master (pas Trade Intelligence).
5) Calculer marges cohérentes : marge ≈ prix_SN − prix_landed_xof (pas de marge inventée).
6) Classer domaines et produits en tenant compte de la fiabilité des prix et des marges réalistes.

Règles prix ABSOLUES :
- prix_sn_min_xof ≤ prix_sn_max_xof (entiers XOF).
- Prioriser prix_locaux_bdd si présents, sinon web SN ouvert, sinon estimation prudente.
- marge_pct entre 5 et 70 si données crédibles ; sinon baisser la note et alerter.
- Pas de fourchettes fantaisistes (ex. min 1000 / max 500000 pour un même SKU).

Recommandations EXACTES :
« Bon, je vous le recommande » | « Peut faire l'affaire mais moyen » | « À éviter »
Commentaires : 2–4 phrases max, chiffres (min–max SN, marge %) obligatoires.
"""

COMPARE_USER = """Analyse comparative d'importation YAYEMATY.

=== ANALYSES TRADE INTELLIGENCE + PRIX LOCAUX BDD (par domaine) ===
{domains_json}

=== RECHERCHE WEB (marché SN ouvert min/max + sourcing Alibaba/AliExpress/Amazon/Made-in-China) ===
{web_context}

Consignes :
- Chaque domaine inclut jusqu'à 2 analyses récentes : tendances notes / produits.
- Compare les domaines avec critères demande, marge réelle, fiabilité prix SN, concurrence.
- EXACTEMENT 10 produits dans produits_import (Top 10 tous domaines), triés par note décroissante.
- Marché SN : sites prioritaires + TOUT autre site web utile pour prix Sénégal (pas limité à la liste).
- Sourcing : Alibaba, AliExpress, Amazon ET Made-in-China.com (USD) + landed XOF.
- Pour chaque produit : prix_sn_min_xof et prix_sn_max_xof OBLIGATOIRES (entiers),
  prix sourcing USD (dont made-in-china si pertinent), prix_landed_xof, marge_min/max/pct.
- resume et commentaire_global DOIVENT citer fourchettes SN et marges % des priorités.
- comparaison domaines : s'appuyer sur fourchettes structurées, pas du marketing vague.
- meilleures_opportunites (≤10) alignées sur les mêmes Top produits.

Réponds avec ce JSON exact :
{{
  "resume": "Synthèse 3–5 phrases avec fourchettes SN et marges % des priorités.",
  "commentaire_global": "Commentaire analyste (marché SN, sourcing, timing).",
  "methodologie": "TI + web SN ouvert (prioritaires + autres sites) + sourcing Alibaba/AliExpress/Amazon/Made-in-China + BDD.",
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
      "prix_alibaba_usd": "18–22 USD",
      "prix_alibaba_usd_min": 18,
      "prix_alibaba_usd_max": 22,
      "prix_aliexpress_usd": "...",
      "prix_amazon_usd": "...",
      "prix_made_in_china_usd": "ex. 16–20 USD",
      "prix_potentiel_achat_xof": "15 000 XOF",
      "prix_landed_xof": 15000,
      "marge_min_xof": 7000,
      "marge_max_xof": 10000,
      "marge_pct": 32,
      "marge_estimee_xof": "7 000 – 10 000 XOF (~32%)",
      "fiabilite_prix": "web|bdd|mixte|estime",
      "sources_prix": ["jumia.sn", "jiji.sn", "alibaba.com", "made-in-china.com"]
    }}
  ],
  "alertes": ["Risque ou point de vigilance…"]
}}
"""


class ImportMasterDeepSeekService:
    """Compare domaines déjà analysés + opportunités / prix web via DeepSeek."""

    SESSIONS_PER_DOMAIN = 2
    TOP_PRODUCTS_PER_SESSION = 8
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
        'prix les plus bas marché Sénégal : Jumia Jiji Promo CoinAfrique Expat-Dakar '
        'Jemba DakarCenter OccasionDakar TafTaf Facebook Instagram ET tout autre '
        'site web SN (prix min XOF par modèle)',
        'prix les plus hauts / premium marché Sénégal : mêmes priorités + web ouvert '
        'autres marketplaces / annonces SN (prix max XOF par modèle)',
        'prix gros Alibaba Made-in-China 1688 Global Sources (USD) + coût landed XOF '
        'Sénégal (fret + douane approximatifs) par modèle',
        'prix AliExpress Amazon DHgate Yiwugo HKTDC wholesale vs revente marché SN',
        'marges revendeur Sénégal réalistes (prix SN min–max moins coût landed) '
        'tous domaines confondus — web ouvert autorisé',
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
                f'Cherche prix min et max en XOF sur le marché sénégalais '
                f'(sites prioritaires + web ouvert) et prix sourcing '
                f'Alibaba / AliExpress / Amazon / Made-in-China.com.',
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
        if fiabilite not in ('web', 'bdd', 'mixte', 'estime'):
            sources = ' '.join(str(s) for s in (row.get('sources_prix') or [])).lower()
            if 'jumia' in sources or 'jiji' in sources or 'bdd' in sources:
                fiabilite = 'mixte' if ('alibaba' in sources or 'aliexpress' in sources) else 'bdd'
            elif sources:
                fiabilite = 'web'
            else:
                fiabilite = 'estime'

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
                if p.get('fiabilite_prix') in ('bdd', 'mixte', 'web')
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
        domains_json = json.dumps(snapshots, ensure_ascii=False, indent=2)[:DOMAINS_JSON_MAX_CHARS]
        web_max = DeepSeekAnalysisService._char_limit(
            'ANALYSIS_WEB_CONTEXT_MAX_CHARS', USER_WEB_CONTEXT_MAX_CHARS,
        )
        user_content = COMPARE_USER.format(
            domains_json=domains_json,
            web_context=(web_context or 'Aucun contexte web.')[:web_max],
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
            alibaba = str(row.get('prix_alibaba_usd') or '').strip()
            if not alibaba and usd_min is not None:
                if usd_max and usd_max != usd_min:
                    alibaba = f'{usd_min}–{usd_max} USD'
                else:
                    alibaba = f'{usd_min} USD'
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
                'prix_alibaba_usd': alibaba[:80],
                'prix_alibaba_usd_min': usd_min,
                'prix_alibaba_usd_max': usd_max,
                'prix_aliexpress_usd': str(row.get('prix_aliexpress_usd') or '')[:80],
                'prix_amazon_usd': str(row.get('prix_amazon_usd') or '')[:80],
                'prix_made_in_china_usd': str(row.get('prix_made_in_china_usd') or '')[:80],
                'sources_prix': [
                    str(s) for s in (row.get('sources_prix') or []) if s
                ][:8],
                **price_fields,
            })

        # Fallback produits depuis snapshots (+ prix BDD si déjà enrichis)
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
                local = item.get('prix_locaux_bdd') or {}
                seed = {
                    'prix_sn_min_xof': local.get('min_xof'),
                    'prix_sn_max_xof': local.get('max_xof'),
                    'prix_sn_median_xof': local.get('avg_xof'),
                    'fiabilite_prix': 'bdd' if local else 'estime',
                    'sources_prix': local.get('sources') or [],
                }
                price_fields = cls._normalize_product_prices(seed)
                price_fields.pop('_price_alert', None)
                products.append({
                    'rang': i,
                    'produit': str(item.get('produit'))[:200],
                    'domaine': domaine,
                    'note': round(max(0.0, min(10.0, n)), 1),
                    'recommandation': reco_for(n, str(item.get('recommandation') or '')),
                    'synthese': str(item.get('synthese') or '')[:360],
                    'commentaire_analyste': str(item.get('synthese') or '')[:500],
                    'commentaire_prix': (
                        'Prix SN issus de la BDD locale — relancez l’analyse pour '
                        'compléter sourcing web et marges landed.'
                        if local else
                        'Prix sourcing web non disponibles — relancez l’analyse comparative.'
                    ),
                    'prix_alibaba_usd': '',
                    'prix_alibaba_usd_min': None,
                    'prix_alibaba_usd_max': None,
                    'prix_aliexpress_usd': '',
                    'prix_amazon_usd': '',
                    'prix_made_in_china_usd': '',
                    'sources_prix': list(seed.get('sources_prix') or [])[:8],
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

        # Opportunités alignées sur Top produits si vides ou incohérentes
        if products:
            opportunities.sort(key=lambda x: x.get('note') or 0, reverse=True)
            if len(opportunities) < min(5, len(products)):
                opportunities = []
                for p in products[:TOP_PRODUCTS_IMPORT]:
                    sn = p.get('prix_sn_xof') or 'prix SN n/d'
                    marge = p.get('marge_estimee_xof') or 'marge n/d'
                    opportunities.append({
                        'rang': p['rang'],
                        'titre': f"{p['produit'][:80]}",
                        'domaine': p.get('domaine') or '',
                        'produit': p.get('produit') or '',
                        'note': p.get('note') or 0,
                        'recommandation': p.get('recommandation') or '',
                        'commentaire': (
                            f"Marché SN {sn} · marge {marge}. "
                            f"{(p.get('synthese') or '')[:200]}"
                        )[:450],
                        'action': 'Importer / tester stock / surveiller',
                    })
            else:
                opportunities = opportunities[:TOP_PRODUCTS_IMPORT]
                for i, row in enumerate(opportunities, start=1):
                    row['rang'] = i

        ranking = cls._adjust_domain_notes(ranking, products)

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
            'methodologie': str(data.get('methodologie') or (
                'Comparaison des 2 dernières sessions Trade Intelligence par domaine '
                '(90 jours max), enrichie par recherches web marché SN ouvertes (min/max) + '
                'sourcing Alibaba / AliExpress / Amazon / Made-in-China.com et BDD Jumia/Jiji.'
            ))[:400],
            'classement_domaines': ranking[:12],
            'comparaison': comparisons[:12],
            'meilleures_opportunites': opportunities[:TOP_PRODUCTS_IMPORT],
            'produits_import': products[:TOP_PRODUCTS_IMPORT],
            'alertes': alertes[:10],
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

        report(12, 'Croisement prix locaux Jumia / Jiji en base…')
        try:
            snapshots = cls.enrich_snapshots_with_local_prices(snapshots)
        except Exception as exc:
            logger.warning('Enrichissement prix BDD Import Master : %s', exc)

        report(
            20,
            f'{len(snapshots)} domaine(s) · {sessions_total} analyse(s) — '
            f'recherche web marché SN & sourcing…',
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

        report(55, 'Analyse IA — comparaison, Top 10 et prix marché SN…')
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
