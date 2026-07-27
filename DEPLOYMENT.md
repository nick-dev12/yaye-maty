# Guide de déploiement — YAYEMATY MARKET (Django + Webuzo)

Guide complet pour déployer **YAYEMATY MARKET** sur un VPS **Ubuntu 24.04** avec le panneau **Webuzo**, **Nginx**, **Gunicorn**, **PostgreSQL**, **Redis**, **Celery** et **NLP CamemBERT** (chaîne autonome sur le VPS).

> **Environnement de référence** (déploiement validé — juillet 2026)  
> - VPS : Contabo **Cloud VPS 8** — 8 vCPU, 24 Go RAM, 300 Go SSD  
> - IP : `173.249.41.61`  
> - Domaine : `analyse.yayematy.com`  
> - Utilisateur Webuzo : `colobanes`  
> - Dossier projet : `/home/colobanes/analyse.yayematy.com`  
> - Dépôt Git : `https://github.com/nick-dev12/yaye-maty`  
> - Python système : **3.12.3** (venv du projet, pas Python 3.14 Webuzo)

---

## Table des matières

1. [Architecture](#1-architecture)
2. [Prérequis](#2-prérequis)
3. [Phase 1 — Préparer le VPS (Webuzo)](#3-phase-1--préparer-le-vps-webuzo)
4. [Phase 2 — Domaine et DNS](#4-phase-2--domaine-et-dns)
5. [Phase 3 — PostgreSQL](#5-phase-3--postgresql)
6. [Phase 4 — Cloner le projet](#6-phase-4--cloner-le-projet)
7. [Phase 5 — Python, venv et dépendances](#7-phase-5--python-venv-et-dépendances)
8. [Phase 6 — Fichier .env production](#8-phase-6--fichier-env-production)
9. [Phase 7 — Django (migrate, static, superuser)](#9-phase-7--django-migrate-static-superuser)
10. [Phase 8 — Gunicorn (systemd)](#10-phase-8--gunicorn-systemd)
11. [Phase 9 — Nginx + Webuzo (étape critique)](#11-phase-9--nginx--webuzo-étape-critique)
12. [Phase 10 — Celery Worker + Beat](#12-phase-10--celery-worker--beat)
13. [Phase 11 — Playwright (scraping)](#13-phase-11--playwright-scraping)
14. [Phase 12 — NLP CamemBERT sur le VPS](#14-phase-12--nlp-camembert-sur-le-vps)
15. [Phase 13 — Sessions réseaux sociaux (TikTok / Facebook)](#15-phase-13--sessions-réseaux-sociaux-tiktok--facebook)
16. [Phase 14 — Campagne de collecte](#16-phase-14--campagne-de-collecte)
17. [Phase 15 — Tests et vérifications complètes](#17-phase-15--tests-et-vérifications-complètes)
18. [Mises à jour du code](#18-mises-à-jour-du-code) — voir aussi **[README-DEPLOIEMENT.md](README-DEPLOIEMENT.md)** (guide rapide)
19. [Dépannage](#19-dépannage)
20. [Fichiers prêts à l'emploi dans le dépôt](#20-fichiers-prêts-à-lemploi-dans-le-dépôt)

---

## 1. Architecture

### Stack production

```
Internet
   │
   ▼
Nginx (443 HTTPS) — analyse.yayematy.com
   ├── /static/  →  /home/colobanes/analyse.yayematy.com/staticfiles/
   └── /         →  Gunicorn (socket Unix) → Django (WSGI)
                           │
            ┌──────────────┼──────────────────────────┐
            ▼              ▼                          ▼
      PostgreSQL        Redis              Celery Worker + Beat
                                                    │
                    ┌───────────────────────────────┼───────────────────────────────┐
                    ▼                               ▼                               ▼
            Playwright (Jumia, Jiji,          NLP hybride                    Google Trends
            TikTok, Facebook)                 (keyword + CamemBERT)            (pytrends)
```

**Important :** Django ne passe **jamais** par Apache/PHP. Apache reste pour les autres domaines PHP (`colobanes.com`). Pour `analyse.yayematy.com`, Nginx proxy directement vers **Gunicorn**.

### Chaîne de collecte automatique (Celery Beat)

Toute la chaîne tourne **sur le VPS** — le PC local n'est **pas requis** en production.

| Horaire (serveur) | Tâche Celery | Rôle |
|-------------------|--------------|------|
| 03:00 | `intelligence.scraper_google_trends` | Tendances Google (mots-clés Paramètres) |
| 04:30 | `intelligence.generate_top_purchase_recommendations` | Top recommandations achat (7 jours) |
| 06:45, 12:45, 18:45 | `intelligence.scraper_jiji` | Marketplace Jiji |
| 07:30, 13:30, 19:30 | `intelligence.scraper_jumia` | Marketplace Jumia |
| 08:15, 14:15, 20:15 | `intelligence.scraper_reseaux_sociaux` | TikTok + Facebook |
| 09:00, 15:00, 21:00 | `intelligence.analyser_donnees_non_traitees` | **NLP hybride** (sync + keyword + CamemBERT) |

**Collecte manuelle** (interface `/intelligence/collecte/`) : après Social / Google / mot-clé, le NLP s'enchaîne automatiquement si configuré.

### Pipeline NLP hybride

```
Commentaires / posts non traités
        │
        ▼
  Sync JSON → SocialComment (depuis posts scrapés)
        │
        ▼
  Filtre mots-clés / wolof (rapide, sans GPU)
        │
        ▼ (si non résolu)
  CamemBERT zero-shot (~500 Mo RAM / worker)
        │
        ▼
  Backfill produits + Top recommandations
```

Modèle par défaut : `cmarkea/distilcamembert-base-nli` (~272 Mo, téléchargé une fois au premier usage).

### PC local (`local_nlp/`) — optionnel

Le dossier `local_nlp/` sert au **développement** ou en **secours**. En production VPS avec `NLP_CLASSIFIER_ENABLED=True`, **ne pas** lancer `python -m local_nlp.runner` sur le PC.

---

## 2. Prérequis

### Sur le VPS (via Webuzo → Applications)

| Composant | Version testée | Rôle |
|-----------|----------------|------|
| **Ubuntu** | 24.04 | OS |
| **Webuzo** | 4.7.x | Panneau |
| **Python 3** | 3.12+ (système) | Runtime |
| **PostgreSQL** | 15 | Base de données |
| **Redis** | 8.x | Broker Celery |
| **Nginx** | (Webuzo) | Reverse proxy front |
| **Apache** | (Webuzo) | PHP uniquement (autres sites) |

**RAM recommandée :** minimum 8 Go ; **24 Go** (Cloud VPS 8) confortable pour scraping Playwright + CamemBERT en parallèle (`--concurrency=2`).

### Paquets système (SSH root)

```bash
apt update && apt upgrade -y
apt install -y git build-essential libpq-dev python3-venv python3-dev python3.12-venv
```

> **Note Ubuntu :** la commande `python` n'existe pas par défaut. Utilisez toujours le venv du projet :
> `source /home/colobanes/analyse.yayematy.com/venv/bin/activate` puis `python manage.py ...`

### Accès

- SSH root : `ssh root@173.249.41.61`
- Panneau Webuzo utilisateur : `https://173.249.41.61:2003`
- Panneau Webuzo admin : `https://173.249.41.61:2005`
- Site public : **https://analyse.yayematy.com**

### Activer le shell pour l'utilisateur Webuzo

Webuzo crée souvent l'utilisateur avec shell `nologin` :

```bash
usermod -s /bin/bash colobanes
su - colobanes   # test
```

Alternative sans session interactive :

```bash
su -s /bin/bash colobanes -c "whoami"
```

---

## 3. Phase 1 — Préparer le VPS (Webuzo)

1. Connectez-vous au panneau **Webuzo admin** (port 2005).
2. **Applications** → installez dans cet ordre si absent :
   - Python 3
   - PostgreSQL (PGSQL 15)
   - Redis
   - Nginx
   - Apache (déjà présent pour PHP)
3. **Services** → vérifiez que **Nginx**, **PostgreSQL** et **Redis** sont **actifs**.

Test Redis :

```bash
redis-cli ping
# → PONG
```

---

## 4. Phase 2 — Domaine et DNS

### Chez le registrar (ex. Namecheap)

Créez un enregistrement **A** :

| Type | Host | Value |
|------|------|-------|
| A | `analyse` | `173.249.41.61` |

Résultat : `analyse.yayematy.com` → votre VPS.

### Dans Webuzo (utilisateur colobanes)

1. **Domaines** → **Ajouter un domaine**
2. Domaine addon : `analyse.yayematy.com`
3. Chemin document : `/home/colobanes/analyse.yayematy.com`
4. **Forcer HTTPS** : ON
5. **SSL** → Let's Encrypt pour `analyse.yayematy.com`

---

## 5. Phase 3 — PostgreSQL

### Via Webuzo (recommandé)

1. **Base de données** → **PostgreSQL**
2. Créez une **base** : ex. `colobanes_yaye`
3. Créez un **utilisateur** : ex. `colobanes_jomas`
4. **Associez** l'utilisateur à la base avec tous les privilèges
5. Notez le **mot de passe**

> **Chemins config Webuzo (≠ installation apt)**  
> Webuzo installe PostgreSQL sous `/usr/local/apps/postgresql*/` — pas sous `/etc/postgresql/`.  
> Pour trouver les vrais fichiers sur le VPS :
> ```bash
> sudo bash /home/colobanes/analyse.yayematy.com/deploy/find-postgres-config.sh
> ```
> Fichiers à modifier manuellement si besoin :
> - `postgresql.conf` → `listen_addresses = '*'`
> - `pg_hba.conf` → ligne `host colobanes_yaye colobanes_jomas 0.0.0.0/0 scram-sha-256`
>
> Ou automatique (toutes les IP) :
> ```bash
> sudo bash deploy/configure-postgres-remote.sh all
> ```
> Puis redémarrer PostgreSQL dans **Webuzo → Admin → Services → PostgreSQL**.

### Test connexion

```bash
PGPASSWORD='VOTRE_MOT_DE_PASSE' psql -h 127.0.0.1 -U colobanes_jomas -d colobanes_yaye -c "SELECT 1;"
```

> **Erreur `Ident authentication failed` ?**  
> Utilisez `DB_HOST=127.0.0.1` dans `.env` (pas `localhost`).  
> Si ça persiste, modifiez `pg_hba.conf` : remplacez `ident`/`peer` par `scram-sha-256`, puis `systemctl reload postgresql`.

---

## 6. Phase 4 — Cloner le projet

### Option A — Git en SSH (root ou colobanes)

```bash
mkdir -p /home/colobanes/analyse.yayematy.com
cd /home/colobanes/analyse.yayematy.com
git clone https://github.com/nick-dev12/yaye-maty.git .
```

### Option B — Git Webuzo

**Utilitaires serveur** → **Git™ Version Control** → Clone URL → chemin `/home/colobanes/analyse.yayematy.com`

### Permissions (obligatoire si clone en root)

```bash
chown -R colobanes:colobanes /home/colobanes/analyse.yayematy.com
chmod 755 /home/colobanes /home/colobanes/analyse.yayematy.com
```

> **Règle :** tout dans `/home/colobanes/` doit appartenir à `colobanes:colobanes` pour le gestionnaire de fichiers Webuzo.

---

## 7. Phase 5 — Python, venv et dépendances

```bash
cd /home/colobanes/analyse.yayematy.com
python3 --version          # ex. Python 3.12.3

rm -rf venv                # si ancien venv cassé
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

Le fichier `requirements.txt` inclut **torch**, **transformers** et **sentencepiece** pour CamemBERT sur le VPS.

Si l'installation échoue (mémoire insuffisante pendant `pip install`) :

```bash
pip install Django psycopg2-binary celery redis python-dotenv \
  playwright playwright-stealth pytrends requests pandas lxml numpy gunicorn
pip install torch transformers sentencepiece --index-url https://download.pytorch.org/whl/cpu
```

---

## 8. Phase 6 — Fichier .env production

```bash
cp .env.production.example .env
nano .env
```

Générer `SECRET_KEY` :

```bash
source venv/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Générer `INTELLIGENCE_API_KEY` (API REST optionnelle) :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Exemple `.env` production (chaîne complète sur VPS)

```env
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=analyse.yayematy.com,173.249.41.61,localhost,127.0.0.1

DB_NAME=colobanes_yaye
DB_USER=colobanes_jomas
DB_PASSWORD=...
DB_HOST=127.0.0.1
DB_PORT=5432

CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

SOCIAL_SCRAPER_HEADLESS=True
CELERY_UI_LAUNCH=False

# NLP sur VPS — OBLIGATOIRE pour chaîne autonome
NLP_CLASSIFIER_ENABLED=True
NLP_MODEL_NAME=cmarkea/distilcamembert-base-nli
NLP_CONFIDENCE_THRESHOLD=0.55

COLLECTION_NLP_COMMENTS=200
COLLECTION_NLP_POSTS=100

INTELLIGENCE_API_KEY=...

COLLECTION_ENABLED=True
COLLECTION_CAMPAIGN_START=2026-07-27
COLLECTION_CAMPAIGN_DAYS=3
COLLECTION_MAX_VIDEOS_SESSION=15
```

Sécuriser :

```bash
chmod 600 .env
chown colobanes:colobanes .env
```

> **Ne jamais** commiter le fichier `.env` (secrets). Modèle complet : `.env.production.example`.

---

## 9. Phase 7 — Django (migrate, static, superuser)

Le projet inclut déjà `STATIC_ROOT` et les réglages HTTPS production dans `settings.py`.

```bash
source venv/bin/activate
cd /home/colobanes/analyse.yayematy.com

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py check --deploy
```

Test Gunicorn manuel :

```bash
gunicorn --bind 127.0.0.1:8001 yayematy_project.wsgi:application
# Ctrl+C pour arrêter si OK
```

---

## 10. Phase 8 — Gunicorn (systemd)

Copier le service depuis le dépôt :

```bash
cp /home/colobanes/analyse.yayematy.com/deploy/systemd/gunicorn-yayematy.service \
   /etc/systemd/system/gunicorn-yayematy.service
```

Contenu de référence :

```ini
[Unit]
Description=Gunicorn YAYEMATY
After=network.target postgresql.service redis.service

[Service]
User=colobanes
Group=colobanes
WorkingDirectory=/home/colobanes/analyse.yayematy.com
Environment="PATH=/home/colobanes/analyse.yayematy.com/venv/bin"
ExecStart=/home/colobanes/analyse.yayematy.com/venv/bin/gunicorn \
    --workers 2 \
    --bind unix:/home/colobanes/analyse.yayematy.com/gunicorn.sock \
    --timeout 120 \
    yayematy_project.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activer :

```bash
systemctl daemon-reload
systemctl enable gunicorn-yayematy
systemctl start gunicorn-yayematy
systemctl status gunicorn-yayematy
```

Test socket :

```bash
curl -I --unix-socket /home/colobanes/analyse.yayematy.com/gunicorn.sock http://localhost/
# → HTTP/1.1 200 OK  (Server: gunicorn)
```

---

## 11. Phase 9 — Nginx + Webuzo (étape critique)

### Comprendre la stack Webuzo

| Fichier / Port | Rôle |
|----------------|------|
| `/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf` | Config publique **80/443** |
| Port **443** | Site public `https://analyse.yayematy.com` |
| Port **2003** | Panneau Webuzo utilisateur (≠ site public) |
| `/var/webuzo-data/nginx/custom/domains/analyse.yayematy.com.conf` | Config custom par domaine |
| `$webuzoproxy` → Apache | PHP — **à remplacer par Gunicorn pour Django** |

### Étape 9.1 — Fichier custom (static + sécurité)

```bash
mkdir -p /var/webuzo-data/nginx/custom/domains
nano /var/webuzo-data/nginx/custom/domains/analyse.yayematy.com.conf
```

Contenu (copier depuis `deploy/nginx/analyse.yayematy.com.conf`) :

```nginx
location ^~ /static/ {
    alias /home/colobanes/analyse.yayematy.com/staticfiles/;
    expires 30d;
    access_log off;
}

location ~ /\.git {
    deny all;
}
```

> ⚠ **NE PAS** mettre `location /` ici — cela crée un doublon avec `webuzoVH.conf` et empêche Nginx de recharger :
> `duplicate location "/" in analyse.yayematy.com.conf`

### Étape 9.2 — Modifier webuzoVH.conf (Gunicorn)

**Sauvegarde obligatoire** (Webuzo régénère ce fichier) :

```bash
cp /usr/local/apps/nginx/etc/conf.d/webuzoVH.conf \
   /usr/local/apps/nginx/etc/conf.d/webuzoVH.conf.bak
```

Éditer :

```bash
nano /usr/local/apps/nginx/etc/conf.d/webuzoVH.conf
```

Trouvez les **2 blocs** `server { ... server_name analyse.yayematy.com ... }` :
- un sur le port **80**
- un sur le port **443 ssl**

Dans **chaque** bloc, remplacez le `location / { ... proxy_pass $webuzoproxy; ... }` par :

```nginx
    location / {
        proxy_pass http://unix:/home/colobanes/analyse.yayematy.com/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
```

(Snippet aussi dans `deploy/nginx/webuzoVH-location-gunicorn.conf`.)

### Étape 9.3 — Recharger Nginx (Webuzo)

```bash
rm -rf /var/webuzo-data/nginx_proxy_cache/colobanes/*
/usr/local/apps/nginx/sbin/nginx -t
/usr/local/apps/nginx/sbin/nginx -s reload
```

> Sur Webuzo, utilisez `/usr/local/apps/nginx/sbin/nginx`, pas toujours `systemctl reload nginx`.

### Étape 9.4 — Tests

```bash
curl -I --unix-socket /home/colobanes/analyse.yayematy.com/gunicorn.sock http://localhost/
curl -Ik --resolve analyse.yayematy.com:443:173.249.41.61 https://analyse.yayematy.com/
```

Attendu : **HTTP 200** ou **302** (login Django), **pas 403**.

Navigateur : **https://analyse.yayematy.com**

### Schéma Nginx corrigé

```
AVANT (403 Forbidden) :
  HTTPS → Nginx → Apache ($webuzoproxy) → root du dossier → 403

APRÈS (OK) :
  HTTPS → Nginx → Gunicorn (socket) → Django
  /static/ → staticfiles/ (fichier custom)
```

---

## 12. Phase 10 — Celery Worker + Beat

```bash
cp deploy/systemd/celery-yayematy.service /etc/systemd/system/
cp deploy/systemd/celerybeat-yayematy.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable celery-yayematy celerybeat-yayematy
systemctl start celery-yayematy celerybeat-yayematy
systemctl status celery-yayematy celerybeat-yayematy
```

Le worker tourne sous **`colobanes`** avec **`--concurrency=2`** (scraping + NLP en parallèle).

Vérification :

```bash
source venv/bin/activate
celery -A yayematy_project inspect ping
# → pong

python manage.py check_infrastructure --celery-task
# [OK] PostgreSQL — Connexion OK
# [OK] Redis/Memurai — redis://127.0.0.1:6379/0
# [OK] Celery worker — task_id=..., response={'status': 'pong'}
```

### Consommation RAM estimée (Cloud VPS 8 — 24 Go)

| Composant | RAM approx. |
|-----------|-------------|
| Gunicorn (×2 workers) | ~200–400 Mo |
| Celery worker (×2 process) | ~400–800 Mo |
| CamemBERT (1 instance active) | ~500 Mo–1 Go |
| Playwright (scraping en cours) | ~300–600 Mo |
| PostgreSQL + Redis + OS | ~1–2 Go |
| **Total pic observé** | ~3–5 Go → marge confortable sur 24 Go |

Si RAM > 18 Go en pic, réduire `--concurrency=1` dans `celery-yayematy.service`.

---

## 13. Phase 11 — Playwright (scraping)

**Important :** installer Chromium pour l'utilisateur **`colobanes`** (Celery tourne sous cet utilisateur).

```bash
su -s /bin/bash colobanes -c "
cd /home/colobanes/analyse.yayematy.com
source venv/bin/activate
playwright install chromium
"
```

Dépendances système (root, une seule fois) :

```bash
source /home/colobanes/analyse.yayematy.com/venv/bin/activate
playwright install-deps chromium
```

Test :

```bash
su -s /bin/bash colobanes -c "
cd /home/colobanes/analyse.yayematy.com
source venv/bin/activate
python -c \"from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print('OK'); b.close(); p.stop()\"
"
# → OK
```

---

## 14. Phase 12 — NLP CamemBERT sur le VPS

### Activation

Dans `.env` :

```env
NLP_CLASSIFIER_ENABLED=True
NLP_MODEL_NAME=cmarkea/distilcamembert-base-nli
NLP_CONFIDENCE_THRESHOLD=0.55
COLLECTION_NLP_COMMENTS=200
COLLECTION_NLP_POSTS=100
```

Redémarrer Celery (obligatoire après changement `.env`) :

```bash
systemctl restart celery-yayematy celerybeat-yayematy
```

### Test 1 — Modèle CamemBERT isolé

```bash
cd /home/colobanes/analyse.yayematy.com
source venv/bin/activate
python scripts/test_camembert.py
```

**Sortie attendue (exemple validé) :**

```
NLP enabled: True
Model: cmarkea/distilcamembert-base-nli
Wolof filter: {'intent': ..., 'confidence': 0.92, 'method': 'keyword'}
CamemBERT: {'intent': ..., 'confidence': 0.46..., 'method': 'camembert', ...}
```

Au **premier lancement**, Hugging Face télécharge le modèle (~272 Mo). Message normal :

```
Warning: You are sending unauthenticated requests to the HF Hub...
```

Optionnel : ajouter `HF_TOKEN=...` dans `.env` pour accélérer les téléchargements.

### Test 2 — Pipeline NLP via Celery

```bash
celery -A yayematy_project call intelligence.analyser_donnees_non_traitees
```

Suivre les logs :

```bash
journalctl -u celery-yayematy -f
```

**Sortie attendue :**

```
Session NLP terminée : {
  'sync': {'created': 0, 'updated': 106, 'skipped': 0, 'posts': 7},
  'comments': {'keyword': 1, 'camembert': 0, 'skipped': 0, 'total': 1},
  'posts': {'keyword': 0, 'camembert': 0, 'updated': 0, 'skipped': 0},
  'top_recommendations': {'created': 7, 'deleted': 0, ...},
  'success': True, 'reason': 'Campagne jour 1/3.'
}
```

> **`camembert: 0` avec `keyword: 1` est normal** : le pipeline hybride traite d'abord par mots-clés/wolof ; CamemBERT ne s'applique qu'aux commentaires ambigus.

### Test 3 — Métriques NLP en base

```bash
python manage.py shell -c "
from intelligence.models import SocialComment, SocialPost
print('Commentaires non analysés:', SocialComment.objects.filter(is_analyzed=False).count())
print('Posts en attente:', SocialPost.objects.filter(analysis_status='pending').count())
print('Posts analysés:', SocialPost.objects.filter(analysis_status='done').count())
print('Commentaires keyword:', SocialComment.objects.filter(analysis_method='keyword').count())
print('Commentaires CamemBERT:', SocialComment.objects.filter(analysis_method='camembert').count())
"
```

**Exemple production validé :**

```
Commentaires non analysés: 0
Posts en attente: 0
Posts analysés: 14
Commentaires keyword: 30
Commentaires CamemBERT: 75
```

> **Attention aux champs modèle :** `SocialComment` utilise `is_analyzed` ; `SocialPost` utilise `analysis_status` (`pending`, `done`, etc.) — pas `is_analyzed`.

### Autres commandes NLP utiles

```bash
python manage.py analyze_social_nlp --limit 50
python manage.py generate_top_recommendations
```

---

## 15. Phase 13 — Sessions réseaux sociaux (TikTok / Facebook)

Les cookies Playwright sont stockés dans :

```
/home/colobanes/analyse.yayematy.com/data/scraper_sessions/
├── tiktok.json      ← requis pour TikTok
└── facebook.json    ← requis pour Facebook
```

Vérifier :

```bash
ls -la /home/colobanes/analyse.yayematy.com/data/scraper_sessions/
```

### TikTok — session existante

Si `tiktok.json` est présent (~190 Ko), TikTok est prêt. Vérifier :

```bash
source venv/bin/activate
python manage.py verify_social_session --platform tiktok
```

### Facebook — créer ou copier la session

**Option A — Copier depuis votre PC** (recommandé si déjà connecté localement) :

```bash
# Depuis votre PC Windows (PowerShell) :
scp "C:\chemin\vers\yaye-maty\data\scraper_sessions\facebook.json" \
  root@173.249.41.61:/home/colobanes/analyse.yayematy.com/data/scraper_sessions/

# Sur le VPS :
chown colobanes:colobanes /home/colobanes/analyse.yayematy.com/data/scraper_sessions/facebook.json
chmod 644 /home/colobanes/analyse.yayematy.com/data/scraper_sessions/facebook.json
```

**Option B — Créer sur le VPS** (navigateur visible requis — X11 forwarding ou bureau distant) :

```bash
source venv/bin/activate
# SOCIAL_SCRAPER_HEADLESS=False temporairement pour init
python manage.py init_social_session --platform facebook
chown colobanes:colobanes data/scraper_sessions/facebook.json
```

**Option C — Créer sur PC local, puis copier** :

```bash
# PC local
python manage.py init_social_session --platform facebook
# Puis scp vers VPS (Option A)
```

### Vérifier la session Facebook

```bash
source venv/bin/activate
python manage.py verify_social_session --platform facebook
```

Sans `facebook.json`, le scraping Facebook est **ignoré** ; TikTok et les marketplaces continuent normalement.

---

## 16. Phase 14 — Campagne de collecte

### Variables `.env`

```env
COLLECTION_ENABLED=True
COLLECTION_CAMPAIGN_START=2026-07-27    # Date début (YYYY-MM-DD)
COLLECTION_CAMPAIGN_DAYS=3              # Durée en jours
COLLECTION_MAX_VIDEOS_SESSION=15
```

Pendant la campagne, Celery Beat exécute les tâches planifiées. Hors fenêtre, les sessions sont **ignorées** avec un log du type :

```
Session NLP ignorée : Campagne terminée.
```

### Mots-clés (source de vérité)

Configurez les mots-clés actifs dans l'interface **Paramètres** (`MarketSearchKeyword`). Toute collecte (Jumia, Jiji, réseaux, Trends) se base **uniquement** sur ces mots-clés — pas sur un secteur prédéfini.

Vérifier en shell :

```bash
python manage.py shell -c "
from intelligence.models import MarketSearchKeyword
for p in ('social', 'jumia', 'jiji'):
    qs = MarketSearchKeyword.objects.filter(is_active=True, platform=p)
    print(f'{p}:', list(qs.values_list('keyword', flat=True)))
"
```

### Lancer une collecte manuelle (UI)

1. Connexion : https://analyse.yayematy.com
2. **Intelligence** → **Collecte** : `/intelligence/collecte/`
3. Test rapide : `/intelligence/collecte/test/`

### Lancer une tâche Celery manuellement

```bash
source venv/bin/activate

celery -A yayematy_project call intelligence.scraper_jiji
celery -A yayematy_project call intelligence.scraper_jumia
celery -A yayematy_project call intelligence.scraper_reseaux_sociaux
celery -A yayematy_project call intelligence.scraper_google_trends
celery -A yayematy_project call intelligence.analyser_donnees_non_traitees
celery -A yayematy_project call intelligence.generate_top_purchase_recommendations
```

---

## 17. Phase 15 — Tests et vérifications complètes

### Checklist post-déploiement

#### Infrastructure

- [ ] `redis-cli ping` → `PONG`
- [ ] `python manage.py check_infrastructure --celery-task` → 3× OK
- [ ] `systemctl status gunicorn-yayematy celery-yayematy celerybeat-yayematy` → **active (running)**
- [ ] `curl -Ik https://analyse.yayematy.com` → **200** ou **302**
- [ ] `.env` en `chmod 600`, propriétaire `colobanes`

#### Django / interface

- [ ] https://analyse.yayematy.com → page connexion + CSS (`/static/css/style.css`)
- [ ] Connexion superuser OK
- [ ] `/admin/` accessible
- [ ] Mots-clés actifs configurés dans Paramètres

#### Scraping

- [ ] Playwright Chromium installé pour `colobanes`
- [ ] `data/scraper_sessions/tiktok.json` présent
- [ ] `data/scraper_sessions/facebook.json` présent (Facebook)
- [ ] `python manage.py verify_social_session --platform tiktok` → OK

#### NLP

- [ ] `NLP_CLASSIFIER_ENABLED=True` dans `.env`
- [ ] `python scripts/test_camembert.py` → classification OK
- [ ] `celery call intelligence.analyser_donnees_non_traitees` → `success: True`
- [ ] Commentaires CamemBERT > 0 après plusieurs sessions (si données ambiguës)

#### Nginx

- [ ] Sauvegarde `webuzoVH.conf.bak` conservée
- [ ] Pas de `duplicate location "/"` dans les logs nginx -t

### Script de vérification rapide (copier-coller)

```bash
cd /home/colobanes/analyse.yayematy.com
source venv/bin/activate

echo "=== Services ==="
systemctl is-active gunicorn-yayematy celery-yayematy celerybeat-yayematy

echo "=== Infrastructure ==="
python manage.py check_infrastructure --celery-task

echo "=== Site ==="
curl -s -o /dev/null -w "HTTPS: %{http_code}\n" https://analyse.yayematy.com

echo "=== Sessions scraping ==="
ls -la data/scraper_sessions/

echo "=== NLP .env ==="
grep NLP_CLASSIFIER_ENABLED .env

echo "=== Métriques NLP ==="
python manage.py shell -c "
from intelligence.models import SocialComment, SocialPost
print('Commentaires non analysés:', SocialComment.objects.filter(is_analyzed=False).count())
print('Posts en attente:', SocialPost.objects.filter(analysis_status='pending').count())
print('Posts analysés:', SocialPost.objects.filter(analysis_status='done').count())
print('Commentaires keyword:', SocialComment.objects.filter(analysis_method='keyword').count())
print('Commentaires CamemBERT:', SocialComment.objects.filter(analysis_method='camembert').count())
"
```

### Tests pipeline avancés (optionnel)

```bash
# Pipeline synchrone (sans Celery) — petit échantillon
python manage.py validate_scrape_pipeline --max-videos 3 --keyword-count 2

# Pipeline complet via Celery (long — worker requis)
python manage.py run_celery_pipeline_test --max-videos 5 --keyword-count 2
```

### Surveillance logs en production

```bash
# Celery worker (scraping + NLP)
journalctl -u celery-yayematy -f

# Celery Beat (planification)
journalctl -u celerybeat-yayematy -f

# Gunicorn (HTTP)
journalctl -u gunicorn-yayematy -f

# Nginx domaine
tail -f /usr/local/apps/nginx/var/log/analyse.yayematy.com.log
```

### Surveillance ressources

```bash
free -h
htop                    # ou top
ps aux | grep celery
du -sh ~/.cache/huggingface/   # cache modèle CamemBERT (user colobanes)
```

---

## 18. Mises à jour du code

```bash
cd /home/colobanes/analyse.yayematy.com
git pull

source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput

systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

Si Webuzo a régénéré `webuzoVH.conf`, réappliquez le bloc Gunicorn depuis votre `.bak`.

Après changement `.env` (NLP, campagne, DB) :

```bash
systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

---

## 19. Dépannage

### 403 Forbidden sur le domaine

| Cause | Solution |
|-------|----------|
| Nginx proxy encore vers Apache | Modifier `location /` dans `webuzoVH.conf` → Gunicorn |
| Cache Nginx | `rm -rf /var/webuzo-data/nginx_proxy_cache/colobanes/*` + reload |
| Doublon `location /` | Retirer `location /` du fichier custom |
| Config non rechargée | `nginx -t` doit être **successful** avant reload |

### `duplicate location "/"`

Le fichier custom **ne doit pas** contenir `location /`. Uniquement `/static/` et `.git`.

### `Ident authentication failed` (PostgreSQL)

Mettre `DB_HOST=127.0.0.1` dans `.env`.

### `Command 'python' not found`

Ubuntu n'a pas `python` par défaut. Toujours :

```bash
cd /home/colobanes/analyse.yayematy.com && source venv/bin/activate
python manage.py ...
```

### `This account is currently not available`

```bash
usermod -s /bin/bash colobanes
```

### Pas d'écriture dans le gestionnaire Webuzo

```bash
chown -R colobanes:colobanes /home/colobanes/analyse.yayematy.com
```

### Gunicorn 502 Bad Gateway

```bash
systemctl status gunicorn-yayematy
journalctl -u gunicorn-yayematy -n 50
ls -la /home/colobanes/analyse.yayematy.com/gunicorn.sock
chmod 755 /home/colobanes /home/colobanes/analyse.yayematy.com
```

### Celery ne démarre pas

```bash
journalctl -u celery-yayematy -n 50
redis-cli ping
python manage.py check_infrastructure --celery-task
```

### Playwright échoue dans Celery

Réinstaller Chromium **en tant que colobanes** (voir Phase 11).

### NLP / CamemBERT

| Symptôme | Solution |
|----------|----------|
| `NLP enabled: False` | `.env` → `NLP_CLASSIFIER_ENABLED=True` + restart Celery |
| Téléchargement HF lent | Ajouter `HF_TOKEN` dans `.env` |
| OOM / worker tué | `--concurrency=1` dans `celery-yayematy.service` |
| `camembert: 0` dans logs | Normal si keyword résout tout ; vérifier avec `test_camembert.py` |
| Erreur `is_analyzed` sur SocialPost | Utiliser `analysis_status='pending'` pour les posts |

### Facebook ne scrape pas

```bash
ls -la data/scraper_sessions/facebook.json   # doit exister
python manage.py verify_social_session --platform facebook
```

### Webuzo régénère webuzoVH.conf

Conserver `/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf.bak` et réappliquer les 2 blocs `location /` Gunicorn pour `analyse.yayematy.com`.

### Chaîne NLP ne tourne pas

1. `COLLECTION_ENABLED=True` et date campagne valide
2. `celerybeat-yayematy` actif : `systemctl status celerybeat-yayematy`
3. Logs Beat : `journalctl -u celerybeat-yayematy -n 30`
4. Test manuel : `celery call intelligence.analyser_donnees_non_traitees`

---

## 20. Fichiers prêts à l'emploi dans le dépôt

```
deploy/
├── systemd/
│   ├── gunicorn-yayematy.service
│   ├── celery-yayematy.service          # --concurrency=2
│   └── celerybeat-yayematy.service
└── nginx/
    ├── analyse.yayematy.com.conf          → custom Webuzo (static only)
    └── webuzoVH-location-gunicorn.conf    → snippet location /

.env.production.example                     → modèle .env VPS (NLP activé)
scripts/test_camembert.py                   → test rapide CamemBERT
DEPLOYMENT.md                               → ce guide
```

---

## Commandes de référence rapide

```bash
# Activer l'environnement (à faire avant toute commande Django)
cd /home/colobanes/analyse.yayematy.com && source venv/bin/activate

# Redémarrer toute la stack applicative
systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy

# Recharger Nginx Webuzo
/usr/local/apps/nginx/sbin/nginx -t && /usr/local/apps/nginx/sbin/nginx -s reload

# Vérification complète
python manage.py check_infrastructure --celery-task
python scripts/test_camembert.py

# Logs en direct
journalctl -u celery-yayematy -f
journalctl -u gunicorn-yayematy -f
```

---

**YAYEMATY MARKET** — Intelligence de marché au Sénégal.  
Périmètre de veille défini par les **mots-clés Paramètres**, pas par un secteur fixe.  
Chaîne production **100 % VPS** : scraping + NLP hybride + recommandations, sans dépendance au PC local.
