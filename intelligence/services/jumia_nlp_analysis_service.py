"""
Analyse NLP des avis Jumia — destinée à la machine locale (CamemBERT).

Le VPS ne doit PAS charger le modèle : il stocke les avis bruts et reçoit
les résultats via API REST (apply_analysis_results).
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from django.db import transaction
from django.utils import timezone

from intelligence.models.jumia_review import JumiaReview
from intelligence.models.social_comment import SocialComment
from intelligence.services.collection_model_router import CollectionModelRouter

logger = logging.getLogger(__name__)

ASPECT_LABELS = (
    'qualite',
    'durabilite',
    'panne',
    'livraison',
    'prix',
    'service',
    'notice',
)

FAILURE_PATTERNS: dict[str, tuple[str, ...]] = {
    'fragile': ('fragile', 'cassé', 'casse', 'se casse', 'facilement cass'),
    'panne': ('panne', 'ne marche pas', 'ne fonctionne pas', 'hors service', 'defectueux', 'défectueux'),
    'batterie': ('batterie', 'autonomie', 'ne dure pas', 'se decharge', 'se décharge'),
    'livraison_retard': ('livraison', 'retard', 'pas recu', 'pas reçu', "n'est pas arrive", 'colis'),
    'notice_manquante': ('notice', 'manuel', 'pas en francais', 'pas en français', 'mode d emploi'),
    'pieces': ('piece', 'pièce', 'accessoire manquant', 'incomplet', 'manque'),
}

ASPECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    'qualite': ('qualite', 'qualité', 'bon produit', 'mauvais', 'nickel', 'top'),
    'durabilite': ('solide', 'resistant', 'résistant', 'dure', 'fragile'),
    'panne': ('panne', 'marche pas', 'fonctionne pas', 'defectueux'),
    'livraison': ('livraison', 'livre', 'livré', 'colis', 'retard'),
    'prix': ('prix', 'cher', 'abordable', 'couteux', 'coûteux', 'bon marche'),
    'service': ('service', 'vendeur', 'sav', 'garantie', 'apres vente'),
    'notice': ('notice', 'manuel', 'francais', 'français', 'explication'),
}


class JumiaNlpAnalysisService:
    """Analyse / application des résultats NLP sur les avis Jumia."""

    @classmethod
    def get_pending_for_nlp(cls, *, limit: int = 50) -> list:
        router = CollectionModelRouter()
        Review = router.jumia_review_model
        return list(
            Review.objects.filter(is_analyzed=False)
            .select_related('product')
            .order_by('scraped_at')[:limit]
        )

    @classmethod
    def serialize_for_nlp(cls, review) -> dict:
        product = review.product
        return {
            'id': review.pk,
            'sku': getattr(product, 'sku', ''),
            'product_name': getattr(product, 'name', ''),
            'search_keyword': getattr(product, 'search_keyword', ''),
            'catalog_product_slug': getattr(product, 'catalog_product_slug', ''),
            'rating_stars': review.rating_stars,
            'title': review.title,
            'comment_text': review.comment_text,
            'text': review.text,
            'author': review.author,
            'verified_purchase': review.verified_purchase,
            'review_date': review.review_date.isoformat() if review.review_date else None,
        }

    @classmethod
    @transaction.atomic
    def apply_analysis_results(cls, results: list[dict]) -> dict:
        """
        Applique les résultats NLP poussés par la machine locale.

        Body item attendu :
        {
          "id": 12,
          "sentiment": "negative",
          "intent": "plainte",
          "aspects": {"qualite": "neg", "livraison": "neg"},
          "failure_tags": ["fragile", "livraison_retard"],
          "confidence": 0.82,
          "aspect_confidence": 0.7,
          "extracted_product": "...",
          "extracted_product_slug": "motopompe",
          "method": "camembert"
        }
        """
        router = CollectionModelRouter()
        Review = router.jumia_review_model
        Product = router.jumia_product_model
        updated = 0
        missing = 0
        touched_products: set[int] = set()
        now = timezone.now()

        for item in results:
            if not isinstance(item, dict):
                continue
            review_id = item.get('id')
            if not review_id:
                continue
            try:
                review = Review.objects.select_related('product').get(pk=review_id)
            except Review.DoesNotExist:
                missing += 1
                continue

            sentiment = (item.get('sentiment') or '').strip().lower()
            if sentiment in JumiaReview.Sentiment.values:
                review.sentiment = sentiment
            elif review.rating_stars is not None:
                if review.rating_stars <= 2:
                    review.sentiment = JumiaReview.Sentiment.NEGATIVE
                elif review.rating_stars >= 4:
                    review.sentiment = JumiaReview.Sentiment.POSITIVE
                else:
                    review.sentiment = JumiaReview.Sentiment.NEUTRAL

            intent = (item.get('intent') or '').strip()
            if intent in SocialComment.Intent.values:
                review.intent = intent
            elif review.sentiment == JumiaReview.Sentiment.NEGATIVE:
                review.intent = SocialComment.Intent.COMPLAINT

            aspects = item.get('aspects') if isinstance(item.get('aspects'), dict) else {}
            failure_tags = item.get('failure_tags') if isinstance(item.get('failure_tags'), list) else []
            review.aspects = aspects
            review.failure_tags = [str(t)[:60] for t in failure_tags][:12]
            if item.get('aspect_confidence') is not None:
                try:
                    review.aspect_confidence = float(item['aspect_confidence'])
                except (TypeError, ValueError):
                    pass
            if item.get('confidence') is not None:
                try:
                    review.confidence_score = float(item['confidence'])
                except (TypeError, ValueError):
                    pass

            method = (item.get('method') or SocialComment.AnalysisMethod.CAMEMBERT).strip()
            if method in SocialComment.AnalysisMethod.values:
                review.analysis_method = method

            if item.get('extracted_product'):
                review.extracted_product = str(item['extracted_product'])[:120]
            if item.get('extracted_product_slug'):
                review.extracted_product_slug = str(item['extracted_product_slug'])[:80]
            elif getattr(review.product, 'catalog_product_slug', ''):
                review.extracted_product_slug = review.product.catalog_product_slug

            review.is_analyzed = True
            review.analyzed_at = now
            review.save()
            updated += 1
            if review.product_id:
                touched_products.add(review.product_id)

        # Agrège sentiment/aspects au niveau produit
        for pid in touched_products:
            try:
                product = Product.objects.get(pk=pid)
            except Product.DoesNotExist:
                continue
            cls._refresh_product_nlp_summary(product, Review)

        # Signaux marché + Top10 (sans charger CamemBERT)
        try:
            from intelligence.services.jumia_market_signal_service import JumiaMarketSignalService
            JumiaMarketSignalService.refresh_all()
        except Exception:
            logger.exception('Refresh signaux après NLP Jumia échoué')

        try:
            from intelligence.services.purchase_recommendation_service import PurchaseRecommendationService
            PurchaseRecommendationService.refresh_top_recommendations()
        except Exception:
            logger.exception('Refresh Top10 après NLP Jumia échoué')

        return {'updated': updated, 'missing': missing, 'products_touched': len(touched_products)}

    @classmethod
    def analyze_pending_locally(cls, *, limit: int = 50, use_camembert: bool = True) -> dict:
        """
        Analyse locale (machine cerveau) des avis pending.

        Utilise un filtre lexical rapide, puis CamemBERT si activé.
        """
        pending = cls.get_pending_for_nlp(limit=limit)
        results = []
        for review in pending:
            text = review.text or ''
            lexical = cls.analyze_text_lexical(text, rating_stars=review.rating_stars)
            payload = {
                'id': review.pk,
                **lexical,
                'method': SocialComment.AnalysisMethod.KEYWORD,
            }
            if use_camembert and text.strip():
                try:
                    from intelligence.services.camembert_classifier_service import CamembertClassifierService
                    sent = CamembertClassifierService.classify_sentiment(text)
                    intent = CamembertClassifierService.classify_comment_intent(text)
                    payload['sentiment'] = sent.get('sentiment') or payload['sentiment']
                    payload['confidence'] = sent.get('confidence')
                    payload['intent'] = intent.get('intent') or payload.get('intent', '')
                    payload['method'] = SocialComment.AnalysisMethod.CAMEMBERT
                except Exception:
                    logger.exception('CamemBERT avis Jumia #%s échoué — lexical conservé', review.pk)
            if getattr(review.product, 'catalog_product_slug', ''):
                payload['extracted_product_slug'] = review.product.catalog_product_slug
                payload['extracted_product'] = getattr(review.product, 'name', '')[:120]
            results.append(payload)
        stats = cls.apply_analysis_results(results)
        stats['analyzed'] = len(results)
        return stats

    @classmethod
    def analyze_text_lexical(cls, text: str, *, rating_stars: int | None = None) -> dict:
        """Extraction légère d'aspects / failles sans modèle IA."""
        low = cls._normalize(text)
        failure_tags = []
        for tag, patterns in FAILURE_PATTERNS.items():
            if any(p in low for p in patterns):
                failure_tags.append(tag)

        aspects: dict[str, str] = {}
        for aspect, kws in ASPECT_KEYWORDS.items():
            if any(k in low for k in kws):
                # polarité simple
                neg_cues = ('pas', 'mauvais', 'nul', 'probleme', 'problème', 'retard', 'casse', 'panne')
                pos_cues = ('bon', 'bien', 'super', 'excellent', 'top', 'nickel', 'satisfait')
                # fenêtre locale approximative
                polarity = 'neu'
                if any(n in low for n in neg_cues) or (rating_stars is not None and rating_stars <= 2):
                    polarity = 'neg'
                elif any(p in low for p in pos_cues) or (rating_stars is not None and rating_stars >= 4):
                    polarity = 'pos'
                aspects[aspect] = polarity

        if rating_stars is not None:
            if rating_stars <= 2:
                sentiment = JumiaReview.Sentiment.NEGATIVE
                intent = SocialComment.Intent.COMPLAINT
            elif rating_stars >= 4:
                sentiment = JumiaReview.Sentiment.POSITIVE
                intent = SocialComment.Intent.INFO
            else:
                sentiment = JumiaReview.Sentiment.NEUTRAL
                intent = SocialComment.Intent.INFO
        else:
            sentiment = JumiaReview.Sentiment.NEGATIVE if failure_tags else JumiaReview.Sentiment.NEUTRAL
            intent = SocialComment.Intent.COMPLAINT if failure_tags else ''

        return {
            'sentiment': sentiment,
            'intent': intent,
            'aspects': aspects,
            'failure_tags': failure_tags,
            'aspect_confidence': 0.45 if aspects else None,
            'confidence': 0.5,
        }

    @classmethod
    def _refresh_product_nlp_summary(cls, product, Review) -> None:
        reviews = list(Review.objects.filter(product=product, is_analyzed=True))
        sentiments = Counter(r.sentiment for r in reviews if r.sentiment)
        aspect_counter: Counter = Counter()
        for r in reviews:
            for aspect, pol in (r.aspects or {}).items():
                aspect_counter[f'{aspect}:{pol}'] += 1
            for tag in (r.failure_tags or []):
                aspect_counter[f'fail:{tag}'] += 1
        product.sentiment_summary = dict(sentiments)
        product.aspect_summary = dict(aspect_counter.most_common(20))
        product.nlp_analyzed_at = timezone.now()
        product.analysis_status = product.AnalysisStatus.DONE
        product.save(update_fields=[
            'sentiment_summary', 'aspect_summary', 'nlp_analyzed_at', 'analysis_status', 'updated_at',
        ])

    @staticmethod
    def _normalize(text: str) -> str:
        t = (text or '').lower()
        for a, b in (('é', 'e'), ('è', 'e'), ('ê', 'e'), ('à', 'a'), ('ù', 'u'), ('ô', 'o')):
            t = t.replace(a, b)
        return re.sub(r'\s+', ' ', t).strip()
