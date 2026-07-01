# Plan 015: Automation step reliability — bounded retry for transient failures + a manual re-run / test-fire endpoint

> **Executor instructions**: Follow step by step; run every verification command.
> Honor STOP conditions. Update plan 015's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/automation_builder`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (touches the step execution + scheduling path; a retry bug could double-fire a side effect — idempotency matters)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `9e93b16`, 2026-07-01
- **Relates to**: round-2 backlog **B4** (automation cascade needs a depth/visited guard) — complementary; keep B4's guard in mind so a retry can't feed a cascade loop.

## Why this matters

An automation run has **no recovery path**. Step 0 fires synchronously; on failure the
chain "stops on step 0 failure — operator must rerun manually" — but nothing supports
a manual rerun. Scheduled steps 1+ that throw are marked `failed` with no re-attempt,
no backoff, no dead-letter. A transient blip (SMTP hiccup, DB deadlock, momentary
DeepSeek timeout) permanently kills the automation for that lead — the follow-up email
or task a manager configured simply never fires, with no alert beyond a `log.warning`.
Twenty models each step as an independent retryable queue job with a staled-run reaper.
We don't need that whole machine; we need two things: a **bounded retry on transient
step failures**, and an **operator endpoint to re-run / test-fire** an automation so
stranded runs are recoverable and new rules are testable without contriving real data.

## Current state

`apps/api/app/automation_builder/services.py`:
- Step 0 failure → `continue`, steps 1+ never scheduled (line 566):
  ```python
  if step0_failed_error:
      # Chain stops on step 0 failure. Steps 1+ stay
      # unscheduled — operator must rerun manually.
      continue
  ```
- Scheduled-step executor `execute_due_step_runs` (the `except` at line 1025):
  ```python
  except Exception as exc:
      step_run.status = "failed"
      step_run.error = str(exc)[:500]
      step_run.executed_at = datetime.now(tz=timezone.utc)
      ... # commit; log.warning("automation.step_run.failed", ...) — no retry
  ```
- Step run model + statuses: `apps/api/app/automation_builder/models.py` (per audit,
  `AutomationRun`/step-run rows at ~line 101; `StepRunStatus` literal is
  `pending|success|skipped|failed` in `schemas.py:17`).
- Routers (`apps/api/app/automation_builder/routers.py`): only
  `GET / POST / PATCH / DELETE / GET {id}/runs / GET runs steps`. **No** `/run`,
  `/rerun`, or `/test` endpoint. Write routes gate on `require_admin_or_head`.
- The step scheduler runs via Celery beat (`automation-step-scheduler` every 5 min,
  per `docs/brain/00_CURRENT_STATE.md`).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/automation_builder/services.py app/automation_builder/routers.py app/automation_builder/models.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/automation_builder` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_automation_reliability.py` | all pass |
| Migration (if added) | `cd apps/api && uv run alembic heads` | single head |

## Scope

**In scope:**
- `apps/api/app/automation_builder/services.py` (retry-on-transient in the step executor; a `rerun_run` / `test_fire` service fn)
- `apps/api/app/automation_builder/routers.py` (add `POST /{id}/test` and `POST /runs/{run_id}/rerun`)
- `apps/api/app/automation_builder/models.py` + a migration **only if** you add an
  `attempt_count` column to the step-run table (recommended for bounded retry)
- `apps/api/tests/test_automation_reliability.py` (create)

**Out of scope:**
- Rewriting the engine into per-step queue jobs (Twenty-style) — too large.
- Branching/conditional steps (separate backlog/direction item).
- The cascade depth guard — that is B4; do not implement it here, but ensure a rerun
  goes through the same trigger path so B4's future guard covers it.

## Git workflow

- Branch: `advisor/015-automation-reliability`
- Commit per step; e.g. `feat(automation): bounded step retry + manual rerun/test-fire (plan 015)`.

## Steps

### Step 1: Classify transient vs terminal step failures + bounded retry

