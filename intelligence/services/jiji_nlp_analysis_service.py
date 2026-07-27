"""
Analyse NLP des annonces Jiji — titre + description (équipement agricole SN).

Le VPS exécute un filtre lexical rapide ; CamemBERT reste sur la machine locale
via API ``raw-jiji-listings`` / ``analyzed-jiji-listings``.
"""

from __future__ import annotations

import logging
import re

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from intelligence.models import JijiListing
from intelligence.models.social_comment import SocialComment
from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.local_keyword_filter import LocalKeywordFilter
from intelligence.services.product_extraction_service import ProductExtractionService

logger = logging.getLogger(__name__)

NON_AGRICULTURAL_HINTS: tuple[str, ...] = (
    'iphone', 'samsung', 'telephone', 'smartphone', 'tecno', 'infinix',
    'chargeur', 'ecouteur', 'television', 'televiseur', 'climatiseur',
    'vetement', 'chaussure', 'sac a main', 'maquillage', 'cosmetique',
)

LISTING_ASPECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    'prix': ('prix', 'negociable', 'négociable', 'bon prix', 'promo', 'fcfa'),
    'etat': ('neuf', 'occasion', 'reconditionne', 'etat', 'état'),
    'livraison': ('livraison', 'dakar', 'thies', 'thiès', 'region', 'région'),
    'qualite': ('qualite', 'qualité', 'original', 'authentique', 'garantie'),
}


