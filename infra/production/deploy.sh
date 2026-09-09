#!/usr/bin/env bash
# Deploy / update script — run on the server as the `deploy` user.
# Pulls latest main, rebuilds containers, restarts.
#
# Usage (on server):
#   /opt/drinkx-crm/infra/production/deploy.sh

set -euo pipefail
cd "$(dirname "$0")/../.."

# No `git fetch` here on purpose. The server reaches github.com only
# intermittently from its Russian datacenter, and a wedged fetch took down two
# deploys on 2026-07-14. CI now rsyncs the working tree in before calling this
# script (see .github/workflows/deploy.yml).
#
# Running this by hand deploys whatever is currently on disk. To deploy a
# specific commit by hand, put it there first — e.g. `git fetch && git reset
# --hard origin/main` — and expect that to hang whenever GitHub is unreachable.
#
# Don't read the commit from .git — rsync leaves it untouched, so it still
# points at whatever was last fetched here and would lie about what is live.
echo "==> Deploying ${DEPLOY_SHA:-working tree on disk (no SHA passed)}"

echo "==> Cleanup orphan rename stubs from prior partial runs"
docker ps -a --format '{{.Names}}' | grep -E '^[a-f0-9]+_drinkx-' | xargs -r docker rm -f || true

echo "==> Build + up"
cd infra/production
UP_RC=0
docker compose --env-file .env up -d --build --remove-orphans || UP_RC=$?

echo "==> Self-heal: start any containers left in Created state"
docker compose --env-file .env up -d || true

if [ "$UP_RC" -ne 0 ]; then
  echo "⚠ Initial 'up' exited with $UP_RC — self-heal attempted; falling through to health check"
fi

echo "==> Health check"
sleep 5
for i in 1 2 3 4 5; do
  if curl -fsS http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✓ API healthy"
    break
  fi
  echo "  waiting for API ($i/5)..."
  sleep 5
done

if curl -fsS http://127.0.0.1:3000 > /dev/null 2>&1; then
  echo "✓ Web reachable on :3000"
else
  echo "⚠ Web not yet reachable (may still be building)"
fi

# Plan 027: the API can be healthy while the Celery worker/beat silently failed
# to start (bad migration, import error in a task module, Redis misconfig) —
# which stops enrichment, follow-ups, daily plans and automations. Probe the
# worker with `celery inspect ping` (retried, since a cold worker boots slowly)
# and confirm the beat container is running. Fail the deploy if the worker
# never answers.
echo "==> Worker/beat health check"
WORKER_OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if docker compose --env-file .env exec -T worker \
      uv run celery -A app.scheduled.celery_app inspect ping -t 5 > /dev/null 2>&1; then
    echo "✓ Celery worker responds to ping"
    WORKER_OK=1
    break
  fi
  echo "  waiting for worker ($i/10)..."
  sleep 6
done
if [ "$WORKER_OK" -ne 1 ]; then
  echo "✗ Celery worker did not respond to inspect ping — background jobs are down" >&2
  docker compose ps
  exit 1
fi

if docker compose --env-file .env ps --status running beat | grep -q beat; then
  echo "✓ Celery beat container running"
else
  echo "✗ Celery beat container is not running" >&2
  docker compose ps
  exit 1
fi

echo "==> Done"
docker compose ps
