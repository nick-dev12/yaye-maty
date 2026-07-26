"""Test rapide du modèle NLP zero-shot."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yayematy_project.settings')

import django
django.setup()

from django.conf import settings
from intelligence.services.camembert_classifier_service import CamembertClassifierService
from intelligence.services.local_keyword_filter import LocalKeywordFilter

print('NLP enabled:', settings.NLP_CLASSIFIER['ENABLED'])
print('Model:', settings.NLP_CLASSIFIER['MODEL_NAME'])

w = LocalKeywordFilter.classify('Naata la pompe bi ?')
print('Wolof filter:', w)

r = CamembertClassifierService.classify_comment_intent(
    'Est-ce que vous livrez a Saint-Louis ?'
)
print('CamemBERT:', r)
