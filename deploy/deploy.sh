#!/usr/bin/env bash
# =============================================================================
# YAYEMATY MARKET — Script de déploiement VPS
# Usage (en root sur le VPS) :
#   sudo bash /home/colobanes/analyse.yayematy.com/deploy/deploy.sh
#   sudo bash deploy/deploy.sh --fast          # CSS/JS seulement
#   sudo bash deploy/deploy.sh --skip-pip      # sans pip install
# =============================================================================

set -euo pipefail

# ── Configuration (adapter si besoin) ────────────────────────────────────────
APP_USER="${APP_USER:-colobanes}"
PROJECT_DIR="${PROJECT_DIR:-/home/colobanes/analyse.yayematy.com}"
VENV_DIR="${VENV_DIR:-${PROJECT_DIR}/venv}"
GIT_BRANCH="${GIT_BRANCH:-main}"
SITE_URL="${SITE_URL:-https://analyse.yayematy.com}"

SERVICES=(
    "gunicorn-yayematy"
    "celery-yayematy"
    "celerybeat-yayematy"
)

# ── Options ────────────────────────────────────────────────────────────────────
SKIP_PIP=false
SKIP_MIGRATE=false
SKIP_STATIC=false
SKIP_RESTART=false
SKIP_GIT=false
FAST_MODE=false
RESET_SETTINGS=false
RUN_CHECKS=true

usage() {
    cat <<'EOF'
Usage: deploy.sh [OPTIONS]

Déploie la dernière version depuis GitHub et redémarre les services.

Options:
  --fast              Déploiement rapide : git pull + collectstatic uniquement
  --skip-pip          Ne pas exécuter pip install
  --skip-migrate      Ne pas exécuter migrate
  --skip-static       Ne pas exécuter collectstatic
  --skip-restart      Ne pas redémarrer Gunicorn/Celery
  --skip-git          Ne pas faire git pull (migrate/static/restart seulement)
  --reset-settings    Abandonner les modifs locales de settings.py avant pull
  --no-checks         Pas de vérifications finales (curl, check_infrastructure)
  -h, --help          Afficher cette aide

Exemples:
  sudo bash deploy/deploy.sh
  sudo bash deploy/deploy.sh --fast
  sudo bash deploy/deploy.sh --reset-settings
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast)           FAST_MODE=true; SKIP_PIP=true; SKIP_MIGRATE=true; SKIP_RESTART=true ;;
        --skip-pip)       SKIP_PIP=true ;;
        --skip-migrate)   SKIP_MIGRATE=true ;;
        --skip-static)    SKIP_STATIC=true ;;
        --skip-restart)   SKIP_RESTART=true ;;
        --skip-git)       SKIP_GIT=true ;;
        --reset-settings) RESET_SETTINGS=true ;;
        --no-checks)      RUN_CHECKS=false ;;
        -h|--help)        usage; exit 0 ;;
        *)                echo "Option inconnue: $1"; usage; exit 1 ;;
    esac
    shift
done

# ── Couleurs ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; NC=''
fi

log()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERREUR]${NC} $*" >&2; }

# ── Vérifications préalables ───────────────────────────────────────────────────
if [[ "$(id -u)" -ne 0 ]]; then
    err "Ce script doit être exécuté en root (ou via sudo)."
    err "Exemple : sudo bash deploy/deploy.sh"
    exit 1
fi

if ! id "$APP_USER" &>/dev/null; then
    err "Utilisateur introuvable : $APP_USER"
    exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
    err "Dossier projet introuvable : $PROJECT_DIR"
    exit 1
fi

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    err "Virtualenv introuvable : $VENV_DIR"
    exit 1
fi

run_as_app() {
    sudo -u "$APP_USER" bash -lc "$1"
}

# ── En-tête ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  YAYEMATY MARKET — Déploiement${NC}"
echo -e "${BOLD}  $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
log "Projet  : $PROJECT_DIR"
log "Utilisateur app : $APP_USER"
log "Branche : $GIT_BRANCH"
if $FAST_MODE; then warn "Mode rapide (--fast) : static uniquement, pas de restart"; fi
echo ""

