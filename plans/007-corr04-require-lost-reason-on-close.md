# Plan 007: Require a non-empty lost_reason when closing a deal as Lost

> **Executor instructions**: Follow step by step. Run every verification command
> and confirm the expected result before the next step. On any "STOP conditions"
> item, stop and report. Update this plan's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat a81462c..HEAD -- apps/api/app/leads/services.py apps/api/app/leads/routers.py`
> If either changed, compare against "Current state"; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `a81462c`, 2026-06-20

## Why this matters

`lost_reason` is optional at every layer, so deals can be closed-lost with no reason. The loss-reason retrospective the UI advertises ("почему мы теряем HoReCa?") is therefore sparse and unreliable. The engine already has a precedent for a required reason — when a manager force-skips a stage gate, `skip_reason` is mandatory and a missing one raises `ValueError` (→ HTTP 400). This plan mirrors that guard for the lost path. (Backing it with a structured reason enum for aggregation is a larger follow-up, intentionally out of scope here.)

## Current state

- `apps/api/app/leads/services.py:403` — `move_lead_stage` resolves the destination `to_stage` (a `Stage` with `is_lost: bool`) from the DB, then optionally records `lost_reason`:

```python
# apps/api/app/leads/services.py (inside move_lead_stage)
    to_stage = stage_result.scalar_one_or_none()
    if to_stage is None:
        raise StageNotFound(to_stage_id)

    if lost_reason is not None:
        lead.lost_reason = lost_reason
    ...
```

- **Exemplar guard** to mirror (same file family), in `apps/api/app/automation/stage_change.py:287`:

```python
    if gate_skipped and not (skip_reason and skip_reason.strip()):
        raise ValueError("skip_reason is required when gate_skipped=True")
```

- The router already maps `ValueError` → HTTP 400 (`apps/api/app/leads/routers.py:441`):

```python
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
```

- Frontend `apps/web/components/lead-card/LostModal.tsx` currently labels the field "(необязательно)" and sends `null` when empty — after this change it must require the field (see Step 3).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/leads/services.py` | exit 0 |
| Backend tests | `cd apps/api && uv run pytest -q tests/test_stage_change.py -k "lost"` | pass (Postgres-gated; runs in CI) |
| Frontend gate | `cd apps/web && npm run typecheck && npm run lint` | exit 0 |

## Scope

**In scope:**
- `apps/api/app/leads/services.py` — add the guard in `move_lead_stage`.
- `apps/web/components/lead-card/LostModal.tsx` — make the reason required in the UI.
- `apps/api/tests/test_stage_change.py` — add a "lost without reason → error" case (Postgres-gated, matching the file's existing integration style).

**Out of scope (do NOT touch):**
- A structured reason enum / loss-reason reporting — separate, larger plan.
- The won path and gate-skip path — unchanged.

## Git workflow

- Branch: `advisor/007-require-lost-reason`
- Commit e.g. `fix(leads): require lost_reason when closing a deal as lost`.
- Do NOT push/PR unless instructed.

## Steps

### Step 1: Add the server guard

In `move_lead_stage`, after `to_stage` is resolved and before/where `lost_reason` is applied, add:

```python
    if to_stage.is_lost and not (lost_reason and lost_reason.strip()):
        raise ValueError("lost_reason is required when closing a deal as lost")
    if lost_reason is not None:
        lead.lost_reason = lost_reason
```

**Verify**: `grep -n "lost_reason is required" apps/api/app/leads/services.py` → 1 match. `python -m py_compile app/leads/services.py` → exit 0.

### Step 2: Add a backend test

In `apps/api/tests/test_stage_change.py`, add an integration test (it can reuse the file's `_make_lead`/stage helpers and `skip_no_pg` marker): moving a lead to a lost stage with `lost_reason=None` raises (maps to 400 at the API); with a non-empty reason it succeeds and `lead.lost_reason` is set.

**Verify** (where Postgres is available): `cd apps/api && uv run pytest -q tests/test_stage_change.py -k "lost"` → pass. Where Postgres is absent the test is skipped — that's expected (`POSTGRES_AVAILABLE`).

### Step 3: Make the UI field required

In `apps/web/components/lead-card/LostModal.tsx`: change the label from "(необязательно)" to required, disable the confirm button while the reason is empty/whitespace, and stop sending `null` (send the trimmed reason). Match the modal's existing button-disable pattern (e.g. how other required modals gate their submit).

**Verify**: `cd apps/web && npm run typecheck && npm run lint` → exit 0. Manually: the Lost confirm button is disabled until a reason is typed.

## Test plan

- Backend: lost-without-reason → error; lost-with-reason → success + `lost_reason` persisted (`tests/test_stage_change.py`, Postgres-gated).
- Frontend: typecheck + lint; manual check that Lost cannot be confirmed with an empty reason.

## Done criteria

- [ ] `python -m py_compile app/leads/services.py` exits 0
- [ ] `grep -n "lost_reason is required" apps/api/app/leads/services.py` → 1 match
- [ ] Backend lost-reason test exists (passes where Postgres available)
- [ ] `cd apps/web && npm run typecheck && npm run lint` exit 0
- [ ] `grep -n "необязательно" apps/web/components/lead-card/LostModal.tsx` → no match
- [ ] No out-of-scope files modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report if:
- "Current state" excerpts don't match live code (drift).
- Any automation or import path calls `move_lead_stage` into a lost stage WITHOUT a reason and would now break — `grep -rn "is_lost" apps/api/app` and check callers; if an internal caller legitimately closes-lost without a reason, report so a default reason ("system") can be agreed rather than breaking that flow.

## Maintenance notes

- Follow-up (deferred): replace free-text with a workspace-configurable reason list so losses are aggregatable on the forecast/loss view.
- Reviewer: confirm no server-initiated close-lost path is now blocked.
