"""Tests du filtre hybride Wolof/FR (avec dictionnaire en base)."""

from django.test import TestCase

from intelligence.models.social_comment import SocialComment
from intelligence.services.local_keyword_filter import LocalKeywordFilter


class LocalKeywordFilterTests(TestCase):
    def test_wolof_purchase_intent(self):
        result = LocalKeywordFilter.classify('Ñaata la pompe bi ?')
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], SocialComment.Intent.PURCHASE)

    def test_french_purchase_intent(self):
        result = LocalKeywordFilter.classify('C\'est combien la livraison à Dakar ?')
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], SocialComment.Intent.PURCHASE)

    def test_complaint(self):
        result = LocalKeywordFilter.classify('C\'est une arnaque ce produit')
        self.assertIsNotNone(result)
        self.assertEqual(result['intent'], SocialComment.Intent.COMPLAINT)

    def test_no_match_returns_none(self):
        result = LocalKeywordFilter.classify('Bonjour tout le monde')
        self.assertIsNone(result)
