#!/usr/bin/env bash
# Daily dump of the production database (run on the server).
#
# The prod Postgres lives in the `drinkx-postgres-1` container; until
# 23.10.2026 nothing dumped it, so a bad write could only be undone by
# hand from activity history. This keeps the last N daily dumps next to
# the stack. They live on the same disk — copy them off the server too.
#
# Usage:
#   ./backup-db.sh           # take a dump now, prune old daily dumps
#   ./backup-db.sh install   # add the daily cron entry (idempotent)
#
# Env: DRINKX_BACKUP_DIR (default /opt/drinkx-crm/backups),
#      DRINKX_BACKUP_KEEP_DAYS (default 14).
set -euo pipefail

DIR="${DRINKX_BACKUP_DIR:-/opt/drinkx-crm/backups}"
KEEP_DAYS="${DRINKX_BACKUP_KEEP_DAYS:-14}"
CONTAINER=drinkx-postgres-1
# Stable path: /opt/drinkx-crm/current follows every release.
SELF=/opt/drinkx-crm/current/infra/production/backup-db.sh
LOG=/var/log/drinkx-backup.log

if [[ "${1:-}" == "install" ]]; then
  line="15 3 * * * $SELF >> $LOG 2>&1"
  if crontab -l 2>/dev/null | grep -qF "$SELF"; then
    echo "cron entry already present"
  else
    (crontab -l 2>/dev/null; echo "$line") | crontab -
    echo "installed: $line"
  fi
  exit 0
fi

mkdir -p "$DIR"
chmod 700 "$DIR"
final="$DIR/drinkx_crm_daily_$(date -u +%Y%m%d).dump"
tmp="$final.partial"

docker exec "$CONTAINER" pg_dump -U drinkx -d drinkx_crm -Fc > "$tmp"
chmod 600 "$tmp"

# A dump that pg_restore can't list, or that has no table data, is not a backup.
tables="$(docker exec -i "$CONTAINER" pg_restore -l < "$tmp" | grep -c 'TABLE DATA' || true)"
if [[ "$tables" -lt 1 ]]; then
  echo "$(date -u +%FT%TZ) FAILED: dump has no table data, kept as $tmp" >&2
  exit 1
fi
mv "$tmp" "$final"

# Only daily dumps are pruned; hand-made ones (other names) stay.
find "$DIR" -maxdepth 1 -name 'drinkx_crm_daily_*.dump' -mtime +"$KEEP_DAYS" -delete

echo "$(date -u +%FT%TZ) ok $final $(du -h "$final" | cut -f1) tables=$tables"
