# Guide de déploiement — YAYEMATY MARKET (Django + Webuzo)

Guide complet pour déployer **YAYEMATY MARKET** sur un VPS **Ubuntu 24.04** avec le panneau **Webuzo**, **Nginx**, **Gunicorn**, **PostgreSQL**, **Redis** et **Celery**.

> **Environnement de référence** (déploiement validé)  
> - VPS : Contabo — IP `173.249.41.61`  
> - Domaine : `analyse.yayematy.com`  
> - Utilisateur Webuzo : `colobanes`  
> - Dossier projet : `/home/colobanes/analyse.yayematy.com`  
> - Dépôt Git : `https://github.com/nick-dev12/yaye-maty`

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
14. [Phase 12 — Vérifications finales](#14-phase-12--vérifications-finales)
15. [Mises à jour du code](#15-mises-à-jour-du-code)
16. [Dépannage](#16-dépannage)
17. [Fichiers prêts à l'emploi dans le dépôt](#17-fichiers-prêts-à-lemploi-dans-le-dépôt)

---

## 1. Architecture

```
Internet
   │
   ▼
Nginx (443 HTTPS) — analyse.yayematy.com
   ├── /static/  →  /home/colobanes/analyse.yayematy.com/staticfiles/
   └── /         →  Gunicorn (socket Unix) → Django (WSGI)
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
      PostgreSQL        Redis      Celery Worker + Beat
                                        │
                                   Playwright (Jumia, Jiji, réseaux)
```

**Important :** Django ne passe **jamais** par Apache/PHP. Apache reste pour les autres domaines PHP (`colobanes.com`). Pour `analyse.yayematy.com`, Nginx proxy directement vers **Gunicorn**.

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

### Paquets système (SSH root)

```bash
apt update && apt upgrade -y
apt install -y git build-essential libpq-dev python3-venv python3-dev python3.12-venv
```

### Accès

- SSH root : `ssh root@173.249.41.61`
- Panneau Webuzo utilisateur : `https://173.249.41.61:2003`
- Panneau Webuzo admin : `https://173.249.41.61:2005`

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

Si `torch` / `transformers` échouent (optionnel — NLP désactivé sur VPS) :

```bash
pip install Django psycopg2-binary celery redis python-dotenv \
  playwright playwright-stealth pytrends requests pandas lxml numpy gunicorn
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

Générer `INTELLIGENCE_API_KEY` (2e clé, pour API machine locale) :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Exemple `.env` (voir `.env.production.example` dans le dépôt) :

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
NLP_CLASSIFIER_ENABLED=False
CELERY_UI_LAUNCH=False

INTELLIGENCE_API_KEY=...
COLLECTION_ENABLED=True
```

Sécuriser :

```bash
chmod 600 .env
chown colobanes:colobanes .env
```

Sur votre **PC local**, copiez la même `INTELLIGENCE_API_KEY` dans `local_nlp/.env`.

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

Ou créer `/etc/systemd/system/gunicorn-yayematy.service` :

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

Vérification :

```bash
source venv/bin/activate
celery -A yayematy_project inspect ping
# → pong
```

### Planification automatique (Celery Beat)

| Tâche | Horaire (Africa/Dakar) |
|-------|------------------------|
| Google Trends | 03:00 |
| Jiji | 06:45, 12:45, 18:45 |
| Jumia | 07:30, 13:30, 19:30 |
| Réseaux sociaux | 08:15, 14:15, 20:15 |
| Analyse NLP | 09:00, 15:00, 21:00 |
| Recommandations achat | 04:30 |

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
```

---

## 14. Phase 12 — Vérifications finales

```bash
# Services
systemctl status gunicorn-yayematy celery-yayematy celerybeat-yayematy

# Logs
journalctl -u gunicorn-yayematy -n 30 --no-pager
journalctl -u celery-yayematy -n 30 --no-pager

# Site
curl -Ik https://analyse.yayematy.com

# Redis
redis-cli ping
```

Checklist :

- [ ] https://analyse.yayematy.com → page connexion Django + CSS
- [ ] Connexion superuser OK
- [ ] `/admin/` accessible
- [ ] Fichiers statiques (`/static/css/style.css`) chargés
- [ ] Celery ping → `pong`
- [ ] `.env` en `chmod 600`
- [ ] Sauvegarde `webuzoVH.conf.bak` conservée

---

## 15. Mises à jour du code

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

---

## 16. Dépannage

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
```

### Playwright échoue dans Celery

Réinstaller Chromium **en tant que colobanes** (voir Phase 11).

### Webuzo régénère webuzoVH.conf

Conserver `/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf.bak` et réappliquer les 2 blocs `location /` Gunicorn pour `analyse.yayematy.com`.

---

## 17. Fichiers prêts à l'emploi dans le dépôt

```
deploy/
├── systemd/
│   ├── gunicorn-yayematy.service
│   ├── celery-yayematy.service
│   └── celerybeat-yayematy.service
└── nginx/
    ├── analyse.yayematy.com.conf          → custom Webuzo
    └── webuzoVH-location-gunicorn.conf    → snippet location /

.env.production.example                     → modèle .env VPS
DEPLOYMENT.md                               → ce guide
```

---

## Commandes de référence rapide

```bash
# Redémarrer toute la stack applicative
systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy

# Recharger Nginx Webuzo
/usr/local/apps/nginx/sbin/nginx -t && /usr/local/apps/nginx/sbin/nginx -s reload

# Logs en direct
journalctl -u gunicorn-yayematy -f
journalctl -u celery-yayematy -f
tail -f /usr/local/apps/nginx/var/log/analyse.yayematy.com.log
```

---

**YAYEMATY MARKET** — Intelligence de marché au Sénégal.  
Périmètre de veille défini par les **mots-clés Paramètres**, pas par un secteur fixe.
