"""
Extraction du nom produit depuis captions, commentaires et hashtags.
"""

from __future__ import annotations

import re
import unicodedata

from intelligence.nlp_taxonomy import PRODUCT_CATALOG


class ProductExtractionService:
    """Détecte le produit agricole mentionné dans un texte (regex + catalogue métier)."""

    _COMPILED: dict[str, tuple[tuple[str, ...], ...]] | None = None

    @classmethod
    def extract(cls, text: str, *, hashtags: list | None = None) -> dict | None:
        """
        Retourne {slug, label, category, confidence} ou None.

        Priorise les expressions longues (ex. « mini tracteur » avant « tracteur »).
        """
        normalized = cls._normalize(text)
        hashtag_text = ' '.join(
            str(tag).lstrip('#') for tag in (hashtags or []) if tag
        )
        combined = f'{normalized} {cls._normalize(hashtag_text)}'.strip()
        if len(combined) < 3:
            return None

        best_slug = ''
        best_score = 0
        best_label = ''
        best_category = ''

        for slug, meta in cls._sorted_catalog():
            score = 0
            for keyword in meta['keywords']:
                if keyword in combined:
                    score += len(keyword.split()) + (2 if ' ' in keyword else 1)

            if score > best_score:
                best_score = score
                best_slug = slug
                best_label = meta['label']
                best_category = meta.get('category', '')

        if best_score <= 0:
            return None

        confidence = min(0.98, 0.55 + best_score * 0.08)
        return {
            'slug': best_slug,
            'label': best_label,
            'category': best_category,
            'confidence': confidence,
        }

    @classmethod
    def extract_for_comment(cls, text: str, intent: str, *, context: str = '') -> dict | None:
        """Extrait le produit sur commentaires à intention commerciale."""
        if intent not in ('intention_achat', 'demande_information'):
            return None
        combined = f'{text} {context}'.strip()
        return cls.extract(combined)

    @classmethod
    def extract_for_post(cls, content: str, hashtags: list | None = None) -> dict | None:
        return cls.extract(content, hashtags=hashtags)

    @classmethod
    def get_label(cls, slug: str) -> str:
        meta = PRODUCT_CATALOG.get(slug)
        return meta['label'] if meta else slug.replace('_', ' ').title()

    @classmethod
    def _sorted_catalog(cls) -> list[tuple[str, dict]]:
        items = list(PRODUCT_CATALOG.items())
        items.sort(
            key=lambda item: max(len(kw) for kw in item[1]['keywords']),
            reverse=True,
        )
        return items

    @staticmethod
    def _normalize(text: str) -> str:
        if not text:
            return ''
        text = unicodedata.normalize('NFKD', text.lower())
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r'[^\w\s#-]', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()
