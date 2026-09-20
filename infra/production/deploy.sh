#!/usr/bin/env bash
# Deploy / update script — run on the server as the `deploy` user.
# Rebuilds the images from the code on disk, restarts, and refuses to report
# success unless the expected build is the one actually running.
#
# Usage (on server):
#   DEPLOY_SHA=<git sha> /opt/drinkx-crm/infra/production/deploy.sh
#
# Exit codes: 0 only on a fully verified release. Any build, start, health or
# version failure exits non-zero. The last line is always DEPLOY_RESULT=<state>.
#
# Regression tests: infra/production/tests/test_deploy_release_gate.py

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
#
# Identity is proven from the IMAGES, not from the containers' environment.
# `docker run -e DRINKX_GIT_SHA=...` can override an ENV at start-up, so a
# container that answers with the right string proves nothing. Each image
# instead carries the OCI label org.opencontainers.image.revision, set from the
# GIT_SHA build arg; labels belong to the image and cannot be set at run time.
# The gate records the image IDs produced by this build, then checks that every
# running container was started from exactly those images and that their labels
# match the requested commit.
#
# This proves WHICH BUILD is running. It does not prove the build context was
# clean — a file deleted from git can survive on the server (audit DEBT-01/G4).

DEPLOY_SHA="${DEPLOY_SHA:-}"
if [ -n "$DEPLOY_SHA" ]; then
  VERIFY_VERSION=1
  echo "==> Deploying $DEPLOY_SHA"
else
  VERIFY_VERSION=0
  echo "==> Deploying working tree on disk (no DEPLOY_SHA passed)"
  echo "⚠ Without DEPLOY_SHA the running build cannot be verified."
  echo "  This run can report 'unverified' at best, never 'success'."
fi

# Bound every probe so a hung daemon or socket cannot stall the release.
# `timeout` is coreutils — present on the Ubuntu server, absent on stock macOS,
# where the tests run. Degrade to an unbounded call rather than failing there.
run_bounded() {
  local secs="$1"; shift
  if command -v timeout > /dev/null 2>&1; then
    timeout "$secs" "$@"
  else
    "$@"
  fi
}

# Compose project name — `name: drinkx` in docker-compose.yml. Used only as a
# fallback when `compose config --images` is unavailable.
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-drinkx}"
BUILT_SERVICES="api web worker beat"

# Image reference compose uses for a built service (project-service by default).
compose_image_ref() {
  local svc="$1" ref=""
  ref="$(run_bounded 30 docker compose --env-file .env config --images "$svc" \
           2>/dev/null | head -n 1 | tr -d '\r' || true)"
  [ -n "$ref" ] || ref="${COMPOSE_PROJECT}-${svc}"
  printf '%s' "$ref"
}

# Full image ID for a reference or ID.
image_id_of() {
  run_bounded 30 docker image inspect --format '{{.Id}}' "$1" \
    2>/dev/null | head -n 1 | tr -d '\r' || true
}

# Revision recorded IN THE IMAGE at build time.
image_revision_of() {
  run_bounded 30 docker image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1" \
    2>/dev/null | head -n 1 | tr -d '\r' || true
}

# Image ID a running container was actually started from.
container_image_of() {
  local svc="$1" cid=""
  cid="$(run_bounded 30 docker compose --env-file .env ps -q "$svc" \
           2>/dev/null | head -n 1 | tr -d '\r' || true)"
  [ -n "$cid" ] || return 0
  run_bounded 30 docker inspect --format '{{.Image}}' "$cid" \
    2>/dev/null | head -n 1 | tr -d '\r' || true
}

fail() {
  echo "✗ $1" >&2
  echo "--- container state at failure ---" >&2
  docker compose ps >&2 || true
  echo "DEPLOY_RESULT=failed"
  exit 1
}

echo "==> Cleanup orphan rename stubs from prior partial runs"
docker ps -a --format '{{.Names}}' | grep -E '^[a-f0-9]+_drinkx-' | xargs -r docker rm -f || true

cd infra/production

# ---------------------------------------------------------------------------
# 1. Build. A failed build is a failed release, full stop.
#
# Before G1 this was fused with `up` as `up -d --build || UP_RC=$?`, and a
# non-zero result only printed a warning. The old containers then answered
# every health check and the script exited 0 — a green deploy of the previous
# release. Build is now its own step and its failure is terminal.
# ---------------------------------------------------------------------------
echo "==> Build images"
if ! docker compose --env-file .env build \
       --build-arg GIT_SHA="${DEPLOY_SHA:-unknown}"; then
  fail "image build failed — the previous release is still running, nothing was replaced"
fi

