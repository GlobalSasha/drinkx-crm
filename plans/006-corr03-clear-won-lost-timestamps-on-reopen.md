# Plan 006: Clear won_at/lost_at/lost_reason when a deal leaves a terminal stage

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before the next step.
> If a "STOP conditions" item occurs, stop and report — do not improvise. When
> done, update this plan's row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a81462c..HEAD -- apps/api/app/automation/stage_change.py apps/api/app/daily_plan/priority_scorer.py apps/api/app/leads/analytics.py`
> If any of those changed, compare against the "Current state" excerpts; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `a81462c`, 2026-06-20

## Why this matters

Reopening a mistakenly-closed deal (moving it from a won/lost stage back to an active one) is an explicitly-supported action, but `won_at`/`lost_at`/`lost_reason` are **never cleared**. Concrete damage to a live, reopened deal:
1. The daily-plan priority scorer applies a permanent **−50** penalty keyed off `won_at is not None or lost_at is not None`, so a reopened deal is buried at the bottom of every "Today" plan forever.
2. UTM revenue analytics counts the lead as won (it keys off `won_at`, independent of current stage), inflating channel revenue.
3. A lead closed-won then moved to closed-lost ends up with **both** `won_at` and `lost_at` set.

The fix makes the `*_at` timestamps a faithful reflection of the current terminal state. The audit trail of "this was once won/lost" is preserved independently in `lead_stage_history` and the `stage_change` Activity, so nothing is lost.

## Current state

- `apps/api/app/automation/stage_change.py` — the transition engine. The post-action that stamps terminal timestamps only ever **sets**, never clears:

```python
# apps/api/app/automation/stage_change.py:126
async def set_won_lost_timestamps(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Stamp won_at / lost_at when entering a terminal stage."""
    now = datetime.now(timezone.utc)
    if ctx.to_stage.is_won and ctx.lead.won_at is None:
        ctx.lead.won_at = now
    if ctx.to_stage.is_lost and ctx.lead.lost_at is None:
        ctx.lead.lost_at = now
```

  `ctx.lead` is the Lead being moved; `ctx.to_stage` is the destination `Stage` with boolean `is_won`/`is_lost`. The `db` arg is unused in this function (so it can be unit-tested without a database).

