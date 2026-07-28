#!/usr/bin/env bash
# Réapplique le proxy Gunicorn pour analyse.yayematy.com (Webuzo régénère webuzoVH.conf)
#
# Usage :
#   sudo bash deploy/fix-webuzo-nginx-yayematy.sh           # patch + reload si besoin
#   sudo bash deploy/fix-webuzo-nginx-yayematy.sh --check    # vérifie seulement (timer)
#   sudo bash deploy/fix-webuzo-nginx-yayematy.sh --restore # restaure .bak
#   sudo bash deploy/install-webuzo-nginx-guard.sh           # automatisation systemd

set -euo pipefail

NGINX_CONF="/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf"
NGINX_BAK="/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf.bak"
GUNICORN_SOCK="/home/colobanes/analyse.yayematy.com/gunicorn.sock"
CUSTOM_CONF="/var/webuzo-data/nginx/custom/domains/analyse.yayematy.com.conf"
PROJECT_DIR="${PROJECT_DIR:-/home/colobanes/analyse.yayematy.com}"
NGINX_BIN="/usr/local/apps/nginx/sbin/nginx"
LOG_TAG="yayematy-nginx-guard"

log() { echo "[$LOG_TAG] $*"; }

needs_patch() {
  [[ -f "$NGINX_CONF" ]] || return 0
  grep -q 'server_name[[:space:]]\+analyse\.yayematy\.com' "$NGINX_CONF" || return 1
  # Les 2 blocs analyse (80 + 443) doivent pointer vers Gunicorn
  local count
  count=$(grep -c 'proxy_pass http://unix:/home/colobanes/analyse.yayematy.com/gunicorn.sock' "$NGINX_CONF" 2>/dev/null || echo 0)
  [[ "$count" -lt 2 ]]
}

apply_patch() {
  python3 << 'PY'
import re
import sys
from pathlib import Path

conf_path = Path("/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf")
text = conf_path.read_text(encoding="utf-8", errors="replace")

gunicorn = """\t# YAYEMATY — Django via Gunicorn
\tlocation / {
\t\tproxy_pass http://unix:/home/colobanes/analyse.yayematy.com/gunicorn.sock;
\t\tproxy_set_header Host $host;
\t\tproxy_set_header X-Real-IP $remote_addr;
\t\tproxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
\t\tproxy_set_header X-Forwarded-Proto $scheme;
\t\tproxy_read_timeout 120s;
\t}"""

# Découpe par blocs server { ... }
parts = re.split(r'(?=server\s*\{)', text)
out = []
patched = 0
for part in parts:
    if not part.strip():
        continue
    if re.search(r'server_name\s+analyse\.yayematy\.com', part):
        new_part, n = re.subn(
            r'location\s*/\s*\{.*?\n\t\}',
            gunicorn,
            part,
            count=1,
            flags=re.DOTALL,
        )
        if n:
            patched += 1
            out.append(new_part)
        else:
            out.append(part)
    else:
        out.append(part)

if patched < 2:
    print(f"ERREUR: {patched}/2 blocs patchés", file=sys.stderr)
    sys.exit(1)

conf_path.write_text("".join(out), encoding="utf-8")
print(f"OK: {patched} blocs patchés")
PY
}

reload_nginx() {
  rm -rf /var/webuzo-data/nginx_proxy_cache/colobanes/* 2>/dev/null || true
  "$NGINX_BIN" -t
  "$NGINX_BIN" -s reload
}

sync_custom_conf() {
  mkdir -p "$(dirname "$CUSTOM_CONF")"
  if [[ -f "$PROJECT_DIR/deploy/nginx/analyse.yayematy.com.conf" ]]; then
    cp "$PROJECT_DIR/deploy/nginx/analyse.yayematy.com.conf" "$CUSTOM_CONF"
  fi
}

MODE="${1:-}"

if [[ "$MODE" == "--restore" ]]; then
  [[ -f "$NGINX_BAK" ]] || { log "Absent: $NGINX_BAK"; exit 1; }
  cp "$NGINX_BAK" "$NGINX_CONF"
  sync_custom_conf
  reload_nginx
  log "Restauré depuis .bak"
  exit 0
fi

if [[ "$MODE" == "--check" ]]; then
  if needs_patch; then
    log "Config incorrecte — patch nécessaire"
    exit 1
  fi
  exit 0
fi

if [[ ! -f "$NGINX_CONF" ]]; then
  log "Absent: $NGINX_CONF"
  exit 1
fi

if ! needs_patch; then
  log "Déjà OK (Gunicorn actif pour analyse.yayematy.com)"
  # Rafraîchir .bak seulement si la config est bonne
  if [[ ! -f "$NGINX_BAK" || "$MODE" == "--force-bak" ]]; then
    cp "$NGINX_CONF" "$NGINX_BAK"
    log "Sauvegarde .bak créée (config OK)"
  fi
  exit 0
fi

log "Webuzo a régénéré webuzoVH.conf — application du patch Gunicorn…"
apply_patch
sync_custom_conf
reload_nginx
# .bak = config qui fonctionne (après patch)
cp "$NGINX_CONF" "$NGINX_BAK"
log "Patch appliqué, Nginx rechargé, .bak mis à jour"