# ── 1. Git pull ────────────────────────────────────────────────────────────────
if ! $SKIP_GIT; then
    log "Étape 1/5 — Git pull"

    if $RESET_SETTINGS; then
        warn "Abandon des modifications locales de settings.py"
        run_as_app "cd '$PROJECT_DIR' && git checkout -- yayematy_project/settings.py" || true
    fi

    if run_as_app "cd '$PROJECT_DIR' && git diff --quiet yayematy_project/settings.py 2>/dev/null"; then
        : # settings.py propre
    elif ! $RESET_SETTINGS; then
        if run_as_app "cd '$PROJECT_DIR' && git diff yayematy_project/settings.py | grep -q ."; then
            warn "settings.py modifié localement sur le VPS."
            warn "Relancez avec --reset-settings pour abandonner ces changements."
            warn "Ou manuellement : git checkout -- yayematy_project/settings.py"
            exit 1
        fi
    fi

    run_as_app "cd '$PROJECT_DIR' && git fetch origin && git pull origin '$GIT_BRANCH'"
    ok "Code à jour ($(run_as_app "cd '$PROJECT_DIR' && git rev-parse --short HEAD"))"
else
    log "Étape 1/5 — Git pull (ignoré)"
fi

# ── 2. pip install ─────────────────────────────────────────────────────────────
if ! $SKIP_PIP; then
    log "Étape 2/5 — pip install"
    run_as_app "cd '$PROJECT_DIR' && source '$VENV_DIR/bin/activate' && pip install -r requirements.txt -q"
    ok "Dépendances Python à jour"
else
    log "Étape 2/5 — pip install (ignoré)"
fi

# ── 3. Migrations ──────────────────────────────────────────────────────────────
if ! $SKIP_MIGRATE; then
    log "Étape 3/5 — Migrations Django"
    MIGRATE_OUTPUT=$(run_as_app "cd '$PROJECT_DIR' && source '$VENV_DIR/bin/activate' && python manage.py migrate" 2>&1) || {
        err "Échec migrate"
        echo "$MIGRATE_OUTPUT"
        exit 1
    }
    echo "$MIGRATE_OUTPUT"
    if echo "$MIGRATE_OUTPUT" | grep -q "not yet reflected in a migration"; then
        warn "Des modèles ont changé sans migration — créez-les sur le PC (makemigrations) puis repush."
    fi
    ok "Migrations appliquées"
else
    log "Étape 3/5 — Migrations (ignorées)"
fi

# ── 4. Fichiers statiques ──────────────────────────────────────────────────────
if ! $SKIP_STATIC; then
    log "Étape 4/5 — collectstatic"
    STATIC_OUTPUT=$(run_as_app "cd '$PROJECT_DIR' && source '$VENV_DIR/bin/activate' && python manage.py collectstatic --noinput" 2>&1)
    echo "$STATIC_OUTPUT"
    ok "Fichiers statiques publiés"
else
    log "Étape 4/5 — collectstatic (ignoré)"
fi

# ── 5. Redémarrage services ────────────────────────────────────────────────────
if ! $SKIP_RESTART; then
    log "Étape 5/5 — Redémarrage services systemd"
    for svc in "${SERVICES[@]}"; do
        if systemctl is-enabled "$svc" &>/dev/null || systemctl list-unit-files | grep -q "^${svc}.service"; then
            systemctl restart "$svc"
            ok "Redémarré : $svc"
        else
            warn "Service non installé (ignoré) : $svc"
        fi
    done
    sleep 2
else
    log "Étape 5/5 — Redémarrage services (ignoré)"
fi

# ── Vérifications finales ──────────────────────────────────────────────────────
echo ""
log "Vérifications finales"
echo ""

if ! $SKIP_RESTART; then
    for svc in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            ok "$svc → active (running)"
        elif systemctl list-unit-files 2>/dev/null | grep -q "^${svc}.service"; then
            err "$svc → inactif ou en erreur"
            systemctl status "$svc" --no-pager -l || true
        fi
    done
fi

if $RUN_CHECKS; then
    if command -v curl &>/dev/null; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -I "$SITE_URL/" || echo "000")
        if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "302" ]]; then
            ok "Site HTTP → $HTTP_CODE ($SITE_URL)"
        else
            warn "Site HTTP → $HTTP_CODE (attendu 200 ou 302)"
        fi
    fi

    if ! $SKIP_RESTART && ! $FAST_MODE; then
        if run_as_app "cd '$PROJECT_DIR' && source '$VENV_DIR/bin/activate' && python manage.py check_infrastructure --celery-task" 2>/dev/null; then
            ok "Infrastructure Celery → OK"
        else
            warn "check_infrastructure a échoué ou Celery indisponible (voir logs journalctl)"
        fi
    fi
fi

# ── Fin ────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Déploiement terminé avec succès${NC}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
log "Site : $SITE_URL"
log "Logs : journalctl -u gunicorn-yayematy -f"
echo ""
