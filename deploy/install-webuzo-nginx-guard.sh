#!/usr/bin/env bash
# Installe la surveillance automatique Nginx (patch Gunicorn si Webuzo régénère webuzoVH.conf)
#
# Usage (root sur le VPS) :
#   sudo bash deploy/install-webuzo-nginx-guard.sh

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/colobanes/analyse.yayematy.com}"
NGINX_BAK="/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf.bak"
NGINX_CONF="/usr/local/apps/nginx/etc/conf.d/webuzoVH.conf"
REPO_CONF="$PROJECT_DIR/deploy/nginx/webuzoVH.conf"

echo "=== Installation garde Nginx YAYEMATY ==="

# 1. Patch IMMÉDIAT (avant toute sauvegarde .bak)
if [[ -f "$PROJECT_DIR/deploy/fix-webuzo-nginx-yayematy.sh" ]]; then
  bash "$PROJECT_DIR/deploy/fix-webuzo-nginx-yayematy.sh"
else
  echo "Script fix absent — copie depuis le repo si disponible"
  if [[ -f "$REPO_CONF" ]]; then
    cp "$NGINX_CONF" "${NGINX_CONF}.pre-fix" 2>/dev/null || true
    cp "$REPO_CONF" "$NGINX_CONF"
    /usr/local/apps/nginx/sbin/nginx -t
    /usr/local/apps/nginx/sbin/nginx -s reload
  fi
fi

# 2. .bak = config qui FONCTIONNE (après patch)
if grep -q 'proxy_pass http://unix:/home/colobanes/analyse.yayematy.com/gunicorn.sock' "$NGINX_CONF"; then
  cp "$NGINX_CONF" "$NGINX_BAK"
  echo "→ .bak mis à jour (config Gunicorn OK) : $NGINX_BAK"
else
  echo "ATTENTION: patch Gunicorn non détecté — .bak non écrasé"
fi

# 3. Timer systemd (vérifie toutes les 3 minutes)
cp "$PROJECT_DIR/deploy/systemd/webuzo-nginx-guard.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/systemd/webuzo-nginx-guard.timer" /etc/systemd/system/
chmod +x "$PROJECT_DIR/deploy/fix-webuzo-nginx-yayematy.sh"
systemctl daemon-reload
systemctl enable webuzo-nginx-guard.timer
systemctl start webuzo-nginx-guard.timer

echo ""
echo "OK — Site réparé + garde automatique active."
echo "  Timer : systemctl status webuzo-nginx-guard.timer"
echo "  Logs  : journalctl -u webuzo-nginx-guard.service -n 20"
echo "  Test  : curl -Ik https://analyse.yayematy.com/"
echo ""
echo "Si Webuzo régénère webuzoVH.conf, le patch se réapplique en ≤ 3 min."
