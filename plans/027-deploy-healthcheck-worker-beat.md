# Plan 027: Deploy health check must cover the Celery worker and beat, not just web+API

> **Executor instructions**: Follow step by step. Honor STOP conditions. Update
> this plan's row in `plans/README.md`. This touches CI/deploy — verify by
> reading the workflow and (if possible) a dry-run, never by triggering a real
> production deploy.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- .github/workflows/deploy.yml infra/production/deploy.sh apps/api/app/main.py`
> Compare against "Current state"; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (a too-strict check can flap and block deploys)
- **Depends on**: none
- **Category**: dx / reliability
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

The deploy workflow verifies only the web page and the API health endpoint. It
never checks the Celery **worker** or **beat**, even though enrichment,
follow-ups, daily plans, and automations all depend on them. A deploy where the
worker or beat container fails to start (bad migration, import error in a task
module, Redis misconfig) still reports "✅ Deploy verified" and goes green while
all background automation is silently dead. This makes a whole class of outages
invisible at deploy time.

## Current state

- `.github/workflows/deploy.yml:70-90` — the health check is two HTTP probes
  with a 20×3s retry `check()` helper:
  ```bash
  check "Web" https://crm.drinkx.tech/sign-in || exit 1
  check "API" https://crm.drinkx.tech/api/health || exit 1
  echo "✅ Deploy verified"
  ```
  No worker/beat probe.
- `infra/production/deploy.sh` — `git pull` + `docker compose build` of `web`,
  `api`, `worker`, `beat`, then the health checks. The worker and beat run in
  the same image as the API.
- `apps/api/app/main.py` — the API app; `/api/health` (or `/health`) endpoint
  is defined here (grep `health`). The worker/beat have no HTTP surface.

## Commands you will need

| Purpose            | Command                                                       | Expected |
|--------------------|---------------------------------------------------------------|----------|
| Read workflow      | `sed -n '60,95p' .github/workflows/deploy.yml`               | current check |
| Find health route  | `grep -rn "health" apps/api/app/main.py`                     | endpoint def |
| YAML lint (if avail)| `yamllint .github/workflows/deploy.yml` (skip if not installed) | no errors |

## Scope

**In scope** (pick ONE of the two approaches below):
- `.github/workflows/deploy.yml` — add a worker/beat liveness gate
- AND EITHER:
  - `infra/production/deploy.sh` — run `celery -A <app> inspect ping` over SSH
    and fail the deploy if no worker responds, OR
  - `apps/api/app/main.py` (+ a small helper) — expose worker/beat last-
    heartbeat in the health endpoint so the existing HTTP check covers it
- `apps/api/app/scheduled/` or wherever beat runs — IF the heartbeat approach:
  a periodic task that writes a "beat alive" timestamp to Redis/DB

**Out of scope**:
- Rewriting the deploy pipeline.
- Changing what the worker actually runs.
- Triggering a real deploy to test (verify by reading + a non-prod dry run).

## Steps

### Decide the approach

- **Approach 1 (simplest): `celery inspect ping` over SSH.** In the SSH block
  of `deploy.sh` (or a new workflow step), run
  `docker compose exec -T worker celery -A app.celery_app inspect ping -d celery@$HOSTNAME`
  (confirm the actual Celery app path by grepping
  `grep -rn "Celery(" apps/api/app`) with a retry loop mirroring the existing
  `check()` helper. Non-zero → fail the deploy.
- **Approach 2 (observable at runtime too): heartbeat in `/api/health`.** A
  beat task writes `worker_last_seen` / `beat_last_seen` timestamps to Redis;
  the health endpoint reports them; the workflow asserts they are recent
  (< N minutes). More work but also gives ongoing observability.

Recommended: **Approach 1** for this plan (contained, no runtime changes),
with Approach 2 noted as a follow-up.

### Implement Approach 1

Add a retrying worker probe to the health-check step. Mirror the existing
`check()` retry (20 attempts, 3s) so a slow worker boot doesn't false-fail.
Fail the deploy (`exit 1`) if the worker never answers `inspect ping`.
Add a beat check too if beat exposes a schedulable ping; if not, at least
assert the beat container is `Up` via `docker compose ps --status running beat`.

**Verify**: read the final workflow; the `celery ... inspect ping` (or
`compose ps`) gate is present and gated with `|| exit 1`. If `yamllint` or
`act` is available, dry-run/lint the workflow. Do NOT trigger a real deploy.

## Done criteria

- [ ] `deploy.yml` (or `deploy.sh`) probes the Celery worker and fails on no response
- [ ] The probe uses a retry loop (no single-shot false-fail on slow boot)
- [ ] The correct Celery app path is used (verified via grep, not guessed)
- [ ] Workflow YAML is syntactically valid (lint if a linter is available)
- [ ] No application behavior changed (Approach 1) — or heartbeat task added and tested (Approach 2)
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- The Celery app import path can't be confirmed from the code — STOP and
  report; a wrong path makes `inspect ping` always fail and blocks all deploys.
- `docker compose exec` isn't available in the deploy context (e.g. the SSH
  user lacks permissions) — report and fall back to `compose ps --status running`.
- Any change would require triggering a real prod deploy to validate — STOP;
  validate by reading + non-prod dry run only.

## Maintenance notes

- If the worker/beat move to a separate image or host, the probe target must
  follow.
- Reviewer: confirm the probe can't false-green (e.g. `inspect ping` timing out
  must be treated as failure, not success), and that the retry budget is long
  enough for a cold worker start but not so long it masks a real crash.
- Follow-up: Approach 2 (heartbeat in `/api/health`) gives runtime
  observability beyond deploy time — worth doing later.