Add an `attempt_count` (default 0) to the step-run model + a migration (next Alembic
index after the current head — run `uv run alembic heads` to find it). In
`execute_due_step_runs`' `except` (line 1025), instead of unconditionally marking
`failed`: if the error looks transient (SMTP/`EmailSendError`, DB `OperationalError`,
provider timeout — reuse any existing transient classification, e.g. from the email
sender's tri-state) **and** `attempt_count < _MAX_STEP_ATTEMPTS` (e.g. 3), leave the
step `pending`, bump `attempt_count`, and set `scheduled_at = now + backoff` so the
beat picks it up again. Only mark `failed` when terminal or attempts exhausted.

**Verify**: `grep -n "attempt_count\|_MAX_STEP_ATTEMPTS" app/automation_builder/services.py`
→ present. `python -m py_compile` → 0. `uv run alembic heads` → single head.

### Step 2: Rerun a failed/stranded run

Add `rerun_run(db, workspace_id, run_id)` in services: reset the run's failed/pending
steps (and, for a step-0 stall, schedule steps 1+ as originally intended) and let the
normal executor pick them up. Reuse the existing dispatch path — do **not** duplicate
`_dispatch_step` logic.

**Verify**: `grep -n "def rerun_run" app/automation_builder/services.py` → present.

### Step 3: Test-fire endpoint (author/debug loop)

Add `test_fire(db, workspace_id, automation_id, lead_id)` that runs the automation's
chain against a chosen lead **through the same execution path** as a real trigger, so
managers can validate a rule without moving real data. Guard side effects: reuse the
existing per-automation SAVEPOINT + post-commit email queue so a test that would send
email is subject to the same controls (or add a `dry_run` flag that records intended
steps as `skipped` with a reason — pick one and document it).

Add routes in `routers.py` (both `require_admin_or_head`):
- `POST /{id}/test` → `test_fire(...)` (body: `lead_id`)
- `POST /runs/{run_id}/rerun` → `rerun_run(...)`

**Verify**: `grep -n "/test\|/rerun" app/automation_builder/routers.py` → both present.
`python -m py_compile app/automation_builder/routers.py` → 0.

### Step 4: Tests

Create `tests/test_automation_reliability.py` (model after the existing
`tests/` automation tests — `grep -rln "automation" tests`). Cases: a transient step
failure stays `pending` and increments `attempt_count`; after `_MAX_STEP_ATTEMPTS` it
becomes `failed`; a terminal failure is `failed` immediately (no retry); `rerun_run`
re-schedules a failed run's steps; `test_fire` executes without mutating real lead
state when `dry_run` (or is SAVEPOINT-isolated).

**Verify**: `cd apps/api && uv run pytest -q tests/test_automation_reliability.py` → all pass.

## Test plan

- New `tests/test_automation_reliability.py`, ~5 cases (Step 4).
- Pattern: existing automation service tests.
- Verification: pytest command passes; `alembic heads` single head if a migration was added.

## Done criteria

- [ ] `python -m py_compile` on the touched files → 0
- [ ] `uv run ruff check app/automation_builder` → 0
- [ ] `uv run pytest -q tests/test_automation_reliability.py` → all pass (≥5 new)
- [ ] `uv run alembic heads` → single head (if `attempt_count` migration added)
- [ ] `POST /{id}/test` and `POST /runs/{run_id}/rerun` exist and are `require_admin_or_head`
- [ ] Transient step failures retry with backoff; terminal ones do not (asserted)
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` round-3 row for 015 updated

## STOP conditions

- Excerpts don't match live code (drift) — report.
- A retried step is **not idempotent** (e.g. `create_task` would create a duplicate
  task on re-attempt) — STOP and design idempotency (dedupe key / "already-fired"
  check) before enabling retry for that action type. Double-sending email on retry is
  the worst case — verify the post-commit email queue can't double-dispatch.
- Adding retry requires touching the cascade path such that it could loop (B4) — STOP;
  land B4's depth guard first or coordinate.

## Maintenance notes

- Keep `_MAX_STEP_ATTEMPTS` small (3) and backoff bounded; this is transient-failure
  recovery, not infinite retry.
- Reviewer must focus on **idempotency** of each retryable action and on the
  test-fire not leaking real side effects.
- Natural follow-ups: surface run status + a "Re-run" button in the automations UI
  (`apps/web/app/(app)/automations/page.tsx`); and B4's cascade depth guard.
