"""
Settings de test — alias vers la configuration principale.

Les tests utilisent la même base PostgreSQL que le .env (VPS),
via VpsExistingDatabaseTestRunner (pas de base test_* séparée).

    py manage.py test intelligence.tests.test_import_scoring
"""

from .settings import *  # noqa: F401,F403
