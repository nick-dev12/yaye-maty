"""Tests pont ORM / Playwright."""

from django.test import SimpleTestCase

from intelligence.services.collection_model_router import CollectionModelRouter
from intelligence.services.collection_run_context import (
    CollectionRunContext,
    reset_collection_context,
    set_collection_context,
)
from intelligence.services.django_orm_safe import run_orm_safe


class DjangoOrmSafeTests(SimpleTestCase):
    def test_run_orm_safe_preserves_test_context(self):
        token = set_collection_context(CollectionRunContext.test())
        try:
            is_test = run_orm_safe(lambda: CollectionModelRouter().is_test)
            self.assertTrue(is_test)
        finally:
            reset_collection_context(token)
