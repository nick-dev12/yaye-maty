"""
Configuration Celery — tâches asynchrones YAYEMATY MARKET (VPS).

Sous Windows (dev local), le worker doit utiliser le pool ``solo`` :
``celery -A yayematy_project worker -l info -P solo``
Le pool prefork provoque PermissionError (billiard / multiprocessing).
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')

app = Celery('yayematy')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