class JijiNlpAnalysisService:
    """Analyse / application NLP sur les annonces Jiji."""

    @classmethod
    def get_pending_for_nlp(cls, *, limit: int = 50) -> list:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        return list(
            Listing.objects.filter(is_analyzed=False)
            .order_by('scraped_at')[:limit]
        )

    @classmethod
    def serialize_for_nlp(cls, listing) -> dict:
        return {
            'id': listing.pk,
            'listing_id': listing.listing_id,
            'title': listing.title,
            'description': listing.description,
            'search_keyword': listing.search_keyword,
            'category': listing.category,
            'condition': listing.condition,
            'price_xof': float(listing.price_xof) if listing.price_xof is not None else None,
            'views_count': int(listing.views_count or 0),
            'location_region': listing.location_region,
            'location_area': listing.location_area,
            'seller_name': listing.seller_name,
            'listing_url': listing.listing_url,
            'catalog_product_slug': listing.catalog_product_slug,
            'text': listing.text,
        }

    @classmethod
    @transaction.atomic
    def apply_analysis_results(cls, results: list[dict]) -> dict:
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        updated = 0
        missing = 0
        now = timezone.now()

        for item in results:
            if not isinstance(item, dict):
                continue
            listing_id = item.get('id')
            if not listing_id:
                continue
            try:
                listing = Listing.objects.get(pk=listing_id)
            except Listing.DoesNotExist:
                missing += 1
                continue

            cls._apply_payload(listing, item, now=now)
            listing.save()
            updated += 1

        logger.info('Jiji NLP apply : %s mis à jour, %s manquants', updated, missing)
        return {'updated': updated, 'missing': missing}

    @classmethod
    def analyze_pending_locally(
        cls,
        *,
        limit: int = 100,
        use_camembert: bool | None = None,
    ) -> dict:
        """
        Analyse hybride des annonces Jiji.

        ``use_camembert`` : None → lit ``NLP_CLASSIFIER_ENABLED`` (VPS ou local).
        """
        from intelligence.collection_config import is_nlp_camembert_enabled

        if use_camembert is None:
            use_camembert = is_nlp_camembert_enabled()

        pending = cls.get_pending_for_nlp(limit=limit)
        results = []
        for listing in pending:
            text = listing.text or listing.title or ''
            lexical = cls.analyze_text_lexical(text)
            payload = {'id': listing.pk, **lexical}

            if use_camembert and text.strip() and lexical.get('is_agricultural', True):
                try:
                    from intelligence.services.camembert_classifier_service import CamembertClassifierService

                    cat = CamembertClassifierService.classify_post_category(text)
                    sent = CamembertClassifierService.classify_sentiment(text)
                    intent = CamembertClassifierService.classify_comment_intent(text)

                    if cat.get('category'):
                        payload['nlp_category'] = cat['category']
                        payload['extracted_product_slug'] = cat['category']
                    if sent.get('sentiment'):
                        payload['sentiment'] = sent['sentiment']
                    if intent.get('intent'):
                        payload['intent'] = intent['intent']
                    confidences = [
                        float(c)
                        for c in (
                            cat.get('confidence'),
                            sent.get('confidence'),
                            intent.get('confidence'),
                            payload.get('confidence'),
                        )
                        if c is not None
                    ]
                    if confidences:
                        payload['relevance_score'] = round(max(confidences), 3)
                        payload['confidence'] = payload['relevance_score']
                    payload['method'] = SocialComment.AnalysisMethod.CAMEMBERT
                    payload['analysis_status'] = JijiListing.AnalysisStatus.DONE
                    payload['is_agricultural'] = cat.get('category', 'autre') != 'autre'
                except Exception:
                    logger.exception('CamemBERT annonce Jiji #%s échoué — lexical conservé', listing.pk)

            results.append(payload)

        stats = cls.apply_analysis_results(results)
        stats['analyzed'] = len(results)
        stats['camembert'] = use_camembert
        return stats

    @classmethod
    def analyze_text_lexical(cls, text: str) -> dict:
        """Extraction produit agricole, pertinence et aspects sans modèle lourd."""
        combined = (text or '').strip()
        low = cls._normalize(combined)

        product = ProductExtractionService.extract(combined)
        fast_cat = LocalKeywordFilter.classify_post_category(combined)
        fast_intent = LocalKeywordFilter.classify(combined)

        is_agricultural = cls._is_agricultural(low, product=product)
        if not is_agricultural:
            return {
                'analysis_status': JijiListing.AnalysisStatus.SKIPPED,
                'is_agricultural': False,
                'relevance_score': 0.05,
                'sentiment': JijiListing.Sentiment.NEUTRAL,
                'intent': SocialComment.Intent.OFF_TOPIC,
                'nlp_category': 'hors_perimetre',
                'keywords_detected': [],
                'aspects': {},
                'extracted_product': '',
                'extracted_product_slug': '',
                'confidence': 0.4,
                'method': SocialComment.AnalysisMethod.KEYWORD,
            }

        relevance = 0.35
        extracted_product = ''
        extracted_slug = ''
        nlp_category = fast_cat[0] if fast_cat else 'autre'

        if product:
            extracted_product = product.get('label', '')[:120]
            extracted_slug = product.get('slug', '')[:80]
            nlp_category = product.get('category') or nlp_category
            relevance = float(product.get('confidence') or 0.6)
        elif fast_cat:
            relevance = max(relevance, float(fast_cat[1] or 0.45))

        intent = SocialComment.Intent.INFO
        if fast_intent and fast_intent.get('intent') == SocialComment.Intent.PURCHASE:
            intent = SocialComment.Intent.PURCHASE
        elif any(w in low for w in ('vendre', 'a vendre', 'à vendre', 'disponible', 'stock')):
            intent = SocialComment.Intent.INFO

        sentiment = JijiListing.Sentiment.NEUTRAL
        if any(w in low for w in ('excellent', 'bon etat', 'bon état', 'neuf', 'qualite', 'qualité')):
            sentiment = JijiListing.Sentiment.POSITIVE
        elif any(w in low for w in ('panne', 'defectueux', 'défectueux', 'mauvais', 'usé', 'use')):
            sentiment = JijiListing.Sentiment.NEGATIVE

        aspects: dict[str, str] = {}
        for aspect, kws in LISTING_ASPECT_KEYWORDS.items():
            if any(k in low for k in kws):
                aspects[aspect] = 'pos' if sentiment == JijiListing.Sentiment.POSITIVE else 'neu'

        keywords = cls._extract_keywords(low, nlp_category)

        return {
            'analysis_status': JijiListing.AnalysisStatus.DONE,
            'is_agricultural': True,
            'relevance_score': round(min(0.99, relevance), 3),
            'sentiment': sentiment,
            'intent': intent,
            'nlp_category': nlp_category,
            'keywords_detected': keywords[:12],
            'aspects': aspects,
            'extracted_product': extracted_product,
            'extracted_product_slug': extracted_slug,
            'confidence': round(relevance, 3),
            'method': SocialComment.AnalysisMethod.KEYWORD,
        }

    @classmethod
    def _apply_payload(cls, listing, item: dict, *, now) -> None:
        status = (item.get('analysis_status') or JijiListing.AnalysisStatus.DONE).strip()
        if status in JijiListing.AnalysisStatus.values:
            listing.analysis_status = status
        else:
            listing.analysis_status = JijiListing.AnalysisStatus.DONE

        listing.is_analyzed = True
        listing.analyzed_at = now
        listing.nlp_analyzed_at = now

        sentiment = (item.get('sentiment') or '').strip().lower()
        if sentiment in JijiListing.Sentiment.values:
            listing.sentiment = sentiment

        intent = (item.get('intent') or '').strip()
        if intent in SocialComment.Intent.values:
            listing.intent = intent

        if item.get('extracted_product'):
            listing.extracted_product = str(item['extracted_product'])[:120]
        slug = (item.get('extracted_product_slug') or item.get('catalog_product_slug') or '').strip()
        if slug:
            listing.catalog_product_slug = slug[:80]
        if item.get('nlp_category'):
            listing.nlp_category = str(item['nlp_category'])[:64]

        keywords = item.get('keywords_detected')
        if isinstance(keywords, list):
            listing.keywords_detected = [str(k)[:60] for k in keywords][:12]

        aspects = item.get('aspects')
        if isinstance(aspects, dict):
            listing.aspects = aspects

        if item.get('relevance_score') is not None:
            try:
                listing.relevance_score = float(item['relevance_score'])
            except (TypeError, ValueError):
                pass

        if 'is_agricultural' in item:
            listing.is_agricultural = bool(item['is_agricultural'])

        method = (item.get('method') or SocialComment.AnalysisMethod.KEYWORD).strip()
        if method in SocialComment.AnalysisMethod.values:
            listing.analysis_method = method

        if item.get('confidence') is not None:
            try:
                listing.confidence_score = float(item['confidence'])
            except (TypeError, ValueError):
                pass

    @classmethod
    def _is_agricultural(cls, normalized_text: str, *, product: dict | None) -> bool:
        if product and product.get('slug'):
            return True
        if any(h in normalized_text for h in NON_AGRICULTURAL_HINTS):
            if not product:
                return False
        agri_hints = (
            'agricol', 'ferme', 'irrigation', 'motopompe', 'pompe', 'tracteur',
            'semence', 'engrais', 'elevage', 'volaille', 'materiel agricole',
            'farm', 'solaire', 'goutte',
        )
        return any(h in normalized_text for h in agri_hints)

    @classmethod
    def _extract_keywords(cls, normalized_text: str, category: str) -> list[str]:
        found: list[str] = []
        for token in re.split(r'[^a-z0-9]+', normalized_text):
            if len(token) >= 4 and token not in found:
                found.append(token)
            if len(found) >= 8:
                break
        if category and category not in found:
            found.insert(0, category.replace('_', ' '))
        return found

    @staticmethod
    def _normalize(text: str) -> str:
        t = (text or '').lower()
        for a, b in (('é', 'e'), ('è', 'e'), ('ê', 'e'), ('à', 'a'), ('ù', 'u'), ('ô', 'o')):
            t = t.replace(a, b)
        return re.sub(r'\s+', ' ', t).strip()

    @classmethod
    def display_listings_qs(cls):
        """Annonces analysées et pertinentes pour l'affichage Intelligence."""
        router = CollectionModelRouter()
        Listing = router.jiji_listing_model
        return (
            Listing.objects.filter(is_analyzed=True, is_agricultural=True)
            .order_by(F('relevance_score').desc(nulls_last=True), '-views_count', '-scraped_at')
        )
