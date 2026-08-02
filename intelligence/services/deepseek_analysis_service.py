"""
Analyse marché via DeepSeek (deepseek-v4-flash) — recherche web + JSON Top 15.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

LIST_KEYS = ('top_investissement', 'plus_recherche', 'plus_aime', 'vitesse_vente')
TOP_N = 15

SYSTEM_PROMPT = """Tu es un analyste marché e-commerce au Sénégal (XOF, Jumia.sn, Jiji.sn, TikTok, Google Trends SN).
Tu produis UNIQUEMENT du JSON valide, sans markdown.
Objectif : aider YAYEMATY à décider DANS QUELS MODÈLES / VARIANTES investir.

RÈGLE N°1 — PÉRIMÈTRE DOMAINE (ABSOLUE, NON NÉGOCIABLE) :
- Tu te limites STRICTEMENT au DOMAINE fourni. Aucun produit hors domaine.
- Exemples : domaine « Téléphone et tablette » → uniquement téléphones, tablettes, accessoires mobiles.
  INTERDIT : agriculture, mode, électroménager, etc.
  Domaine « Agriculture & Forêt » → uniquement agrib/forêt. INTERDIT : smartphones, mode, etc.
- Si le mot-clé est hors domaine, IGNORE-le pour le classement et reste 100 % dans le domaine
  (ou ne garde que l'interprétation du mot-clé qui appartient au domaine).
- Ignore toute donnée scrapée / web hors domaine.

Règles produits :
- Mot-clé DANS le domaine (ex. « iphone » dans Téléphonie) → Top 15 de MODÈLES concrets
  (iPhone 12, iPhone 13, iPhone 14 Pro… — pas le générique seul).
- Sans mot-clé → Top 15 des meilleurs modèles/produits DU DOMAINE au Sénégal.
- Chaque ligne = modèle achetable/revendable + note d'investissement.
- Notes 0.0–10.0 (basses OK). EXACTEMENT 15 produits par onglet.
- Sources : google_trends, jumia, jiji, tiktok, deepseek_web

RECOMMANDATION (libellé EXACT selon la note — 1 seule phrase courte) :
- Note ≥ 7.5 → « Bon, je vous le recommande »
- Note 5.0 à 7.4 → « Peut faire l'affaire mais moyen »
- Note < 5.0 → « À éviter »
Aucun autre libellé. Le texte DOIT coller à la note.

ANALYSE DU MARCHÉ / champ « synthese » (OBLIGATOIRE pour les 15 rangs, y compris 11–15) :
- Exactement 2 phrases courtes, motivantes et convaincantes (max ~280 caractères).
- Expliquer POURQUOI cette note (demande SN, prix/marge si connus, risque).
- Ton décisionnel : pourquoi investir, tester, ou éviter.
- Interdit : texte vide, « … », ou phrases sans raison. Économise les tokens : pas de roman.
"""

USER_PROMPT_TEMPLATE = """DOMAINE OBLIGATOIRE (ne jamais sortir de ce périmètre) : {domain_label}
Mot-clé (optionnel, UNIQUEMENT s'il appartient au domaine) : {category_label}
Requête marché : {search_query}

CONTRAINTES :
1) TOUS les produits listés doivent appartenir au domaine « {domain_label} ». Zéro exception.
2) Classe EXACTEMENT 15 MODÈLES/VARIANTES pour investir au Sénégal.
3) Si mot-clé pertinent pour le domaine (ex. iphone dans téléphonie) : un modèle précis par ligne
   (iPhone 11, 12, 13, 14…). Si mot-clé hors domaine : ignore-le et reste dans « {domain_label} ».
4) Sans mot-clé utile : Top 15 du domaine « {domain_label} » uniquement.
5) recommandation = EXACTEMENT un de :
   « Bon, je vous le recommande » | « Peut faire l'affaire mais moyen » | « À éviter »
6) synthese = 2 phrases pour CHAQUE rang 1 à 15 (y compris 11–15), courte, convaincante,
   justifiant la note. Pas de champ vide.

=== DONNÉES COLLECTÉES (scraping) — filtre mental : ignorer hors domaine ===
{payload_json}