- `apps/api/app/leads/services.py:415` documents the reopen behaviour: *"re-moving a won/lost lead is intentionally allowed … The won_at/lost_at timestamps are preserved on re-entry."* That comment becomes inaccurate after this change — update it to say timestamps now reflect the current terminal state.
- Downstream consumers that the bug poisons (do NOT change them — they become correct once timestamps are accurate):
  - `apps/api/app/daily_plan/priority_scorer.py:38,78` — `P_ARCHIVED_OR_TERMINAL = -50` applied when `won_at`/`lost_at` set.
  - `apps/api/app/leads/analytics.py` — won-revenue aggregates key off `won_at`.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/automation/stage_change.py` | exit 0 |
| Unit test | `cd apps/api && uv run pytest -q tests/test_stage_change.py -k "won_lost"` | new tests pass |

(CI: `uv sync` + `uv run pytest -q` from `apps/api`. `tests/test_stage_change.py` has Postgres-gated integration tests via `POSTGRES_AVAILABLE`; the new test below is a **pure unit test** that needs no DB.)

## Scope

**In scope:**
- `apps/api/app/automation/stage_change.py` — `set_won_lost_timestamps` body only.
- `apps/api/app/leads/services.py` — the one stale docstring at ~line 415 (comment only).
- `apps/api/tests/test_stage_change.py` — add a pure unit test for the function.

**Out of scope (do NOT touch):**
- `priority_scorer.py`, `analytics.py` — they are correct once the timestamps are; changing them would double-fix.
- The reopen *permission* itself (reopen stays allowed).

## Git workflow

- Branch: `advisor/006-clear-won-lost-timestamps`
- Commit message e.g. `fix(leads): clear won_at/lost_at when a deal leaves a terminal stage`.
- Do NOT push/PR unless instructed.

## Steps

### Step 1: Make the timestamp logic reflect the current terminal state

Replace the body of `set_won_lost_timestamps` so it sets the matching timestamp when entering a terminal stage AND clears the timestamps (and `lost_reason`) that no longer apply. Target logic:

- Entering a **won** stage → set `won_at` if null; clear `lost_at` and `lost_reason`.
- Entering a **lost** stage → set `lost_at` if null; clear `won_at`.
- Entering a **non-terminal** stage → clear `won_at`, `lost_at`, and `lost_reason`.

Concretely:

```python
async def set_won_lost_timestamps(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Keep won_at / lost_at / lost_reason in sync with the CURRENT terminal
    state. Entering a terminal stage stamps its timestamp; leaving terminal
    (reopen) or switching terminal kind clears the stale ones. Historical
    'ever won/lost' lives in lead_stage_history + the stage_change Activity."""
    now = datetime.now(timezone.utc)
    if ctx.to_stage.is_won:
        if ctx.lead.won_at is None:
            ctx.lead.won_at = now
        ctx.lead.lost_at = None
        ctx.lead.lost_reason = None
    elif ctx.to_stage.is_lost:
        if ctx.lead.lost_at is None:
            ctx.lead.lost_at = now
        ctx.lead.won_at = None
    else:
        ctx.lead.won_at = None
        ctx.lead.lost_at = None
        ctx.lead.lost_reason = None
```

**Verify**: `cd apps/api && python -m py_compile app/automation/stage_change.py` → exit 0.

### Step 2: Fix the stale docstring in services.py

In `apps/api/app/leads/services.py` (~line 415), update the comment from "timestamps are preserved on re-entry" to state they now reflect the current terminal state (cleared on reopen).

**Verify**: `grep -n "preserved on re-entry" apps/api/app/leads/services.py` → no match.

### Step 3: Add the pure unit test

In `apps/api/tests/test_stage_change.py`, add a test that calls `set_won_lost_timestamps` directly with a duck-typed context (no DB). The function only reads `ctx.to_stage.is_won/is_lost` and `ctx.lead.won_at/lost_at/lost_reason`, so use `types.SimpleNamespace`:

```python
import types, asyncio
from app.automation.stage_change import set_won_lost_timestamps

def _ctx(*, is_won, is_lost, won_at, lost_at, lost_reason="x"):
    lead = types.SimpleNamespace(won_at=won_at, lost_at=lost_at, lost_reason=lost_reason)
    to_stage = types.SimpleNamespace(is_won=is_won, is_lost=is_lost)
    return types.SimpleNamespace(lead=lead, to_stage=to_stage), lead

def test_reopen_clears_terminal_timestamps():
    ctx, lead = _ctx(is_won=False, is_lost=False, won_at="WAS", lost_at=None)
    asyncio.run(set_won_lost_timestamps(ctx, None))
    assert lead.won_at is None and lead.lost_at is None and lead.lost_reason is None

def test_won_clears_lost():
    ctx, lead = _ctx(is_won=True, is_lost=False, won_at=None, lost_at="WAS", lost_reason="gone")
    asyncio.run(set_won_lost_timestamps(ctx, None))
    assert lead.won_at is not None and lead.lost_at is None and lead.lost_reason is None

def test_lost_clears_won():
    ctx, lead = _ctx(is_won=False, is_lost=True, won_at="WAS", lost_at=None)
    asyncio.run(set_won_lost_timestamps(ctx, None))
    assert lead.lost_at is not None and lead.won_at is None
```

(If the file already imports `pytest`/helpers, reuse them; keep the new tests above the Postgres-gated section so they run without a DB.)

**Verify**: `cd apps/api && uv run pytest -q tests/test_stage_change.py -k "reopen_clears or won_clears or lost_clears"` → 3 passed.

## Test plan

- New pure unit tests (above) covering: reopen→both cleared; won→lost cleared; lost→won cleared. No Postgres needed.
- Existing integration tests in `tests/test_stage_change.py` (Postgres-gated) should still pass where a DB is available; run `uv run pytest -q tests/test_stage_change.py` in CI.

## Done criteria

- [ ] `python -m py_compile app/automation/stage_change.py` exits 0
- [ ] 3 new unit tests pass without Postgres
- [ ] `grep -n "preserved on re-entry" apps/api/app/leads/services.py` → no match
- [ ] `grep -rn "P_ARCHIVED_OR_TERMINAL" apps/api/app/daily_plan/priority_scorer.py` still present and unchanged (we did NOT touch the scorer)
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report if:
- "Current state" excerpts don't match live code (drift).
- The team explicitly wants "ever-won" retained on the lead row itself (not just in history) for some report — then clearing `won_at` would break it; report so a separate `ever_won` flag can be considered instead.

## Maintenance notes

- After this, any report that needs "deals ever won (even if reopened)" must read `lead_stage_history` / the `stage_change` Activity, not `lead.won_at`.
- Reviewer: confirm no code path relies on `won_at` surviving a reopen.
