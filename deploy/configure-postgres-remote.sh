#!/usr/bin/env bash
# Autorise PostgreSQL à accepter des connexions distantes (Webuzo / Debian / RHEL).
#
# Usage sur le VPS (root) :
#   sudo bash deploy/find-postgres-config.sh          # voir les chemins
#   sudo bash deploy/configure-postgres-remote.sh all # toutes les IP

set -euo pipefail

REMOTE_ARG="${1:-}"
DB_NAME="${DB_NAME:-colobanes_yaye}"
DB_USER="${DB_USER:-colobanes_jomas}"

if [[ -z "$REMOTE_ARG" ]]; then
  echo "Usage:"
  echo "  sudo bash $0 all                 # toutes les IP (0.0.0.0/0)"
  echo "  sudo bash $0 VOTRE_IP            # une IP seulement"
  echo ""
  echo "Chemins inconnus ? sudo bash deploy/find-postgres-config.sh"
  exit 1
fi

if [[ "$REMOTE_ARG" == "all" || "$REMOTE_ARG" == "0.0.0.0/0" ]]; then
  PG_HBA_CIDR="0.0.0.0/0"
  MARKER="# yayematy-remote-all"
  UFW_RULE="global"
else
  if [[ ! "$REMOTE_ARG" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Argument invalide: $REMOTE_ARG (utilisez 'all' ou une IPv4)"
    exit 1
  fi
  PG_HBA_CIDR="${REMOTE_ARG}/32"
  MARKER="# yayematy-remote-${REMOTE_ARG}"
  UFW_RULE="single"
fi

discover_pg_config() {
  local conf="" hba=""

  if command -v psql >/dev/null 2>&1; then
    for run_as in postgres root; do
      conf=$(su -s /bin/bash "$run_as" -c "psql -t -A -c 'SHOW config_file;'" 2>/dev/null | tr -d '\r' | head -1 || true)
      hba=$(su -s /bin/bash "$run_as" -c "psql -t -A -c 'SHOW hba_file;'" 2>/dev/null | tr -d '\r' | head -1 || true)
      if [[ -n "$conf" && -f "$conf" && -n "$hba" && -f "$hba" ]]; then
        echo "$conf|$hba"
        return 0
      fi
    done
  fi

  local proc data_dir
  proc=$(ps aux 2>/dev/null | grep '[p]ostgres.*-D' | head -1 || true)
  if [[ -n "$proc" ]]; then
    data_dir=$(echo "$proc" | sed -n 's/.*-D \([^ ]*\).*/\1/p')
    if [[ -n "$data_dir" && -f "$data_dir/postgresql.conf" && -f "$data_dir/pg_hba.conf" ]]; then
      echo "$data_dir/postgresql.conf|$data_dir/pg_hba.conf"
      return 0
    fi
  fi

  local search_paths=(
    /usr/local/apps/postgresql*/var/data
    /usr/local/apps/postgresql*/data
    /usr/local/pgsql*/data
    /var/lib/pgsql/data
    /var/lib/pgsql/*/data
    /etc/postgresql/*/main
  )
  local dir hba_path conf_path
  for pattern in "${search_paths[@]}"; do
    for dir in $pattern; do
      [[ -d "$dir" ]] || continue
      hba_path="$dir/pg_hba.conf"
      conf_path="$dir/postgresql.conf"
      if [[ -f "$hba_path" && -f "$conf_path" ]]; then
        echo "$conf_path|$hba_path"
        return 0
      fi
    done
  done

  mapfile -t found < <(find /usr/local/apps/postgresql* /var/lib/pgsql /etc/postgresql \
    -name pg_hba.conf 2>/dev/null | head -1)
  if [[ ${#found[@]} -gt 0 && -f "${found[0]}" ]]; then
    hba_path="${found[0]}"
    conf_path="$(dirname "$hba_path")/postgresql.conf"
    if [[ -f "$conf_path" ]]; then
      echo "$conf_path|$hba_path"
      return 0
    fi
  fi

  return 1
}

RESULT=$(discover_pg_config || true)
if [[ -z "$RESULT" ]]; then
  echo "Impossible de localiser postgresql.conf / pg_hba.conf."
  echo "Lancez : sudo bash deploy/find-postgres-config.sh"
  exit 1
fi

PG_CONF="${RESULT%%|*}"
PG_HBA="${RESULT##*|}"

echo "→ postgresql.conf : $PG_CONF"
echo "→ pg_hba.conf     : $PG_HBA"
echo "→ Autorisation    : $PG_HBA_CIDR"
echo "→ Base / user     : $DB_NAME / $DB_USER"

# listen_addresses
if grep -qE '^[#[:space:]]*listen_addresses' "$PG_CONF"; then
  sed -i "s/^[#[:space:]]*listen_addresses.*/listen_addresses = '*'/" "$PG_CONF"
else
  echo "listen_addresses = '*'" >> "$PG_CONF"
fi

# pg_hba
sed -i '/# yayematy-remote-/d' "$PG_HBA"
if ! grep -q "$MARKER" "$PG_HBA" 2>/dev/null; then
  echo "" >> "$PG_HBA"
  echo "$MARKER" >> "$PG_HBA"
  echo "host    ${DB_NAME}    ${DB_USER}    ${PG_HBA_CIDR}    scram-sha-256" >> "$PG_HBA"
  echo "→ Règle pg_hba ajoutée."
fi

reload_postgres() {
  if command -v pg_ctl >/dev/null 2>&1; then
    local data_dir
    data_dir=$(dirname "$PG_CONF")
    su -s /bin/bash postgres -c "pg_ctl reload -D '$data_dir'" 2>/dev/null && return 0
  fi
  for svc in postgresql postgresql-16 postgresql-15 postgresql-14; do
    if systemctl restart "$svc" 2>/dev/null; then
      echo "→ Service redémarré : $svc"
      return 0
    fi
  done
  if [[ -x /etc/init.d/postgresql ]]; then
    /etc/init.d/postgresql restart
    echo "→ /etc/init.d/postgresql restart"
    return 0
  fi
  # Webuzo EMPS
  if [[ -x /usr/local/emps/sbin/postgresql ]]; then
    /usr/local/emps/sbin/postgresql restart 2>/dev/null || true
  fi
  echo "→ Redémarrez PostgreSQL depuis Webuzo : Admin → Services → PostgreSQL"
}

reload_postgres

if command -v ufw >/dev/null 2>&1; then
  if [[ "$UFW_RULE" == "global" ]]; then
    ufw allow 5432/tcp comment 'PostgreSQL YAYEMATY'
    echo "→ UFW : port 5432 ouvert"
  else
    ufw allow from "$REMOTE_ARG" to any port 5432 proto tcp
    echo "→ UFW : port 5432 pour $REMOTE_ARG"
  fi
fi

echo ""
echo "OK — Test PC : .\\scripts\\test-vps-db.ps1"
echo "Pare-feu Contabo : TCP 5432 entrant si besoin."
