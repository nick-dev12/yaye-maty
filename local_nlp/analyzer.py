"""
Analyseur NLP local — équipement agricole Sénégal.

MVP : classification par mots-clés métier (rapide, CPU).
Extensible : remplacez analyze() par un modèle transformers.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisResult:
    """Résultat d'analyse pour une publication."""

    post_id: int
    category: str
    sentiment: str
    keywords: list[str]
    confidence: float


# Taxonomie métier YAYEMATY — équipement agricole
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    'irrigation': (
        'irrigation', 'pompe', 'arrosage', 'goutte', 'eau', 'forage', 'puit',
    ),
    'solaire_pompage': (
        'solaire', 'photovoltaique', 'panneau', 'energie', 'batterie',
    ),
    'tracteurs_machinisme': (
        'tracteur', 'charrue', 'moissonneuse', 'semoir', 'machine', 'engin',
    ),
    'semences_engrais': (
        'semence', 'engrais', 'fertilisa', 'npk', 'uree', 'phyto', 'herbicide',
    ),
    'elevage_alimentation': (
        'elevage', 'volaille', 'poulet', 'betail', 'vache', 'mouton', 'aliment',
        'provende', 'cage', 'poulailler',
    ),
    'marche_prix': (
        'prix', 'marche', 'vente', 'achat', 'commercial', 'fournisseur', 'commande',
    ),
    'formation_conseil': (
        'formation', 'conseil', 'technique', 'agronome', 'cooperative', 'saed',
    ),
}

POSITIVE_WORDS = (
    'bon', 'bonne', 'excellent', 'super', 'merci', 'reussi', 'profit',
    'qualite', 'efficace', 'recommande', 'gagnant', 'opportunite',
)

PURCHASE_INTENT_WORDS = (
    'combien', 'prix', 'acheter', 'commander', 'stock', 'disponible',
    'whatsapp', 'contact', 'livraison', 'boutique', 'dakar',
)

NEGATIVE_WORDS = (
    'cher', 'chere', 'probleme', 'difficile', 'panne', 'mauvais', 'perte',
    'secheresse', 'crise', 'rupture', 'arnaque', 'decu',
)


@dataclass(frozen=True)
class JijiAnalysisResult:
    """Résultat d'analyse pour une annonce Jiji."""

    listing_id: int
    nlp_category: str
    sentiment: str
    keywords: list[str]
    relevance_score: float
    extracted_product: str
    is_agricultural: bool


class AgriculturalAnalyzer:
    """Analyse locale des textes collectés sur les réseaux sociaux."""

    def analyze_batch(self, posts: list[dict]) -> list[AnalysisResult]:
        return [self.analyze_post(post) for post in posts]

    def analyze_post(self, post: dict) -> AnalysisResult:
        post_id = int(post['id'])
        content = str(post.get('content', ''))
        comments = post.get('comments') or []
        comment_texts = [
            item.get('text', '') if isinstance(item, dict) else str(item)
            for item in comments
        ]
        full_text = content + ' ' + ' '.join(comment_texts)
        normalized = self._normalize(full_text)

        category, cat_score = self._detect_category(normalized)
        sentiment = self._detect_sentiment(normalized)
        keywords = self._extract_keywords(normalized, category)

        return AnalysisResult(
            post_id=post_id,
            category=category,
            sentiment=sentiment,
            keywords=keywords,
            confidence=round(cat_score, 2),
        )

    def to_api_payload(self, results: list[AnalysisResult]) -> list[dict]:
        """Format attendu par POST /intelligence/api/analyzed-data/."""
        return [
            {
                'id': item.post_id,
                'category': item.category,
                'sentiment': item.sentiment,
                'keywords': item.keywords,
                'status': 'done',
            }
            for item in results
        ]

    def analyze_jiji_batch(self, listings: list[dict]) -> list[JijiAnalysisResult]:
        return [self.analyze_jiji_listing(row) for row in listings]

    def analyze_jiji_listing(self, listing: dict) -> JijiAnalysisResult:
        listing_id = int(listing['id'])
        text = str(listing.get('text') or listing.get('title') or '')
        desc = str(listing.get('description') or '')
        combined = self._normalize(f'{text} {desc}')
        category, cat_score = self._detect_category(combined)
        sentiment = self._detect_sentiment(combined)
        keywords = self._extract_keywords(combined, category)
        agri_hints = (
            'agricol', 'motopompe', 'pompe', 'tracteur', 'irrigation', 'semence',
            'engrais', 'ferme', 'volaille', 'farm', 'solaire',
        )
        phone_hints = ('iphone', 'telephone', 'samsung', 'smartphone')
        is_agricultural = any(h in combined for h in agri_hints) and not any(
            h in combined for h in phone_hints
        )
        product_label = (listing.get('search_keyword') or listing.get('title') or '')[:80]
        return JijiAnalysisResult(
            listing_id=listing_id,
            nlp_category=category,
            sentiment=sentiment,
            keywords=keywords,
            relevance_score=round(cat_score if is_agricultural else 0.1, 2),
            extracted_product=product_label,
            is_agricultural=is_agricultural,
        )

    def to_jiji_api_payload(self, results: list[JijiAnalysisResult]) -> list[dict]:
        return [
            {
                'id': item.listing_id,
                'nlp_category': item.nlp_category,
                'sentiment': item.sentiment,
                'keywords_detected': item.keywords,
                'relevance_score': item.relevance_score,
                'extracted_product': item.extracted_product,
                'extracted_product_slug': item.nlp_category.replace(' ', '_')[:80],
                'is_agricultural': item.is_agricultural,
                'analysis_status': 'done' if item.is_agricultural else 'skipped',
                'method': 'keyword',
                'confidence': item.relevance_score,
            }
            for item in results
        ]

    def _detect_category(self, text: str) -> tuple[str, float]:
        scores: dict[str, int] = {}

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score:
                scores[category] = score

        if not scores:
            return 'autre', 0.35

        best_category = max(scores, key=scores.get)
        max_score = scores[best_category]
        confidence = min(0.95, 0.45 + max_score * 0.12)
        return best_category, confidence

    def _detect_sentiment(self, text: str) -> str:
        pos = sum(1 for w in POSITIVE_WORDS if w in text)
        neg = sum(1 for w in NEGATIVE_WORDS if w in text)

        if pos > neg:
            return 'positive'
        if neg > pos:
            return 'negative'
        return 'neutral'

    def _extract_keywords(self, text: str, category: str) -> list[str]:
        found: list[str] = []
        keywords = CATEGORY_KEYWORDS.get(category, ())

        for kw in keywords:
            if kw in text and kw not in found:
                found.append(kw)

        if not found:
            tokens = [t for t in text.split() if len(t) > 4][:5]
            found = tokens

        for word in PURCHASE_INTENT_WORDS:
            if word in text and word not in found:
                found.append(word)

        return found[:8]

    @staticmethod
    def _normalize(text: str) -> str:
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s#@]', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()
