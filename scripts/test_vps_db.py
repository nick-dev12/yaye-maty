"""Test connexion Django -> PostgreSQL VPS."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yayematy_project.settings")
django.setup()

from django.db import connection

with connection.cursor() as c:
    c.execute("SELECT current_database(), current_user")
    db, user = c.fetchone()

print("OK - base=%s, user=%s" % (db, user))
