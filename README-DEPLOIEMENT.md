# Mises à jour sur le serveur — YAYEMATY MARKET

Guide rapide pour **mettre à jour le code**, **publier les fichiers statiques** (CSS, JS, images) et **redémarrer les services** après chaque déploiement.

> Installation initiale complète du VPS : voir **[DEPLOYMENT.md](DEPLOYMENT.md)**.

---

## Workflow complet (PC → GitHub → VPS)

### 1. Sur votre PC (Windows) — envoyer les modifications

```powershell
cd "C:\Users\jomas\Desktop\yaye maty"
git add .
git status
git commit -m "Description de vos changements"
git push origin main
```

### 2. Sur le VPS — récupérer et déployer

Connectez-vous en SSH :

```bash
ssh root@173.249.41.61
```

Puis exécutez **cette commande bloc** (copier-coller) :

```bash
cd /home/colobanes/analyse.yayematy.com
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
systemctl status gunicorn-yayematy celery-yayematy celerybeat-yayematy
python manage.py check_infrastructure --celery-task
```

### 3. Vérifier dans le navigateur

- Site : https://analyse.yayematy.com
- Rafraîchir avec **Ctrl+F5** si vous avez modifié du CSS/JS

---
## Environnement de référence

| Élément | Valeur |
|---------|--------|
| Serveur | VPS Ubuntu 24.04 (Webuzo) |
| Domaine | `https://analyse.yayematy.com` |
| Utilisateur | `colobanes` |
| Dossier projet | `/home/colobanes/analyse.yayematy.com` |
| Virtualenv | `/home/colobanes/analyse.yayematy.com/venv` |

---

## Commande essentielle — fichiers statiques

À exécuter **sur le VPS** après chaque déploiement qui modifie `static/` (CSS, JS, images) :

```bash
cd /home/colobanes/analyse.yayematy.com
source venv/bin/activate
python manage.py collectstatic --noinput
```

**Rôle :** copie le contenu de `static/` vers `staticfiles/` (`STATIC_ROOT`).  
**Nginx** sert les URLs `/static/` depuis `staticfiles/` — **pas Gunicorn**.

Après `collectstatic`, un simple **Ctrl+F5** dans le navigateur suffit si vous n’avez modifié **que** du CSS/JS.

---

## Faut-il redémarrer Gunicorn et Celery ?

| Type de changement | `collectstatic` | Gunicorn | Celery worker | Celery Beat |
|--------------------|-----------------|----------|---------------|-------------|
| CSS / JS / images uniquement | ✅ Oui | ❌ Non | ❌ Non | ❌ Non |
| Code Python (views, services, tasks…) | — | ✅ Oui | ✅ Oui | ⚠️ Si `settings.py` ou planification |
| Migrations base de données | — | ✅ Oui | ✅ Oui | ❌ (sauf settings) |
| Fichier `.env` (DB, Redis, NLP…) | — | ✅ Oui | ✅ Oui | ✅ Oui |

**En pratique :** après un `git pull` complet, redémarrez les trois services (voir ci-dessous).

---

## Déploiement complet (recommandé)

À lancer **sur le VPS** après chaque `git push` :

```bash
cd /home/colobanes/analyse.yayematy.com
git pull

source venv/bin/activate
pip install -r requirements.txt          # uniquement si requirements.txt a changé
python manage.py migrate                 # uniquement si de nouvelles migrations existent
python manage.py collectstatic --noinput

sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

### Vérifications

```bash
sudo systemctl status gunicorn-yayematy celery-yayematy celerybeat-yayematy
python manage.py check_infrastructure --celery-task
curl -I https://analyse.yayematy.com/
```

Tous les services doivent être **active (running)**.

---

## Déploiement rapide — CSS / JS seulement

Si vous avez **uniquement** modifié des fichiers dans `static/` :

```bash
cd /home/colobanes/analyse.yayematy.com
git pull
source venv/bin/activate
python manage.py collectstatic --noinput
```

**Pas de redémarrage** Gunicorn / Celery nécessaire.

---

## Déploiement rapide — code Python seulement

Si vous avez modifié du code Django **sans** toucher aux fichiers statiques :

```bash
cd /home/colobanes/analyse.yayematy.com
git pull
source venv/bin/activate
python manage.py migrate                 # si besoin
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy
```

`collectstatic` n’est pas obligatoire dans ce cas.

---

## Services systemd (noms officiels)

| Service | Rôle |
|---------|------|
| `gunicorn-yayematy` | Application Django (HTTP) |
| `celery-yayematy` | Worker — scraping, NLP, tâches async |
| `celerybeat-yayematy` | Planification (Cron Celery) |

### Commandes utiles

```bash
# Redémarrer
sudo systemctl restart gunicorn-yayematy celery-yayematy celerybeat-yayematy

# Statut
sudo systemctl status gunicorn-yayematy

# Logs en direct
sudo journalctl -u gunicorn-yayematy -f
sudo journalctl -u celery-yayematy -f
sudo journalctl -u celerybeat-yayematy -f
```

Fichiers unités dans le dépôt : `deploy/systemd/`.

---

## Architecture des fichiers statiques

```
Projet
├── static/           ← sources (développement + dépôt Git)
└── staticfiles/      ← destination production (généré par collectstatic)

Navigateur
  → GET /static/css/auth.css?v=4
  → Nginx lit staticfiles/css/auth.css
  → Gunicorn n’intervient pas
```

En **local** (`runserver`), Django sert directement `static/` : **`collectstatic` n’est pas nécessaire** en développement.

---

## En local (Windows) — rappel

```powershell
cd "C:\chemin\vers\yaye maty"
.\venv\Scripts\Activate.ps1
py manage.py runserver
```

Worker Celery local :

```powershell
.\scripts\run_celery_worker.ps1
```

Après modification de code Python local, **redémarrez le worker Celery** (pas `collectstatic`).

---

## Checklist post-déploiement

- [ ] `git pull` sans erreur
- [ ] `python manage.py migrate` (si migrations)
- [ ] `python manage.py collectstatic --noinput`
- [ ] `systemctl restart` des 3 services (si code Python ou `.env`)
- [ ] Site accessible : `https://analyse.yayematy.com/`
- [ ] CSS à jour (Ctrl+F5)
- [ ] `python manage.py check_infrastructure --celery-task` → OK

---

## Dépannage rapide

### Les CSS ne changent pas en production

1. Vérifier que `collectstatic` a bien été exécuté sur le VPS.
2. Vider le cache navigateur (Ctrl+F5).
3. Vérifier que Nginx sert bien `/static/` depuis `staticfiles/` (voir `DEPLOYMENT.md`, phase Nginx).

### Page blanche ou erreur 502

```bash
sudo journalctl -u gunicorn-yayematy -n 50
sudo systemctl restart gunicorn-yayematy
```

### Tâches Celery ne partent plus

```bash
sudo systemctl restart celery-yayematy celerybeat-yayematy
python manage.py check_infrastructure --celery-task
sudo journalctl -u celery-yayematy -n 50
```

---

## Voir aussi

- **[DEPLOYMENT.md](DEPLOYMENT.md)** — installation initiale complète du VPS
- **`deploy/systemd/`** — fichiers service Gunicorn / Celery
- **`deploy/nginx/`** — configuration Nginx / Webuzo
