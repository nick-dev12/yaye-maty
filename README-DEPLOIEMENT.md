# Mises à jour sur le serveur — YAYEMATY MARKET

Guide pratique pour **déployer et mettre à jour** le site sur le VPS : Git, fichiers statiques, migrations, redémarrage Gunicorn/Celery.

> **Installation initiale** (première fois sur le VPS) : **[DEPLOYMENT.md](DEPLOYMENT.md)**  
> Modèle `.env` production : **`.env.production.example`**

---

## Environnement de référence

| Élément | Valeur |
|---------|--------|
| VPS | Ubuntu 24.04 — Contabo Cloud VPS 8 |
| IP | `173.249.41.61` |
| Domaine | `https://analyse.yayematy.com` |
| Utilisateur Linux | **`colobanes`** (propriétaire du projet) |
| Dossier projet | `/home/colobanes/analyse.yayematy.com` |
| Virtualenv | `/home/colobanes/analyse.yayematy.com/venv` |
| Dépôt Git | `https://github.com/nick-dev12/yaye-maty` |

---

## Règle d’or sur le VPS

| Action | Utilisateur |
|--------|-------------|
| `git pull`, `migrate`, `collectstatic`, `pip install` | **`colobanes`** (`sudo -u colobanes …`) |
| `systemctl restart …` | **root** ou **sudo** |

**Ne jamais** faire `git pull` en **root** directement sur le dossier de `colobanes` (erreur *dubious ownership*).

**Ne jamais** modifier **`settings.py`** sur le VPS — la config prod va dans **`.env`**.

---

## Workflow complet (PC → GitHub → VPS)

### 1. Sur votre PC (Windows)

```powershell
cd "C:\Users\jomas\Desktop\yaye maty"
git add .
git status
git commit -m "Description de vos changements"
git push origin main
```

### 2. Connexion SSH au VPS

```bash
ssh root@173.249.41.61
```

### 3. Commande bloc — déploiement standard (recommandé)

Copier-coller **en root** :

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git pull
  source venv/bin/activate
  pip install -r requirements.txt -q
  python manage.py migrate
  python manage.py collectstatic --noinput
'

sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy

sudo systemctl status gunicorn-yayematy celery-yayematy celerybeat-yayematy --no-pager
curl -I https://analyse.yayematy.com/
```

### 4. Vérifier dans le navigateur

- Ouvrir : https://analyse.yayematy.com
- **Ctrl+F5** si CSS/JS modifiés

---

## Quoi redémarrer selon les fichiers modifiés ?

| Fichiers modifiés (exemples) | `git pull` | `pip install` | `migrate` | `collectstatic` | Gunicorn | Celery worker | Celery Beat |
|------------------------------|:----------:|:---------------:|:---------:|:---------------:|:--------:|:-------------:|:-----------:|
| `static/css/`, `static/js/` | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `templates/` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `intelligence/views.py`, `controllers/` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| `intelligence/tasks.py`, `services/` | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| `yayematy_project/settings.py`, `.env` | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `CELERY_BEAT_SCHEDULE` (settings) | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `intelligence/migrations/` | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ |
| `requirements.txt` | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `deploy/systemd/*.service` | ✅ | ❌ | ❌ | ❌ | ⚠️ | ⚠️ | ⚠️ |

⚠️ = copier le fichier vers `/etc/systemd/system/`, puis `systemctl daemon-reload` + restart.

**En cas de doute** après un déploiement : redémarrez les **3 services** (sans danger).

---

## Déploiements rapides (ciblés)

### CSS / JS / images seulement

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git pull
  source venv/bin/activate
  python manage.py collectstatic --noinput
'
```

Pas de redémarrage Gunicorn/Celery.

### Code Python seulement (sans static)

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git pull
  source venv/bin/activate
  python manage.py migrate
'

sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

### Fichier `.env` modifié (sans git)

```bash
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

---

## Commande `collectstatic` — détail

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  source venv/bin/activate
  python manage.py collectstatic --noinput
'
```

- **Source** : dossier `static/` (dans Git)
- **Destination** : `staticfiles/` (`STATIC_ROOT`)
- **Servi par** : Nginx sur `/static/` — **pas** Gunicorn

Exemple de sortie normale :

```
2 static files copied to '.../staticfiles', 143 unmodified.
```

En local (`runserver`), **`collectstatic` n’est pas nécessaire**.

---

## Services systemd

| Service | Rôle | Fichier dans le dépôt |
|---------|------|------------------------|
| `gunicorn-yayematy` | Django (HTTP via socket Unix) | `deploy/systemd/gunicorn-yayematy.service` |
| `celery-yayematy` | Worker — scraping, NLP, tâches async | `deploy/systemd/celery-yayematy.service` |
| `celerybeat-yayematy` | Planification (horaires Celery) | `deploy/systemd/celerybeat-yayematy.service` |

### Redémarrer

```bash
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

### Statut

```bash
sudo systemctl status gunicorn-yayematy --no-pager
sudo systemctl status celery-yayematy --no-pager
sudo systemctl status celerybeat-yayematy --no-pager
```

### Logs en direct

```bash
sudo journalctl -u gunicorn-yayematy -f
sudo journalctl -u celery-yayematy -f
sudo journalctl -u celerybeat-yayematy -f
```

### Test HTTP

```bash
curl -I https://analyse.yayematy.com/
# Attendu : HTTP/1.1 200 OK
```

### Test Celery

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  source venv/bin/activate
  python manage.py check_infrastructure --celery-task
'
```

---

## Problèmes fréquents et solutions

### 1. `fatal: detected dubious ownership in repository`

**Cause :** `git pull` lancé en **root** sur un dossier appartenant à `colobanes`.

**Solution :** toujours utiliser `sudo -u colobanes bash -lc '...'`.

Ne pas utiliser `git config --global safe.directory` sauf cas exceptionnel.

---

### 2. `This account is currently not available` (`su - colobanes`)

**Cause :** shell de l’utilisateur = `/usr/sbin/nologin`.

**Fix (une fois, en root) :**

```bash
usermod -s /bin/bash colobanes
```

Ensuite `su - colobanes` fonctionne. **`sudo -u colobanes bash`** fonctionne déjà sans ce fix.

---

### 3. `Your local changes would be overwritten by merge` (`settings.py`)

**Cause :** `settings.py` modifié à la main sur le VPS lors du premier déploiement.

**Vérifier les différences :**

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git diff yayematy_project/settings.py
'
```

Si le diff ne contient que `STATIC_ROOT` et le bloc HTTPS → **déjà dans Git**, on peut abandonner la version locale :

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git checkout -- yayematy_project/settings.py
  git pull
'
```

**Sauvegarde avant abandon (optionnel) :**

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  cp yayematy_project/settings.py /tmp/settings.py.vps.bak
  git checkout -- yayematy_project/settings.py
  git pull
'
```

Toute config prod → **`.env`**, jamais `settings.py` sur le serveur.

---

### 4. `No migrations to apply` + `models have changes not yet reflected in a migration`

**Cause :** le code local (PC) a des changements de modèles sans fichier de migration commité.

**Sur le PC (pas le VPS) :**

```powershell
py manage.py makemigrations intelligence
git add intelligence/migrations/
git commit -m "Add migrations for model changes"
git push origin main
```

**Puis sur le VPS :**

```bash
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git pull
  source venv/bin/activate
  python manage.py migrate
'
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

Si le message apparaît mais le site fonctionne, ce n’est **pas bloquant** pour un déploiement CSS/templates.

---

### 5. Fichiers avec mauvais propriétaire (`root` au lieu de `colobanes`)

```bash
chown -R colobanes:colobanes /home/colobanes/analyse.yayematy.com
```

---

### 6. CSS ne change pas en production

1. `collectstatic` exécuté sur le VPS ?
2. Ctrl+F5 dans le navigateur
3. Vérifier la version dans l’URL (`auth.css?v=4`)

---

### 7. Page blanche / 502 / 405 déconnexion

```bash
sudo journalctl -u gunicorn-yayematy -n 50
sudo systemctl restart gunicorn-yayematy
```

La déconnexion doit être en **POST** (déjà corrigé dans le template sidebar).

---

## Fichiers `.env` production (rappel)

Ne **jamais** commiter `.env`. Sur le VPS :

```bash
nano /home/colobanes/analyse.yayematy.com/.env
```

Variables essentielles (voir `.env.production.example`) :

```env
DEBUG=False
ALLOWED_HOSTS=analyse.yayematy.com,173.249.41.61
SECRET_KEY=votre-cle-secrete
DB_HOST=127.0.0.1
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
NLP_CLASSIFIER_ENABLED=True
```

Après modification de `.env` :

```bash
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

---

## Checklist post-déploiement

- [ ] `git pull` sans erreur (via `sudo -u colobanes`)
- [ ] `python manage.py migrate` (si nouvelles migrations)
- [ ] `python manage.py collectstatic --noinput`
- [ ] `systemctl restart` gunicorn + celery + beat
- [ ] `systemctl status` → **active (running)**
- [ ] `curl -I https://analyse.yayematy.com/` → **200 OK**
- [ ] Site OK dans le navigateur (Ctrl+F5)
- [ ] `check_infrastructure --celery-task` → OK (optionnel)

---

## Exemple de déploiement réussi (juillet 2026)

```bash
# 1. Abandon des modifs locales settings.py + pull
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  git checkout -- yayematy_project/settings.py
  git pull
'

# 2. Migrate + static
sudo -u colobanes bash -lc '
  cd /home/colobanes/analyse.yayematy.com
  source venv/bin/activate
  python manage.py migrate
  python manage.py collectstatic --noinput
'

# 3. Restart services
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy

# 4. Vérification
sudo systemctl status gunicorn-yayematy --no-pager
curl -I https://analyse.yayematy.com/
```

Résultat attendu :

```
Fast-forward
...
2 static files copied to '.../staticfiles', 143 unmodified.
● gunicorn-yayematy.service - Active: active (running)
HTTP/1.1 200 OK
```

---

## En local (Windows) — rappel

```powershell
cd "C:\Users\jomas\Desktop\yaye maty"
.\venv\Scripts\Activate.ps1
py manage.py runserver
```

Worker Celery local :

```powershell
.\scripts\run_celery_worker.ps1
```

Après modification Python local → **redémarrer le worker Celery** (pas `collectstatic`).

---

## Architecture fichiers statiques

```
Projet
├── static/           ← sources (Git)
└── staticfiles/      ← généré par collectstatic (Nginx)

Navigateur → GET /static/css/auth.css
          → Nginx → staticfiles/css/auth.css
          → Gunicorn n'intervient pas
```

---

## Voir aussi

| Fichier | Contenu |
|---------|---------|
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Installation initiale complète VPS |
| **`.env.production.example`** | Modèle variables d'environnement |
| **`deploy/systemd/`** | Services Gunicorn / Celery |
| **`deploy/nginx/`** | Config Nginx / Webuzo |
