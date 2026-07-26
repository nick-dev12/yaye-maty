"""
Commande : vérification infrastructure (DB, Redis, Celery).

Usage :
    python manage.py check_infrastructure
    python manage.py check_infrastructure --celery-task
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Vérifie PostgreSQL, Redis/Memurai et optionnellement Celery.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--celery-task',
            action='store_true',
            help='Envoie une tâche ping Celery (worker requis).',
        )

    def handle(self, *args, **options):
        results: list[tuple[str, bool, str]] = []

        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            results.append(('PostgreSQL', True, 'Connexion OK'))
        except Exception as exc:
            results.append(('PostgreSQL', False, str(exc)))

        redis_ok, redis_msg = self._check_redis()
        results.append(('Redis/Memurai', redis_ok, redis_msg))

        if options['celery_task']:
            celery_ok, celery_msg = self._check_celery_task()
            results.append(('Celery worker', celery_ok, celery_msg))

        all_ok = all(item[1] for item in results)
        for label, ok, message in results:
            style = self.style.SUCCESS if ok else self.style.ERROR
            status = 'OK' if ok else 'ÉCHEC'
            self.stdout.write(style(f'[{status}] {label} — {message}'))

        if not all_ok:
            import sys
            from django.conf import settings

            pool = getattr(settings, 'CELERY_WORKER_POOL', 'prefork')
            worker_cmd = f'celery -A yayematy_project worker -l info -P {pool}'
            if sys.platform == 'win32':
                worker_cmd += '  # obligatoire sous Windows (solo)'
            self.stdout.write(self.style.WARNING(
                f'Redis / Celery : démarrez Memurai ou Redis, puis le worker :\n  {worker_cmd}'
            ))

    @staticmethod
    def _check_redis() -> tuple[bool, str]:
        try:
            from django.conf import settings
            import redis

            client = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=3)
            pong = client.ping()
            return (bool(pong), settings.CELERY_BROKER_URL)
        except ImportError:
            return False, 'Package redis non installé (pip install redis)'
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _check_celery_task() -> tuple[bool, str]:
        try:
            from intelligence.tasks import ping_celery

            result = ping_celery.delay()
            payload = result.get(timeout=15)
            return True, f'task_id={result.id}, response={payload}'
        except Exception as exc:
            return False, str(exc)
