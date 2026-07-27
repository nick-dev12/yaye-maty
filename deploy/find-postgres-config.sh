#!/usr/bin/env bash
# Trouve les chemins postgresql.conf et pg_hba.conf (Webuzo, Debian, RHEL…)
#
# Usage sur le VPS :
#   sudo bash deploy/find-postgres-config.sh

set -euo pipefail

echo "=== Recherche configuration PostgreSQL ==="
echo ""

# 1) Demander à PostgreSQL s'il tourne (méthode la plus fiable)
if command -v psql >/dev/null 2>&1; then
  for RUN_AS in postgres root; do
    CONF=$(
      su -s /bin/bash "$RUN_AS" -c "psql -t -A -c 'SHOW config_file;'" 2>/dev/null \
        | tr -d '\r' | head -1 || true
    )
    HBA=$(
      su -s /bin/bash "$RUN_AS" -c "psql -t -A -c 'SHOW hba_file;'" 2>/dev/null \
        | tr -d '\r' | head -1 || true
    )
    if [[ -n "$CONF" && -f "$CONF" ]]; then
      echo "Via psql (user $RUN_AS) :"
      echo "  postgresql.conf : $CONF"
      echo "  pg_hba.conf     : ${HBA:-?}"
      echo ""
      DATA=$(dirname "$CONF")
      echo "  data_directory  : $DATA"
      exit 0
    fi
  done
fi

# 2) Processus postgres en cours (-D data dir)
PG_PROC=$(ps aux 2>/dev/null | grep '[p]ostgres.*-D' | head -1 || true)
if [[ -n "$PG_PROC" ]]; then
  DATA_DIR=$(echo "$PG_PROC" | sed -n 's/.*-D \([^ ]*\).*/\1/p')
  if [[ -n "$DATA_DIR" && -d "$DATA_DIR" ]]; then
    echo "Via processus postgres :"
    echo "  data_directory  : $DATA_DIR"
    [[ -f "$DATA_DIR/postgresql.conf" ]] && echo "  postgresql.conf : $DATA_DIR/postgresql.conf"
    [[ -f "$DATA_DIR/pg_hba.conf" ]] && echo "  pg_hba.conf     : $DATA_DIR/pg_hba.conf"
    exit 0
  fi
fi

# 3) Chemins Webuzo / EMPS + Debian / RHEL
echo "Recherche fichiers pg_hba.conf …"
mapfile -t CANDIDATES < <(
  find /usr/local/apps/postgresql* \
       /usr/local/pgsql* \
       /var/lib/pgsql* \
       /var/pgsql* \
       /etc/postgresql \
       -name pg_hba.conf 2>/dev/null | sort -u
)

if [[ ${#CANDIDATES[@]} -eq 0 ]]; then
  echo "Aucun pg_hba.conf trouvé."
  echo "Essayez : sudo find / -name pg_hba.conf 2>/dev/null"
  exit 1
fi

for HBA in "${CANDIDATES[@]}"; do
  DIR=$(dirname "$HBA")
  CONF="$DIR/postgresql.conf"
  echo "---"
  echo "  pg_hba.conf     : $HBA"
  [[ -f "$CONF" ]] && echo "  postgresql.conf : $CONF" || echo "  postgresql.conf : (absent dans $DIR)"
done

echo ""
echo "Webuzo : chemins fréquents sous /usr/local/apps/postgresql*/var/data/"
