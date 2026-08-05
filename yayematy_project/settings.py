"""
Django settings for yayematy_project project.

Architecture MVC adaptée à Django (MTV) :
- models/       → couche données (par app)
- controllers/  → logique métier
- views.py      → points d'entrée HTTP fins
- templates/    → présentation
- middlewares/  → traitement transversal des requêtes
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

SECRET_KEY = os.getenv(
    'SECRET_KEY',
    'django-insecure-()nerb)_@=ujl+eib@o!3*x-jje)(%086nl2i^6irjd7&tr2_5',
)

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Apps métier YAYEMATY MARKET
    'shop',
    'intelligence',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'yayematy_project.middlewares.security_headers_middleware.SecurityHeadersMiddleware',
]

ROOT_URLCONF = 'yayematy_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'yayematy_project.wsgi.application'


# Database — PostgreSQL via variables d'environnement
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'yayematy_db'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        # Même base pour les tests — pas de test_colobanes_yaye (voir test_runner.py)
        'TEST': {
            'NAME': os.getenv('DB_NAME', 'yayematy_db'),
        },
    }
}

# Tests sur la base .env (VPS) — sans CREATEDB ni seconde base
TEST_RUNNER = 'yayematy_project.test_runner.VpsExistingDatabaseTestRunner'


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'fr-fr'

TIME_ZONE = 'Africa/Dakar'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentification
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', '3600'))

# E-mail SMTP (cPanel — mail.yayematy.com, port 465 SSL)
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'yayematy_project.email_backend.EmailBackend',
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'mail.yayematy.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '465'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'service@yayematy.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'True').lower() in ('true', '1', 'yes')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() in ('true', '1', 'yes')
EMAIL_SSL_INSECURE = os.getenv('EMAIL_SSL_INSECURE', 'True').lower() in ('true', '1', 'yes')
DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL',
    'YAYEMATY MARKET <service@yayematy.com>',
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Liens dans les e-mails de réinitialisation (prod : https + analyse.yayematy.com)
EMAIL_RESET_DOMAIN = os.getenv(
    'EMAIL_RESET_DOMAIN',
    ALLOWED_HOSTS[0] if ALLOWED_HOSTS else '127.0.0.1:8000',
)
EMAIL_RESET_USE_HTTPS = os.getenv(
    'EMAIL_RESET_USE_HTTPS',
    'False' if DEBUG else 'True',
).lower() in ('true', '1', 'yes')

# Scraping réseaux sociaux (Playwright Stealth — VPS)
SOCIAL_SCRAPER = {
    'SESSIONS_DIR': BASE_DIR / 'data' / 'scraper_sessions',
    'HEADLESS': os.getenv('SOCIAL_SCRAPER_HEADLESS', 'False').lower() in ('true', '1', 'yes'),
    'VIEWPORT': {'width': 1920, 'height': 1080},
    'USER_AGENT': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'LOCALE': 'fr-FR',
    'TIMEZONE': 'Africa/Dakar',
    # Proxy résidentiel Sénégal (optionnel) — ex: http://user:pass@host:port
    'PROXY_SERVER': os.getenv('SOCIAL_SCRAPER_PROXY', ''),
}

# Clé API (legacy — machine locale, optionnel si Celery NLP actif)
INTELLIGENCE_API_KEY = os.getenv('INTELLIGENCE_API_KEY', '')

from celery.schedules import crontab

# Celery + Redis — tâches asynchrones VPS (scraping, NLP CamemBERT)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Windows : le pool prefork (multiprocessing) provoque PermissionError / WinError 5.
# En dev local, utiliser solo (1 tâche à la fois — adapté à Playwright).
if sys.platform == 'win32':
    CELERY_WORKER_POOL = os.getenv('CELERY_WORKER_POOL', 'solo')
    CELERY_WORKER_CONCURRENCY = int(os.getenv('CELERY_WORKER_CONCURRENCY', '1'))
else:
    CELERY_WORKER_POOL = os.getenv('CELERY_WORKER_POOL', 'prefork')
    CELERY_WORKER_CONCURRENCY = int(os.getenv('CELERY_WORKER_CONCURRENCY', '4'))

# Lancement worker/beat depuis l'UI Collecte — dev local uniquement (jamais en prod VPS).
CELERY_UI_LAUNCH = os.getenv(
    'CELERY_UI_LAUNCH',
    'True' if DEBUG and sys.platform == 'win32' else 'False',
).lower() in ('true', '1', 'yes')

# Planification collecte — Google Trends (macro) + réseaux sociaux (micro) + Jumia
# CAMPAIGN_DURATION_DAYS=3 + CAMPAIGN_START=YYYY-MM-DD → fenêtre de 3 jours consécutifs
COLLECTION_SCHEDULE = {
    'ENABLED': os.getenv('COLLECTION_ENABLED', 'True').lower() in ('true', '1', 'yes'),
    'CAMPAIGN_START': os.getenv('COLLECTION_CAMPAIGN_START', ''),
    'CAMPAIGN_DURATION_DAYS': int(os.getenv('COLLECTION_CAMPAIGN_DAYS', '3')),
    'GOOGLE_SEED_DELAY_MIN': float(os.getenv('COLLECTION_GOOGLE_SEED_MIN', '20')),
    'GOOGLE_SEED_DELAY_MAX': float(os.getenv('COLLECTION_GOOGLE_SEED_MAX', '55')),
    'GOOGLE_DOMAIN_DELAY_MIN': float(os.getenv('COLLECTION_GOOGLE_DOMAIN_MIN', '45')),
    'GOOGLE_DOMAIN_DELAY_MAX': float(os.getenv('COLLECTION_GOOGLE_DOMAIN_MAX', '120')),
    'SOCIAL_VIDEO_DELAY_MIN': float(os.getenv('COLLECTION_SOCIAL_VIDEO_MIN', '12')),
    'SOCIAL_VIDEO_DELAY_MAX': float(os.getenv('COLLECTION_SOCIAL_VIDEO_MAX', '45')),
    'SOCIAL_KEYWORD_DELAY_MIN': float(os.getenv('COLLECTION_SOCIAL_KEYWORD_MIN', '30')),
    'SOCIAL_KEYWORD_DELAY_MAX': float(os.getenv('COLLECTION_SOCIAL_KEYWORD_MAX', '90')),
    'SOCIAL_TARGET_DELAY_MIN': float(os.getenv('COLLECTION_SOCIAL_TARGET_MIN', '25')),
    'SOCIAL_TARGET_DELAY_MAX': float(os.getenv('COLLECTION_SOCIAL_TARGET_MAX', '70')),
    'MAX_VIDEOS_PER_KEYWORD_SESSION': int(os.getenv('COLLECTION_MAX_VIDEOS_SESSION', '15')),
    'MAX_POSTS_PER_TARGET_SESSION': int(os.getenv('COLLECTION_MAX_POSTS_SESSION', '12')),
    'MAX_KEYWORDS_PER_SESSION': int(os.getenv('COLLECTION_MAX_KEYWORDS_SESSION', '0')),
    'MAX_TARGETS_PER_SESSION': int(os.getenv('COLLECTION_MAX_TARGETS_SESSION', '0')),
    'NLP_COMMENT_LIMIT': int(os.getenv('COLLECTION_NLP_COMMENTS', '150')),
    'NLP_POST_LIMIT': int(os.getenv('COLLECTION_NLP_POSTS', '75')),
    # Jumia — nb produits plafonné aussi par max_videos du mot-clé Paramètres
    'JUMIA_MAX_PRODUCTS_PER_KEYWORD': int(os.getenv('COLLECTION_JUMIA_MAX_PRODUCTS', '0')),
    'JUMIA_MAX_REVIEWS_PER_PRODUCT': int(os.getenv('COLLECTION_JUMIA_MAX_REVIEWS', '20')),
    'JUMIA_MAX_LISTING_PAGES': int(os.getenv('COLLECTION_JUMIA_MAX_PAGES', '3')),
    'JUMIA_DELAY_MIN': float(os.getenv('COLLECTION_JUMIA_DELAY_MIN', '1.5')),
    'JUMIA_DELAY_MAX': float(os.getenv('COLLECTION_JUMIA_DELAY_MAX', '3.5')),
    'JUMIA_USE_PLAYWRIGHT': os.getenv('COLLECTION_JUMIA_PLAYWRIGHT', 'True').lower() in ('true', '1', 'yes'),
    'JUMIA_SKIP_KNOWN_PRODUCTS': os.getenv('COLLECTION_JUMIA_SKIP_KNOWN', 'True').lower() in ('true', '1', 'yes'),
    'JUMIA_MAX_LISTING_SCAN_PAGES': int(os.getenv('COLLECTION_JUMIA_MAX_SCAN_PAGES', '9')),
    'JUMIA_HOMEPAGE_RADAR_ENABLED': os.getenv('COLLECTION_JUMIA_HOMEPAGE', 'True').lower() in ('true', '1', 'yes'),
    'JUMIA_HOMEPAGE_MAX_PRODUCTS_PER_KEYWORD': int(os.getenv('COLLECTION_JUMIA_HOMEPAGE_MAX', '3')),
    # Jiji — nb annonces = max_videos du mot-clé Paramètres
    'JIJI_MAX_LISTINGS_PER_KEYWORD': int(os.getenv('COLLECTION_JIJI_MAX_LISTINGS', '0')),
    'JIJI_DELAY_MIN': float(os.getenv('COLLECTION_JIJI_DELAY_MIN', '1.5')),
    'JIJI_DELAY_MAX': float(os.getenv('COLLECTION_JIJI_DELAY_MAX', '3.5')),
    'JIJI_USE_PLAYWRIGHT': os.getenv('COLLECTION_JIJI_PLAYWRIGHT', 'True').lower() in ('true', '1', 'yes'),
    'JIJI_REVEAL_CONTACTS': os.getenv('COLLECTION_JIJI_REVEAL_CONTACTS', 'False').lower() in ('true', '1', 'yes'),
    'JIJI_SKIP_KNOWN_LISTINGS': os.getenv('COLLECTION_JIJI_SKIP_KNOWN', 'True').lower() in ('true', '1', 'yes'),
    'JIJI_SEARCH_FIRST': os.getenv('COLLECTION_JIJI_SEARCH_FIRST', 'True').lower() in ('true', '1', 'yes'),
    'JIJI_HOMEPAGE_RADAR_ENABLED': os.getenv('COLLECTION_JIJI_HOMEPAGE', 'True').lower() in ('true', '1', 'yes'),
    'JIJI_HOMEPAGE_MAX_LISTINGS_PER_KEYWORD': int(os.getenv('COLLECTION_JIJI_HOMEPAGE_MAX', '3')),
}

# Fenêtre « flux actuel » du tableau de bord Intelligence (jours affichés)
# Si COLLECTION_CAMPAIGN_DAYS > 0, cette valeur est ignorée au profit de la campagne.
INTELLIGENCE_LIVE_WINDOW_DAYS = int(os.getenv('INTELLIGENCE_LIVE_WINDOW_DAYS', '3'))

# Planification Celery Beat — vide si COLLECTION_ENABLED=False (collectes 100 % manuelles)
_COLLECTION_BEAT_SCHEDULE = {
    'google-trends-daily': {
        'task': 'intelligence.scraper_google_trends',
        'schedule': crontab(hour=3, minute=0),
    },
    'jiji-marketplace-routine': {
        'task': 'intelligence.scraper_jiji',
        'schedule': crontab(hour='6,12,18', minute=45),
    },
    'jumia-marketplace-routine': {
        'task': 'intelligence.scraper_jumia',
        'schedule': crontab(hour='7,13,19', minute=30),
    },
    'social-media-routine': {
        'task': 'intelligence.scraper_reseaux_sociaux',
        'schedule': crontab(hour='8,14,20', minute=15),
    },
    'analyse-hybride-routine': {
        'task': 'intelligence.analyser_donnees_non_traitees',
        'schedule': crontab(hour='9,15,21', minute=0),
    },
    'generate-top-purchase-recommendations-daily': {
        'task': 'intelligence.generate_top_purchase_recommendations',
        'schedule': crontab(hour=4, minute=30),
        'kwargs': {'window_days': 7},
    },
    'generate-import-opportunities-daily': {
        'task': 'intelligence.generate_import_opportunities',
        'schedule': crontab(hour=5, minute=15),
        'kwargs': {'window_days': 7},
    },
}

CELERY_BEAT_SCHEDULE = (
    _COLLECTION_BEAT_SCHEDULE
    if COLLECTION_SCHEDULE['ENABLED']
    else {}
)

# NLP CamemBERT zero-shot — VPS si NLP_CLASSIFIER_ENABLED=True, sinon lexical seul
NLP_CLASSIFIER = {
    'ENABLED': os.getenv('NLP_CLASSIFIER_ENABLED', 'True').lower() in ('true', '1', 'yes'),
    'MODEL_NAME': os.getenv('NLP_MODEL_NAME', 'cmarkea/distilcamembert-base-nli'),
    'CONFIDENCE_THRESHOLD': float(os.getenv('NLP_CONFIDENCE_THRESHOLD', '0.55')),
}

def _csv_env_list(name: str, default: str = '') -> list[str]:
    """Liste CSV depuis .env — domaines, tags, etc."""
    raw = os.getenv(name, default) or ''
    return [part.strip() for part in raw.split(',') if part.strip()]


def _env_marketplace_source(name: str, *, legacy_catalog_first: bool | None = None) -> str:
    """
    Mode collecte marketplace Trade Intelligence.

    - ``catalog`` / ``database`` / ``db`` / ``bdd`` → base de données
    - ``live`` / ``scrape`` / ``web`` → scraping HTTP normal
    """
    raw = (os.getenv(name, '') or '').strip().lower()
    if raw in ('catalog', 'database', 'db', 'bdd'):
        return 'catalog'
    if raw in ('live', 'scrape', 'scraping', 'web'):
        return 'live'
    if legacy_catalog_first is not None:
        return 'catalog' if legacy_catalog_first else 'live'
    return 'live'


_jumia_legacy_catalog = os.getenv(
    'TRADE_RESEARCH_JUMIA_USE_CATALOG_FIRST', '1',
).strip().lower() in ('1', 'true', 'yes', 'on')

# DeepSeek — Trade Intelligence (analyse marché + recherche web)
DEEPSEEK = {
    'API_KEY': os.getenv('DEEPSEEK_API_KEY', ''),
    'MODEL': os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-flash'),
    'BASE_URL': os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
    'ANTHROPIC_BASE_URL': os.getenv(
        'DEEPSEEK_ANTHROPIC_BASE_URL',
        'https://api.deepseek.com/anthropic',
    ),
    'ENABLED': os.getenv('DEEPSEEK_ANALYSIS_ENABLED', 'True').lower() in ('true', '1', 'yes'),
    'THINKING_ENABLED': os.getenv('DEEPSEEK_THINKING_ENABLED', 'False').lower() in (
        'true', '1', 'yes',
    ),
    # Import Master : réflexion DeepSeek activée par défaut (prix / marges / cohérence)
    'IMPORT_MASTER_THINKING_ENABLED': os.getenv(
        'DEEPSEEK_IMPORT_MASTER_THINKING_ENABLED', 'True',
    ).lower() in ('true', '1', 'yes'),
    'MAX_TOKENS': int(os.getenv('DEEPSEEK_MAX_TOKENS', '8192')),
    'TIMEOUT_SECONDS': float(os.getenv('DEEPSEEK_TIMEOUT_SECONDS', '120')),
    # Veille web Trade Intelligence — marché SN uniquement
    # (Alibaba / AliExpress / Amazon / Made-in-China = Import Master seulement)
    'WEB_ALLOWED_DOMAINS': _csv_env_list(
        'DEEPSEEK_WEB_ALLOWED_DOMAINS',
        'jumia.sn,jiji.sn,promo.sn,expat-dakar.com,sn.coinafrique.com,'
        'jemba.sn,dakarcenter.com,occasiondakar.com,taftaf.sn,'
        'facebook.com,instagram.com,tiktok.com',
    ),
    # True = web ouvert + sites prioritaires en consigne ; False = allowed_domains strict API
    'WEB_OPEN_SEARCH': os.getenv('DEEPSEEK_WEB_OPEN_SEARCH', 'True').lower() in (
        'true', '1', 'yes', 'on',
    ),
    # Exclusions (strict mode ou complément open — jamais avec allowed_domains API)
    'WEB_BLOCKED_DOMAINS': _csv_env_list('DEEPSEEK_WEB_BLOCKED_DOMAINS', ''),
    'WEB_MAX_USES': int(os.getenv('DEEPSEEK_WEB_MAX_USES', '5')),
    'WEB_COUNTRY': os.getenv('DEEPSEEK_WEB_COUNTRY', 'SN'),
    'WEB_CITY': os.getenv('DEEPSEEK_WEB_CITY', 'Dakar'),
    'WEB_TIMEZONE': os.getenv('DEEPSEEK_WEB_TIMEZONE', 'Africa/Dakar'),
    # Veille web — limites caractères (deepseek-v4-flash)
    'WEB_CHUNK_MAX_CHARS': int(os.getenv('DEEPSEEK_WEB_CHUNK_MAX_CHARS', '12000')),
    'WEB_STORED_CONTEXT_MAX_CHARS': int(
        os.getenv('DEEPSEEK_WEB_STORED_CONTEXT_MAX_CHARS', '12000'),
    ),
    'ANALYSIS_PAYLOAD_MAX_CHARS': int(
        os.getenv('DEEPSEEK_ANALYSIS_PAYLOAD_MAX_CHARS', '12000'),
    ),
    'ANALYSIS_WEB_CONTEXT_MAX_CHARS': int(
        os.getenv('DEEPSEEK_ANALYSIS_WEB_CONTEXT_MAX_CHARS', '12000'),
    ),
    # Tours veille web — nombre fixe par session (DEEPSEEK_WEB_MAX_TOURS dans .env)
    'WEB_MAX_TOURS': max(1, int(os.getenv('DEEPSEEK_WEB_MAX_TOURS', '3'))),
}

# Trade Intelligence — limites collecte ad-hoc par session
# Trade Intelligence — 0 = illimité (seule la durée borne la collecte)
TRADE_RESEARCH = {
    'MAX_PRODUCTS': int(os.getenv('TRADE_RESEARCH_MAX_PRODUCTS', '0')),
    'MAX_LISTINGS': int(os.getenv('TRADE_RESEARCH_MAX_LISTINGS', '0')),
    'MAX_SOCIAL_POSTS': int(os.getenv('TRADE_RESEARCH_MAX_SOCIAL', '0')),
    'MAX_REVIEWS': int(os.getenv('TRADE_RESEARCH_MAX_REVIEWS', '20')),
    # Catalogue Jumia pré-crawlé (local) → analyse TI
    'JUMIA_CATALOG_PRODUCTS_PER_TOUR': int(
        os.getenv('TRADE_RESEARCH_JUMIA_CATALOG_PRODUCTS_PER_TOUR', '100')
    ),
    'JUMIA_CATALOG_MAX_TOURS': int(
        os.getenv('TRADE_RESEARCH_JUMIA_CATALOG_MAX_TOURS', '3')
    ),
    # catalog = BDD JumiaProduct | live = scrape HTTP (legacy : JUMIA_USE_CATALOG_FIRST)
    'JUMIA_SOURCE': _env_marketplace_source(
        'TRADE_RESEARCH_JUMIA_SOURCE',
        legacy_catalog_first=_jumia_legacy_catalog,
    ),
    'JUMIA_CATALOG_FALLBACK_LIVE': os.getenv(
        'TRADE_RESEARCH_JUMIA_CATALOG_FALLBACK_LIVE', '0',
    ).strip().lower() in ('1', 'true', 'yes', 'on'),
    'JUMIA_USE_CATALOG_FIRST': _jumia_legacy_catalog,
    # Jiji : database = JijiListing en BDD | live = scrape HTTP
    'JIJI_SOURCE': _env_marketplace_source('TRADE_RESEARCH_JIJI_SOURCE'),
    'JIJI_DATABASE_LISTINGS_PER_TOUR': int(
        os.getenv('TRADE_RESEARCH_JIJI_DATABASE_LISTINGS_PER_TOUR', '100')
    ),
    'JIJI_DATABASE_MAX_TOURS': int(
        os.getenv('TRADE_RESEARCH_JIJI_DATABASE_MAX_TOURS', '3')
    ),
    'JIJI_DATABASE_FALLBACK_LIVE': os.getenv(
        'TRADE_RESEARCH_JIJI_DATABASE_FALLBACK_LIVE', '0',
    ).strip().lower() in ('1', 'true', 'yes', 'on'),
}

# Production derrière Nginx + HTTPS (voir DEPLOYMENT.md)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
