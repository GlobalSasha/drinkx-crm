#!/usr/bin/env bash
# Quick log viewer for the DrinkX CRM prod stack (run on the server).
#
# Logs are JSON lines, available two ways:
#   - docker stdout (rotated 10MB×5)  → this script reads these
#   - /app/logs/app-<service>.log     → read by GET /api/admin/logs (for agents)
#
# Usage:
#   ./logs.sh errors [service] [since]   # errors/tracebacks (default: all, 1h)
#   ./logs.sh tail   <service>           # live tail (api|worker|beat|web|...)
#   ./logs.sh digest [since]             # counts by level
set -euo pipefail
cd "$(dirname "$0")"
DC=(docker compose --env-file .env)

cmd="${1:-errors}"; shift || true
case "$cmd" in
  errors)
    svc="${1:-}"; since="${2:-1h}"
    echo "== errors (last $since)${svc:+ · service=$svc} =="
    "${DC[@]}" logs --since "$since" --no-log-prefix ${svc:+"$svc"} 2>/dev/null \
      | grep -iE '"level": ?"(error|critical)"|traceback|exception' \
      || echo "(ошибок не найдено)"
    ;;
  tail)
    svc="${1:?usage: logs.sh tail <service>}"
    "${DC[@]}" logs -f --tail 100 "$svc"
    ;;
  digest)
    since="${1:-1h}"
    echo "== digest (last $since) · строк по уровням =="
    "${DC[@]}" logs --since "$since" 2>/dev/null \
      | grep -oE '"level": ?"[a-z]+"' | sort | uniq -c | sort -rn \
      || echo "(пусто)"
    ;;
  *)
    echo "usage: logs.sh [errors [service] [since] | tail <service> | digest [since]]"
    exit 1
    ;;
esac
