# YAYEMATY MARKET

Plateforme d'intelligence de marché et marketplace généraliste au Sénégal.

## Stack

- **Backend** : Django 5.2, PostgreSQL, Celery, Redis
- **Collecte** : Playwright (Jumia, Jiji, réseaux sociaux), pytrends (Google Trends)
- **Frontend admin** : Templates Django (HTML/CSS/JS)

## Installation locale

```bash
python -m venv venv
source venv/bin/activate   # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # puis éditer .env
python manage.py migrate
python manage.py runserver
```

## Celery (Linux / VPS)

```bash
celery -A yayematy_project worker -l info
celery -A yayematy_project beat -l info
```

## Périmètre de veille

Les mots-clés actifs configurés dans **Paramètres** définissent toute la collecte et l'analyse (Jumia, Jiji, réseaux, Google Trends).
