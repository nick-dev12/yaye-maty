"""
Test runner — réutilise la base PostgreSQL du .env (VPS).

Ne crée jamais de base `test_*` : pas besoin du privilège PostgreSQL CREATEDB.
Les tests s'exécutent sur la base configurée (DB_NAME), avec rollback transactionnel
par test (TestCase Django).
"""

from django.test.runner import DiscoverRunner


class VpsExistingDatabaseTestRunner(DiscoverRunner):
    """Utilise la base existante — aucune CREATE/DROP DATABASE."""

    def setup_databases(self, **kwargs):
        from django.db import connections

        conn = connections['default']
        db_name = conn.settings_dict['NAME']
        # (connection, alias_de_teardown, destroy_flag) — destroy=False : ne pas DROP
        return [(conn, db_name, False)]

    def teardown_databases(self, old_config, **kwargs):
        pass
