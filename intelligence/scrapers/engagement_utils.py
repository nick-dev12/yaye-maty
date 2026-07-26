"""
Utilitaires métriques d'engagement — parsing et score de demande.
"""

from __future__ import annotations

import re

# Phrases d'intention d'achat (FR + expressions locales courantes)
PURCHASE_INTENT_PHRASES: tuple[str, ...] = (
    "c'est combien",
    'cest combien',
    'combien ca coute',
    'combien ça coûte',
    'quel est le prix',
    'le prix',
    'prix svp',
    'ou acheter',
    'où acheter',
    'en stock',
    'avez vous',
    'avez-vous',
    'disponible',
    'commander',
    'commande',
    'livraison',
    'whatsapp',
    'numero',
    'numéro',
    'contact',
    'boutique',
    'dakar',
    'thies',
    'touba',
    'kaolack',
    'ndar',
    'saint-louis',
)


def parse_metric_value(raw: str | None) -> int | None:
    """
    Convertit une métrique TikTok en entier.

    Exemples : « 12.5K », « 1,2 M », « 15 432 », « 890 ».
    """
    if not raw:
        return None

    text = raw.strip().lower()
    text = text.replace('\xa0', '').replace(' ', '')
    text = text.replace(',', '.')

    match = re.search(r'([\d.]+)\s*([km])?', text)
    if not match:
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else None

    value = float(match.group(1))
    suffix = match.group(2) or ''

    if suffix == 'k':
        value *= 1_000
    elif suffix == 'm':
        value *= 1_000_000

    return int(value)


def compute_demand_score(
    *,
    views: int | None = None,
    likes: int | None = None,
    shares: int | None = None,
    saves: int | None = None,
    comment_count: int | None = None,
    purchase_intent_count: int = 0,
) -> int:
    """
    Score de validation marché pour prioriser les stocks.

    Les favoris (saves) et partages pèsent plus que les simples vues.
    """
    score = 0.0
    score += (saves or 0) * 5.0
    score += (shares or 0) * 3.0
    score += purchase_intent_count * 15.0
    score += (comment_count or 0) * 2.0
    score += (likes or 0) * 0.5
    score += (views or 0) * 0.001
    return int(round(score))


def detect_purchase_intent(text: str) -> bool:
    """Détecte une intention d'achat dans un commentaire ou description."""
    normalized = text.lower().strip()
    return any(phrase in normalized for phrase in PURCHASE_INTENT_PHRASES)


def count_purchase_intents(comments: list) -> int:
    """Compte les commentaires avec intention d'achat."""
    count = 0
    for item in comments:
        if isinstance(item, dict):
            text = str(item.get('text', ''))
        else:
            text = str(item)
        if detect_purchase_intent(text):
            count += 1
    return count


def extract_hashtags(text: str) -> list[str]:
    """Extrait les hashtags d'une description (#AgricultureSenegal)."""
    if not text:
        return []
    tags = re.findall(r'#([\w\u00C0-\u024F]+)', text, flags=re.UNICODE)
    seen: list[str] = []
    for tag in tags:
        normalized = tag.lower()
        if normalized not in seen:
            seen.append(normalized)
    return seen[:20]
