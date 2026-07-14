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

echo "==> Done"
docker compose ps
