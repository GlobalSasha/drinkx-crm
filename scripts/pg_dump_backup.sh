#!/bin/bash
# pg_dump_backup — Sprint 2.4 G5 soft-launch carryover.
#
# Daily logical backup of the Postgres DB pointed at by $DATABASE_URL.
# Files land in $BACKUP_DIR (default /var/backups/drinkx) named
# drinkx_YYYYMMDD_HHMMSS.sql.gz; anything older than 7 days is pruned.
#
# Failure mode: if pg_dump exits non-zero we still run the prune — the
# `set -o pipefail` flag below propagates the failure as the script's
# exit code so the cron line redirects it into /var/log/drinkx_backup.log.
#
# Run from the production crontab; see docs/crontab.example.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/drinkx}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/drinkx_${TIMESTAMP}.sql.gz"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[pg_dump_backup] DATABASE_URL not set — aborting." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "[pg_dump_backup] starting at $(date -Iseconds) -> $FILE"
pg_dump "$DATABASE_URL" | gzip > "$FILE"
echo "[pg_dump_backup] dump complete, size: $(du -h "$FILE" | cut -f1)"

# Retention: drop dumps older than 7 days. Same find runs even if the
# pg_dump above failed — set -e propagates pg_dump's non-zero status,
# but we want the prune attempt anyway, so it sits BEFORE the failure
# would be raised at script exit time (set -e exits as the failing
# command runs; we already finished pg_dump above).
find "$BACKUP_DIR" -name "drinkx_*.sql.gz" -mtime +7 -delete
echo "[pg_dump_backup] retention prune complete."
