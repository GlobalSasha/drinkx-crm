#!/usr/bin/env bash
# Deploy / update script — run on the server as the `deploy` user.
# Pulls latest main, rebuilds containers, restarts.
#
# Usage (on server):
#   /opt/drinkx-crm/infra/production/deploy.sh

set -euo pipefail
cd "$(dirname "$0")/../.."

echo "==> Pull"
git fetch origin
git reset --hard origin/main

echo "==> Build + up"
cd infra/production
docker compose --env-file .env up -d --build --remove-orphans

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
