#!/usr/bin/env bash
# Build the project's real images and prove the deploy gate's identity claim.
#
# The gate decides what is running by reading an image's OCI revision label.
# That is only sound if two things hold, and both are checked here against
# actual Docker rather than stubs:
#
#   1. every service image really is labelled with the commit it was built from;
#   2. a runtime `-e DRINKX_GIT_SHA=...` cannot move that label.
#
# Nothing is started: no application, no migrations, no Celery worker, no
# published ports, no production volumes. Images are built and inspected.
#
# Runs in CI (.github/workflows/quality.yml, job `docker-smoke`) and locally on
# any machine with Docker:
#
#     infra/production/tests/check_image_identity.sh <full-git-sha>
#
# It writes a throwaway infra/production/.env with synthetic values, because
# compose validates the whole configuration before it will build anything.
# It refuses to run if a real .env is already there.

set -euo pipefail

EXPECTED="${1:-}"
if [ -z "$EXPECTED" ]; then
  echo "usage: $0 <full-git-sha>" >&2
  exit 2
fi

cd "$(dirname "$0")/../../.." || exit 1
cd infra/production

if [ -f .env ]; then
  echo "✗ infra/production/.env already exists — refusing to overwrite it." >&2
  echo "  This check writes a throwaway env file; move the real one aside first." >&2
  exit 1
fi

cleanup() { rm -f .env; }
trap cleanup EXIT

cat > .env <<'ENVEOF'
POSTGRES_USER=ci
POSTGRES_PASSWORD=ci-not-a-real-password
POSTGRES_DB=ci_smoke
SUPABASE_URL=https://example.invalid
SUPABASE_PUBLISHABLE_KEY=ci-fake
SUPABASE_SECRET_KEY=ci-fake
SUPABASE_JWT_SECRET=ci-fake
MIMO_API_KEY=ci-fake
ANTHROPIC_API_KEY=ci-fake
GEMINI_API_KEY=ci-fake
DEEPSEEK_API_KEY=ci-fake
OPENAI_API_KEY=ci-fake
BRAVE_API_KEY=ci-fake
APIFY_TOKEN=ci-fake
SENTRY_DSN_API=
SENTRY_DSN_WEB=
GOOGLE_CLIENT_ID=ci-fake
GOOGLE_CLIENT_SECRET=ci-fake
API_BASE_URL=https://example.invalid
FRONTEND_BASE_URL=https://example.invalid
ENVEOF

echo "==> Building every service image at $EXPECTED"
docker compose --env-file .env build --build-arg GIT_SHA="$EXPECTED"

echo "==> Checking each image is labelled with this commit"
for svc in api web worker beat; do
  ref="$(docker compose --env-file .env config --images "$svc" | head -n 1)"
  id="$(docker image inspect --format '{{.Id}}' "$ref")"
  rev="$(docker image inspect \
          --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$id")"
  echo "  $svc: ref=$ref id=$id revision=$rev"
  if [ -z "$rev" ]; then
    echo "✗ $svc image carries no revision label" >&2
    exit 1
  fi
  if [ "$rev" != "$EXPECTED" ]; then
    echo "✗ $svc image is labelled '$rev', expected '$EXPECTED'" >&2
    exit 1
  fi
done

echo "==> Checking a runtime override cannot forge the revision"
FORGED=0000000000000000000000000000000000000000
ref="$(docker compose --env-file .env config --images api | head -n 1)"
id="$(docker image inspect --format '{{.Id}}' "$ref")"

env_says="$(docker run --rm --network none --entrypoint printenv \
              -e DRINKX_GIT_SHA="$FORGED" "$id" DRINKX_GIT_SHA)"
label_says="$(docker image inspect \
               --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$id")"

echo "  container environment says: $env_says"
echo "  image label says          : $label_says"

if [ "$env_says" != "$FORGED" ]; then
  echo "✗ the override did not take effect, so this check proves nothing" >&2
  exit 1
fi
if [ "$label_says" != "$EXPECTED" ]; then
  echo "✗ the label moved with the runtime override — identity is forgeable" >&2
  exit 1
fi

echo
echo "OK: all four images labelled $EXPECTED; the label held while the environment lied"