# Record what the build produced, before anything is started. If `up` later
# leaves an old container in place, the comparison below catches it.
if [ "$VERIFY_VERSION" -eq 1 ]; then
  echo "==> Record images produced by this build"
  for svc in $BUILT_SERVICES; do
    ref="$(compose_image_ref "$svc")"
    built_id="$(image_id_of "$ref")"
    if [ -z "$built_id" ]; then
      fail "could not resolve the image built for '$svc' (looked for '$ref')"
    fi
    built_rev="$(image_revision_of "$built_id")"
    if [ -z "$built_rev" ] || [ "$built_rev" = "unknown" ]; then
      fail "image for '$svc' carries no usable org.opencontainers.image.revision label"
    fi
    if [ "$built_rev" != "$DEPLOY_SHA" ]; then
      fail "image for '$svc' is labelled '$built_rev', expected '$DEPLOY_SHA' — this build is not the requested release"
    fi
    eval "EXPECTED_IMAGE_${svc}=\$built_id"
    echo "  ✓ $svc built as $built_id"
  done
fi

# ---------------------------------------------------------------------------
# 2. Start the freshly built images.
# ---------------------------------------------------------------------------
echo "==> Start containers"
if ! docker compose --env-file .env up -d --remove-orphans; then
  echo "⚠ First 'up' failed — retrying once for containers left in Created state"
  if ! docker compose --env-file .env up -d; then
    fail "containers could not be started"
  fi
fi

# ---------------------------------------------------------------------------
# 3. Health. Every probe below is mandatory: exhausting the retry budget is a
#    failure, not a warning. Web used to warn and continue, and the API loop
#    used to fall through silently once its five attempts were spent.
# ---------------------------------------------------------------------------
echo "==> Health check"
sleep 5

API_OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 10 http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✓ API healthy"
    API_OK=1
    break
  fi
  echo "  waiting for API ($i/10)..."
  sleep 5
done
[ "$API_OK" -eq 1 ] || fail "API did not become healthy on :8000/health"

# "/" is an entry point, not a page: middleware 307s it to /today or /sign-in
# depending on the session, and `curl -f` treats a 3xx as success. Probing it
# would accept a redirect as proof the app renders. /sign-in returns a real 200.
WEB_OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 10 http://127.0.0.1:3000/sign-in > /dev/null 2>&1; then
    echo "✓ Web reachable on :3000"
    WEB_OK=1
    break
  fi
  echo "  waiting for Web ($i/10)..."
  sleep 5
done
[ "$WEB_OK" -eq 1 ] || fail "Web did not become reachable on :3000"

# Plan 027: the API can be healthy while the Celery worker/beat silently failed
# to start (bad migration, import error in a task module, Redis misconfig) —
# which stops enrichment, follow-ups, daily plans and automations. Probe the
# worker with `celery inspect ping` (retried, since a cold worker boots slowly)
# and confirm the beat container is running.
echo "==> Worker/beat health check"
WORKER_OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if run_bounded 30 docker compose --env-file .env exec -T worker \
      uv run celery -A app.scheduled.celery_app inspect ping -t 5 > /dev/null 2>&1; then
    echo "✓ Celery worker responds to ping"
    WORKER_OK=1
    break
  fi
  echo "  waiting for worker ($i/10)..."
  sleep 6
done
[ "$WORKER_OK" -eq 1 ] || fail "Celery worker did not respond to inspect ping — background jobs are down"

if run_bounded 30 docker compose --env-file .env ps --status running beat | grep -q beat; then
  echo "✓ Celery beat container running"
else
  fail "Celery beat container is not running"
fi

# ---------------------------------------------------------------------------
# 4. Identity. Healthy is not the same as new: every check above is satisfied
#    by the previous release. Confirm each running container was started from
#    the image this build produced, and that the image's own label names the
#    requested commit. Deliberately NOT read from the container environment,
#    which a runtime -e flag can set to anything.
# ---------------------------------------------------------------------------
if [ "$VERIFY_VERSION" -eq 1 ]; then
  echo "==> Verify running images"
  for svc in $BUILT_SERVICES; do
    eval "expected_id=\$EXPECTED_IMAGE_${svc}"
    running_id="$(container_image_of "$svc")"
    if [ -z "$running_id" ]; then
      fail "no running container for '$svc' — cannot verify which image is live"
    fi
    running_rev="$(image_revision_of "$running_id")"
    if [ "$running_id" != "$expected_id" ]; then
      fail "'$svc' runs image $running_id (revision '${running_rev:-none}'), not the image built for this release ($expected_id)"
    fi
    if [ -z "$running_rev" ] || [ "$running_rev" = "unknown" ]; then
      fail "'$svc' runs an image with no usable revision label — cannot prove the release"
    fi
    if [ "$running_rev" != "$DEPLOY_SHA" ]; then
      fail "'$svc' runs revision '$running_rev', expected '$DEPLOY_SHA' — the new release is NOT live"
    fi
    echo "  ✓ $svc runs $running_rev"
  done
fi

echo "==> Done"
docker compose ps || true

if [ "$VERIFY_VERSION" -eq 1 ]; then
  echo "DEPLOY_RESULT=success"
else
  echo "DEPLOY_RESULT=unverified"
  exit 0
fi