=== CONTEXTE WEB — filtre mental : ignorer hors domaine ===
{web_context}

Réponds avec ce JSON exact. Chaque liste DOIT avoir EXACTEMENT 15 objets (rang 1..15),
TOUS dans le domaine « {domain_label} » :
{{
  "domaine": "{domain_label}",
  "categorie": "{category_label}",
  "top_investissement": [
    {{"rang": 1, "produit": "Modèle précis", "note": 9.5, "recommandation": "Bon, je vous le recommande", "synthese": "Demande forte au Sénégal et bonne rotation Jumia/Jiji : la note 9.5 reflète une marge nette attractive. Priorisez le stock.", "sources": ["jumia", "google_trends"]}},
    {{"rang": 2, "produit": "...", "note": 8.8, "recommandation": "Bon, je vous le recommande", "synthese": "...", "sources": ["jiji"]}},
    {{"rang": 3, "produit": "...", "note": 8.2, "recommandation": "Bon, je vous le recommande", "synthese": "...", "sources": ["tiktok"]}},
    {{"rang": 4, "produit": "...", "note": 7.6, "recommandation": "Bon, je vous le recommande", "synthese": "...", "sources": ["google_trends"]}},
    {{"rang": 5, "produit": "...", "note": 7.0, "recommandation": "Peut faire l'affaire mais moyen", "synthese": "...", "sources": ["jumia"]}},
    {{"rang": 6, "produit": "...", "note": 6.5, "recommandation": "Peut faire l'affaire mais moyen", "synthese": "...", "sources": ["jiji"]}},
    {{"rang": 7, "produit": "...", "note": 6.0, "recommandation": "Peut faire l'affaire mais moyen", "synthese": "...", "sources": ["tiktok"]}},
    {{"rang": 8, "produit": "...", "note": 5.5, "recommandation": "Peut faire l'affaire mais moyen", "synthese": "...", "sources": ["deepseek_web"]}},
    {{"rang": 9, "produit": "...", "note": 5.0, "recommandation": "Peut faire l'affaire mais moyen", "synthese": "...", "sources": ["jumia"]}},
    {{"rang": 10, "produit": "...", "note": 4.5, "recommandation": "À éviter", "synthese": "...", "sources": ["jiji"]}},
    {{"rang": 11, "produit": "...", "note": 4.0, "recommandation": "À éviter", "synthese": "Signaux faibles au Sénégal : volume et marge insuffisants pour la note 4.0. Mieux vaut ne pas immobiliser du capital.", "sources": ["google_trends"]}},
    {{"rang": 12, "produit": "...", "note": 3.5, "recommandation": "À éviter", "synthese": "Peu de traction Jumia/Jiji/TikTok : la note 3.5 sanctionne un risque de stock mort. Écartez pour l’instant.", "sources": ["tiktok"]}},
    {{"rang": 13, "produit": "...", "note": 3.0, "recommandation": "À éviter", "synthese": "Demande incertaine et concurrence défavorable expliquent la note 3.0. Pas d’achat stock recommandé.", "sources": ["deepseek_web"]}},
    {{"rang": 14, "produit": "...", "note": 2.5, "recommandation": "À éviter", "synthese": "Très faible intérêt marché SN : note 2.5 = opportunité trop risquée. Concentrez-vous sur le haut du Top.", "sources": ["jumia"]}},
    {{"rang": 15, "produit": "...", "note": 2.0, "recommandation": "À éviter", "synthese": "Dernier du classement faute de preuves de vente : note 2.0. Évitez tout engagement stock.", "sources": ["jiji"]}}
  ],
  "plus_recherche": [ /* EXACTEMENT 15 + synthese 2 phrases + reco exacte */ ],
  "plus_aime": [ /* EXACTEMENT 15 + synthese 2 phrases + reco exacte */ ],
  "vitesse_vente": [ /* EXACTEMENT 15 + synthese 2 phrases + reco exacte */ ],
  "highlights": {{
    "top_pick": {{"produit": "...", "note": 9.5, "recommandation": "Bon, je vous le recommande", "synthese": "..."}},
    "forte_croissance": {{"produit": "...", "note": 8.9, "recommandation": "Bon, je vous le recommande", "synthese": "...", "source_label": "TikTok Vues (SN)"}},
    "meilleure_marge": {{"produit": "...", "note": 9.2, "recommandation": "Bon, je vous le recommande", "synthese": "..."}}
  }}
}}
"""

# Libellés reco fixes (1 par palier de note).
RECO_BON = 'Bon, je vous le recommande'
RECO_MOYEN = "Peut faire l'affaire mais moyen"
RECO_FAIBLE = 'À éviter'
SYNTH_MAX_LEN = 320


class DeepSeekAnalysisService:
    """Appels DeepSeek Chat + recherche web pour Trade Intelligence."""

    @classmethod
    def _config(cls) -> dict:
        return getattr(settings, 'DEEPSEEK', {})

    @classmethod
    def _char_limit(cls, key: str, default: int = 12000) -> int:
        return max(500, int(cls._config().get(key) or default))

    @classmethod
    def get_web_max_tours(cls, *, cfg: dict | None = None) -> int:
        """
        Nombre de tours veille web DeepSeek — fixé par ``DEEPSEEK_WEB_MAX_TOURS`` (.env).
        """
        cfg = cfg or cls._config()
        raw = cfg.get('WEB_MAX_TOURS')
        if raw is None or raw == '':
            tours = 3
        else:
            try:
                tours = int(raw)
            except (TypeError, ValueError):
                tours = 3
        return max(1, tours)

    @classmethod
    def compute_web_max_tours(cls, duration_minutes: int = 0, *, cfg: dict | None = None) -> int:
        """Alias rétrocompat — la durée session n'influence plus le nombre de tours."""
        return cls.get_web_max_tours(cfg=cfg)

    @classmethod
    def is_enabled(cls) -> bool:
        cfg = cls._config()
        return bool(cfg.get('ENABLED') and cfg.get('API_KEY'))

    @classmethod
    def normalize_web_domain(cls, raw: str) -> str:
        """Normalise un domaine pour allowed_domains (sans schéma ni www.)."""
        text = str(raw or '').strip().lower()
        if not text:
            return ''
        text = re.sub(r'^https?://', '', text)
        text = text.split('/')[0].split('?')[0].strip('.')
        if text.startswith('www.'):
            text = text[4:]
        # Domaines uniquement (lettres, chiffres, points, tirets)
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}', text):
            return ''
        return text

    @classmethod
    def parse_web_domains(cls, values: Any) -> list[str]:
        """Liste unique de domaines valides depuis list/tuple/CSV."""
        if values is None:
            return []
        if isinstance(values, str):
            parts = [p.strip() for p in values.split(',')]
        elif isinstance(values, (list, tuple, set)):
            parts = [str(p).strip() for p in values]
        else:
            return []
        seen: set[str] = set()
        out: list[str] = []
        for part in parts:
            domain = cls.normalize_web_domain(part)
            if domain and domain not in seen:
                seen.add(domain)
                out.append(domain)
        return out

    @classmethod
    def build_web_search_tool(cls, cfg: dict | None = None) -> dict:
        """
        Outil web_search DeepSeek (API Anthropic).

        - ``WEB_OPEN_SEARCH=True`` (défaut) : pas de ``allowed_domains`` → web ouvert ;
          les sites ``WEB_ALLOWED_DOMAINS`` sont prioritaires via le prompt.
        - ``WEB_OPEN_SEARCH=False`` : restriction API ``allowed_domains`` (legacy strict).
        """
        cfg = cfg or cls._config()
        tool: dict[str, Any] = {
            'type': 'web_search_20250305',
            'name': 'web_search',
        }
        max_uses = int(cfg.get('WEB_MAX_USES') or 0)
        if max_uses > 0:
            tool['max_uses'] = min(max_uses, 20)

        open_search = bool(cfg.get('WEB_OPEN_SEARCH', True))
        preferred = cls.parse_web_domains(cfg.get('WEB_ALLOWED_DOMAINS') or [])
        blocked = cls.parse_web_domains(cfg.get('WEB_BLOCKED_DOMAINS') or [])

        if not open_search and preferred:
            tool['allowed_domains'] = preferred
        elif not open_search and blocked:
            tool['blocked_domains'] = blocked
        elif open_search and blocked:
            tool['blocked_domains'] = blocked

        country = str(cfg.get('WEB_COUNTRY') or 'SN').strip().upper()[:2]
        city = str(cfg.get('WEB_CITY') or 'Dakar').strip()
        timezone = str(cfg.get('WEB_TIMEZONE') or 'Africa/Dakar').strip()
        if country:
            location: dict[str, str] = {
                'type': 'approximate',
                'country': country,
                'timezone': timezone or 'Africa/Dakar',
            }
            if city:
                location['city'] = city
            tool['user_location'] = location
        return tool

    @classmethod
    def web_watch_meta(cls, cfg: dict | None = None) -> dict:
        """Métadonnées veille web pour UI / résultat d'analyse."""
        cfg = cfg or cls._config()
        tool = cls.build_web_search_tool(cfg)
        preferred = cls.parse_web_domains(cfg.get('WEB_ALLOWED_DOMAINS') or [])
        open_search = bool(cfg.get('WEB_OPEN_SEARCH', True))
        return {
            'max_uses': int(tool.get('max_uses') or 0),
            'open_search': open_search,
            'preferred_domains': preferred,
            'allowed_domains': list(tool.get('allowed_domains') or preferred),
            'blocked_domains': list(tool.get('blocked_domains') or []),
            'country': (tool.get('user_location') or {}).get('country', ''),
            'city': (tool.get('user_location') or {}).get('city', ''),
        }

    @classmethod
    def _web_sites_prompt_line(
        cls,
        cfg: dict | None = None,
        *,
        extra_note: str = '',
    ) -> str:
        """Consigne sites pour fetch_web_context (prioritaires ± web ouvert)."""
        cfg = cfg or cls._config()
        preferred = cls.parse_web_domains(cfg.get('WEB_ALLOWED_DOMAINS') or [])
        open_search = bool(cfg.get('WEB_OPEN_SEARCH', True))
        note = (extra_note or '').strip()
        sourcing = {
            'alibaba.com', 'aliexpress.com', 'amazon.com', 'made-in-china.com',
            '1688.com', 'dhgate.com', 'globalsources.com', 'yiwugo.com', 'hktdc.com',
        }
        uses_sourcing = bool(set(preferred) & sourcing)
        if open_search:
            if preferred:
                line = (
                    f'SITES PRIORITAIRES (consulter en premier) : {", ".join(preferred)}. '
                    'Tu peux aussi élargir la recherche sur tout le web ouvert '
                    'pour des informations complémentaires fiables (presse, forums, '
                    'marketplaces, réseaux sociaux, autres sites marché SN, etc.).'
                )
            else:
                line = (
                    'Recherche web ouverte — parcours libre du web pour informations '
                    'marché Sénégal fiables.'
                )
            if not uses_sourcing:
                line += (
                    ' Ne priorisez pas Alibaba, AliExpress, Amazon ni Made-in-China '
                    '(réservés exclusivement à Import Master).'
                )
            return f'{line} {note}'.strip()
        if preferred:
            line = f'SITES AUTORISÉS (recherche UNIQUEMENT ici) : {", ".join(preferred)}.'
            return f'{line} {note}'.strip()
        return (
            'Sites prioritaires SN : Jumia, Jiji, Promo, CoinAfrique, Expat-Dakar, '
            'Jemba, DakarCenter, OccasionDakar, TafTaf, Facebook, Instagram, TikTok.'
        )

    @classmethod
    def format_web_watch_status(
        cls,
        tour: int,
        *,
        focus: str = '',
        enabled: bool = True,
        error: str = '',
        cfg: dict | None = None,
    ) -> str:
        """
        Libellé progression : « Veille web tour 3 · 5 recherches · jumia.sn+5 ».
        Compact pour barre de statut parallèle (≤120 car.).
        """
        if not enabled:
            return 'Veille web off'
        if error:
            return f'Web erreur: {error}'[:120]

        meta = cls.web_watch_meta(cfg)
        max_uses = meta['max_uses']
        domains = meta.get('preferred_domains') or meta.get('allowed_domains') or []
        open_search = meta.get('open_search', True)
        if open_search:
            if domains:
                sites = f'web ouvert+{len(domains)}'
            else:
                sites = 'web ouvert'
        elif domains:
            if len(domains) <= 2:
                sites = ','.join(domains)
            else:
                sites = f'{domains[0]}+{len(domains) - 1}'
        else:
            sites = 'web ouvert'

        parts = [f'Veille web tour {max(1, int(tour))}']
        if max_uses > 0:
            parts.append(f'{max_uses} recherches')
        parts.append(sites)
        focus_short = (focus or '').strip()[:22]
        if focus_short:
            parts.append(focus_short)
        return ' · '.join(parts)[:120]

    @classmethod
    def _chat_extra_body(cls, cfg: dict) -> dict:
        """
        DeepSeek V4 active le « thinking » par défaut : le JSON peut arriver vide
        dans message.content → JSONDecodeError. Désactivé pour les réponses structurées.
        """
        if cfg.get('THINKING_ENABLED'):
            return {}
        model = str(cfg.get('MODEL', 'deepseek-v4-flash')).lower()
        if 'v4' in model or model in ('deepseek-chat', 'deepseek-reasoner'):
            return {'thinking': {'type': 'disabled'}}
        return {}

    @classmethod
    def _parse_json_response(cls, raw: str) -> dict:
        """Parse le JSON DeepSeek (strip markdown, erreur claire si vide)."""
        text = (raw or '').strip()
        if not text:
            raise ValueError(
                'Réponse DeepSeek vide — vérifiez DEEPSEEK_API_KEY, le modèle '
                'deepseek-v4-flash et le redémarrage Celery.'
            )
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\s*```$', '', text)
        return json.loads(text)

    @classmethod
    def fetch_web_context(
        cls,
        query: str,
        *,
        domain_label: str = '',
        focus_hint: str = '',
        preferred_domains: list[str] | None = None,
        open_search: bool | None = None,
        extra_sites_note: str = '',
    ) -> str:
        """
        Recherche web native DeepSeek — bornée au domaine produit.

        ``preferred_domains`` remplace la liste TI (Import Master passe sa propre liste
        avec Alibaba / AliExpress / Amazon / Made-in-China — hors .env TI).
        """
        cfg = dict(cls._config() or {})
        api_key = cfg.get('API_KEY', '')
        if not api_key:
            return ''

        if preferred_domains is not None:
            # Remplacement total : Import Master ≠ Trade Intelligence
            cfg['WEB_ALLOWED_DOMAINS'] = cls.parse_web_domains(preferred_domains)
        if open_search is not None:
            cfg['WEB_OPEN_SEARCH'] = bool(open_search)

        base = cfg.get('ANTHROPIC_BASE_URL', 'https://api.deepseek.com/anthropic').rstrip('/')
        url = f'{base}/v1/messages'
        timeout = float(cfg.get('TIMEOUT_SECONDS', 120))
        model = cfg.get('MODEL', 'deepseek-v4-flash')
        domain = (domain_label or '').strip() or 'le domaine indiqué'
        focus = (focus_hint or 'meilleurs modèles et opportunités').strip()
        web_tool = cls.build_web_search_tool(cfg)
        sites_line = cls._web_sites_prompt_line(cfg, extra_note=extra_sites_note)
        domain_lock = (
            f'PÉRIMÈTRE ABSOLU : uniquement le domaine produit « {domain} » au Sénégal. '
            f'N’inclus AUCUN produit hors de « {domain} ». '
            f'{sites_line} '
            'Cite modèles précis, prix (XOF ou USD), et l’URL/site source quand possible.'
        )

        payload = {
            'model': model,
            'max_tokens': min(int(cfg.get('MAX_TOKENS', 8192)), 4096),
            'messages': [
                {
                    'role': 'user',
                    'content': (
                        f'{domain_lock}\n'
                        f'Recherche web marché Sénégal pour : {query}.\n'
                        f'Angle de recherche : {focus}.\n'
                        f'Liste au moins 10 MODÈLES/VARIANTES UNIQUEMENT dans « {domain} ». '
                        'Ex. si domaine téléphonie → modèles précis (Samsung A54, iPhone 13…). '
                        'Jamais hors domaine. Résultats concrets : prix, stock/rotation, '
                        'avis, opportunité d’investissement. Une ligne = un modèle + site source.'
                    ),
                },
            ],
            'tools': [web_tool],
        }
        headers = {
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            parts: list[str] = []
            for block in data.get('content') or []:
                if isinstance(block, dict) and block.get('type') == 'text':
                    parts.append(str(block.get('text') or ''))
            text = '\n'.join(parts).strip()
            chunk_max = cls._char_limit('WEB_CHUNK_MAX_CHARS', 12000)
            if text:
                return text[:chunk_max]
            return json.dumps(data)[:chunk_max]
        except Exception as exc:
            logger.warning('DeepSeek web search indisponible : %s', exc)
            return ''

    @classmethod
    def analyze_market(
        cls,
        payload: dict,
        web_context: str,
        *,
        domain_label: str,
        category_label: str,
        search_query: str,
    ) -> dict:
        """Analyse JSON via deepseek-v4-flash — toujours un Top 15 par onglet."""
        cfg = cls._config()
        api_key = cfg.get('API_KEY', '')
        if not api_key:
            raise RuntimeError('DEEPSEEK_API_KEY non configurée.')

        client = OpenAI(api_key=api_key, base_url=cfg.get('BASE_URL', 'https://api.deepseek.com'))
        payload_max = cls._char_limit('ANALYSIS_PAYLOAD_MAX_CHARS', 12000)
        web_max = cls._char_limit('ANALYSIS_WEB_CONTEXT_MAX_CHARS', 12000)
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)[:payload_max]
        user_content = USER_PROMPT_TEMPLATE.format(
            domain_label=domain_label,
            category_label=category_label,
            search_query=search_query,
            payload_json=payload_json,
            web_context=(web_context or 'Aucun contexte web additionnel.')[:web_max],
        )

        response = client.chat.completions.create(
            model=cfg.get('MODEL', 'deepseek-v4-flash'),
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': user_content},
            ],
            response_format={'type': 'json_object'},
            max_tokens=int(cfg.get('MAX_TOKENS', 8192)),
            timeout=float(cfg.get('TIMEOUT_SECONDS', 120)),
            extra_body=cls._chat_extra_body(cfg),
        )
        raw = (response.choices[0].message.content or '').strip()
        parsed = cls._parse_json_response(raw)
        return cls.ensure_top10(
            cls.validate_result(parsed),
            payload=payload,
            domain_label=domain_label,
            category_label=category_label,
        )

    @classmethod
    def validate_result(cls, data: dict) -> dict:
        """Validation minimale du JSON DeepSeek."""
        if not isinstance(data, dict):
            raise ValueError('Réponse DeepSeek invalide (non objet JSON).')

        for key in LIST_KEYS:
            items = data.get(key)
            if items is None:
                data[key] = []
            elif not isinstance(items, list):
                raise ValueError(f'Champ {key} doit être une liste.')
            else:
                data[key] = cls._normalize_items(items[:TOP_N])

        highlights = data.get('highlights') or {}
        if not isinstance(highlights, dict):
            highlights = {}
        data['highlights'] = highlights
        return data

    @classmethod
    def ensure_top10(
        cls,
        data: dict,
        *,
        payload: dict | None = None,
        domain_label: str = '',
        category_label: str = '',
    ) -> dict:
        """Garantit EXACTEMENT 15 produits par onglet (notes basses acceptées)."""
        if not isinstance(data, dict):
            data = {}

        candidates = cls.extract_candidate_names(payload or {})
        for key in LIST_KEYS:
            for item in data.get(key) or []:
                if isinstance(item, dict) and item.get('produit'):
                    name = str(item['produit']).strip()
                    if name and name not in candidates:
                        candidates.append(name)

        for key in LIST_KEYS:
            items = cls._normalize_items(list(data.get(key) or [])[:TOP_N])
            seen = {cls._norm_name(i['produit']) for i in items}
            for name in candidates:
                if len(items) >= TOP_N:
                    break
                key_name = cls._norm_name(name)
                if not key_name or key_name in seen:
                    continue
                seen.add(key_name)
                rank = len(items) + 1
                note = max(1.0, round(5.5 - 0.35 * rank, 1))
                items.append(cls._mk_item(
                    rank,
                    name,
                    note=note,
                    recommandation=cls._recommendation_for_note(note),
                    synthese=cls._default_synthese(name, note, rank),
                    sources=['jumia', 'jiji', 'google_trends'],
                ))

            # Placeholders toujours ancrés au domaine (jamais hors périmètre)
            pad_base = (domain_label or category_label or 'Opportunité marché').strip()
            while len(items) < TOP_N:
                rank = len(items) + 1
                note = max(1.0, round(4.0 - 0.25 * (rank - 1), 1))
                pad_name = f'{pad_base} — opportunité #{rank}'
                items.append(cls._mk_item(
                    rank,
                    pad_name,
                    note=note,
                    recommandation=cls._recommendation_for_note(note),
                    synthese=cls._default_synthese(pad_name, note, rank),
                    sources=['deepseek_web'],
                ))

            for i, item in enumerate(items, start=1):
                item['rang'] = i
                item['recommandation'] = cls._recommendation_for_note(item['note'])
                synth = (item.get('synthese') or '').strip()
                if not synth or synth in ('.', '...', '…'):
                    item['synthese'] = cls._default_synthese(
                        item.get('produit') or 'Produit', item['note'], i,
                    )
            data[key] = items[:TOP_N]

        highlights = data.get('highlights') if isinstance(data.get('highlights'), dict) else {}
        top = data.get('top_investissement') or []
        if top:
            highlights.setdefault('top_pick', {
                'produit': top[0]['produit'],
                'note': top[0]['note'],
                'recommandation': top[0]['recommandation'],
                'synthese': top[0]['synthese'],
            })
            if len(top) > 1:
                highlights.setdefault('forte_croissance', {
                    'produit': top[1]['produit'],
                    'note': top[1]['note'],
                    'recommandation': top[1]['recommandation'],
                    'synthese': top[1]['synthese'],
                    'source_label': 'TikTok / Google SN',
                })
            if len(top) > 2:
                highlights.setdefault('meilleure_marge', {
                    'produit': top[2]['produit'],
                    'note': top[2]['note'],
                    'recommandation': top[2]['recommandation'],
                    'synthese': top[2]['synthese'],
                })
        data['highlights'] = highlights
        return data

    @classmethod
    def extract_candidate_names(cls, payload: dict) -> list[str]:
        """Noms produits uniques issus du payload de collecte."""
        names: list[str] = []
        seen: set[str] = set()

        def add(raw: Any) -> None:
            text = str(raw or '').strip()
            if not text:
                return
            key = cls._norm_name(text)
            if not key or key in seen:
                return
            seen.add(key)
            names.append(text[:200])

        for block in (payload.get('jumia') or {}).get('products') or []:
            if isinstance(block, dict):
                add(block.get('name') or block.get('title'))
        for block in (payload.get('jiji') or {}).get('listings') or []:
            if isinstance(block, dict):
                add(block.get('title') or block.get('name'))
        for post in (payload.get('social') or {}).get('posts') or []:
            if not isinstance(post, dict):
                continue
            hint = post.get('product_hint') or post.get('title')
            # Évite les captions longues / mots-clés bruts
            if hint and len(str(hint).split()) <= 8:
                add(hint)

        return names

    @staticmethod
    def _norm_name(name: str) -> str:
        return ' '.join(str(name or '').lower().split())

    @classmethod
    def _recommendation_for_note(cls, note: float, current: str = '') -> str:
        """Libellé reco fixe selon le palier de note."""
        del current  # la note prime toujours
        if note >= 7.5:
            return RECO_BON
        if note >= 5.0:
            return RECO_MOYEN
        return RECO_FAIBLE

    @classmethod
    def _default_synthese(cls, produit: str, note: float, rang: int) -> str:
        """Analyse courte si DeepSeek omet la synthèse (ex. rangs 11–15)."""
        name = (produit or 'Ce produit').strip()[:80]
        if note >= 7.5:
            text = (
                f'«{name}» (n°{rang}, {note}/10) : forte demande au Sénégal et bons '
                f'signaux Jumia/Jiji — la note reflète une marge/rotation attractives. '
                f'Bon candidat à stocker.'
            )
        elif note >= 5.0:
            text = (
                f'«{name}» (n°{rang}, {note}/10) : opportunité correcte mais signaux '
                f'mixtes (prix, volume ou concurrence). Note moyenne : tester un petit '
                f'stock avant d’engager plus.'
            )
        else:
            text = (
                f'«{name}» (n°{rang}, {note}/10) : demande ou marge trop faibles au '
                f'Sénégal. La note basse justifie d’éviter le stock pour l’instant.'
            )
        return text[:SYNTH_MAX_LEN]

    @classmethod
    def _mk_item(
        cls,
        rank: int,
        name: str,
        *,
        note: float,
        recommandation: str,
        synthese: str,
        sources: list[str],
    ) -> dict:
        note_val = round(max(0.0, min(10.0, float(note))), 1)
        synth = (synthese or '').strip()
        if not synth or synth in ('.', '...', '…'):
            synth = cls._default_synthese(str(name), note_val, rank)
        return {
            'rang': rank,
            'produit': str(name)[:200],
            'note': note_val,
            'recommandation': cls._recommendation_for_note(note_val, recommandation)[:80],
            'synthese': synth[:SYNTH_MAX_LEN],
            'sources': sources[:6],
        }

    @classmethod
    def _normalize_items(cls, items: list[Any]) -> list[dict]:
        normalized = []
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            note_raw = item.get('note', 0)
            try:
                note = float(note_raw)
            except (TypeError, ValueError):
                note = 0.0
            note = round(max(0.0, min(10.0, note)), 1)
            produit = str(item.get('produit') or 'Produit')[:200]
            rang = int(item.get('rang') or i)
            synth = str(
                item.get('synthese') or item.get('commentaire_mistral') or ''
            ).strip()
            if not synth or synth in ('.', '...', '…'):
                synth = cls._default_synthese(produit, note, rang)
            reco_raw = str(item.get('recommandation') or '').strip()
            normalized.append({
                'rang': rang,
                'produit': produit,
                'note': note,
                'recommandation': cls._recommendation_for_note(note, reco_raw)[:80],
                'synthese': synth[:SYNTH_MAX_LEN],
                'sources': [
                    str(s) for s in (item.get('sources') or []) if s
                ][:6],
            })
        return normalized

    @classmethod
    def fallback_result(
        cls,
        payload: dict,
        *,
        domain_label: str,
        category_label: str,
        error: str = '',
    ) -> dict:
        """Résultat minimal si DeepSeek échoue — toujours Top 15."""
        products = cls.extract_candidate_names(payload)

        def mk_item(rank: int, name: str) -> dict:
            note = max(1.0, round(5.5 - 0.3 * rank, 1))
            return cls._mk_item(
                rank,
                name,
                note=note,
                recommandation=cls._recommendation_for_note(note),
                synthese=cls._default_synthese(name, note, rank),
                sources=['jumia', 'jiji', 'google_trends'],
            )

        top = [mk_item(i + 1, p) for i, p in enumerate(products[:TOP_N])]
        result = {
            'domaine': domain_label,
            'categorie': category_label,
            'top_investissement': top,
            'plus_recherche': list(top),
            'plus_aime': list(top),
            'vitesse_vente': list(top),
            'highlights': {},
            'fallback': True,
            'error': error,
        }
        return cls.ensure_top10(
            result,
            payload=payload,
            domain_label=domain_label,
            category_label=category_label,
        )
