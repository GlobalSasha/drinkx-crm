# Plan 011: Make the AI budget guard fail closed on Redis errors + add a hard monthly ceiling

> **Executor instructions**: Follow step by step; run every verification command.
> Honor STOP conditions. Update plan 011's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/enrichment/budget.py`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (changes behavior only during a Redis outage — from "spend uncapped" to "spend paused")
- **Depends on**: none
- **Category**: bug (security-adjacent: cost-control)
- **Planned at**: commit `9e93b16`, 2026-07-01

## Why this matters

The daily AI budget guard is the only thing capping spend against paid LLM providers.
It reads a Redis counter, and on **any** Redis exception it returns `0.0` spend — so
`has_budget_remaining` returns `True` and enrichment keeps calling providers with no
cap. Upstash Redis is the Celery broker, so a Redis blip is a realistic event, and it
silently disables the one guard whose entire purpose is to *fail safe*. Twenty meters
usage as steps execute and enforces a hard monthly budget; ours fails open and is
pre-flight only. The fix is small: fail **closed** when spend is unknown, and add a
hard monthly ceiling alongside the daily one.

## Current state

`apps/api/app/enrichment/budget.py` (whole file, 54 lines):
```python
def _daily_cap_usd() -> float:                 # line 23
    return float(get_settings().ai_monthly_budget_usd) / 30.0

async def get_daily_spend_usd(workspace_id) -> float:   # line 28
    try:
        client = get_redis()
        raw = await client.get(_key(workspace_id))
        return float(raw) if raw else 0.0
    except Exception as e:
        log.warning("budget.read_failed", error=str(e))
        return 0.0                              # line 35 — FAIL OPEN

async def has_budget_remaining(workspace_id) -> bool:   # line 51
    spent = await get_daily_spend_usd(workspace_id)
    return spent < _daily_cap_usd()
```
- `add_to_daily_spend` (line 38) already swallows Redis errors quietly — that is
  fine (losing a write is safe-ish), but it compounds the read fail-open.
- Config: `ai_monthly_budget_usd: float = 200.0` (`apps/api/app/config.py:70`). There
  is **no** separate monthly key or monthly ceiling today.
- Callers: `grep -rn "has_budget_remaining\|get_daily_spend_usd" apps/api/app` — the
  guard is called pre-flight before enrichment/agent LLM calls.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/enrichment/budget.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/enrichment/budget.py` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_ai_budget_guard.py` | all pass |

## Scope

**In scope:**
- `apps/api/app/enrichment/budget.py`
- `apps/api/app/config.py` (add `ai_hard_monthly_budget_usd` if you choose the explicit-ceiling option in Step 2)
- `apps/api/tests/test_ai_budget_guard.py` (create)

**Out of scope:**
- Per-step metering (Twenty-style live usage accounting) — larger change, not now.
- The Redis client wrapper (`enrichment/sources/cache.py`).
- Callers of `has_budget_remaining` — their contract (`bool`) is unchanged.

## Git workflow

- Branch: `advisor/011-budget-failsafe`
- One commit: `fix(enrichment): fail closed on budget-read error + hard monthly ceiling (plan 011)`.

## Steps

### Step 1: Fail closed when spend is unknown

Split "spend is 0" from "spend is unknown". Change `get_daily_spend_usd` to raise or
return a sentinel on Redis error, and have `has_budget_remaining` treat unknown spend
as **no budget**:
```python
class BudgetUnknown(Exception): ...

async def get_daily_spend_usd(workspace_id) -> float:
    client = get_redis()
    raw = await client.get(_key(workspace_id))   # let a Redis error propagate
    return float(raw) if raw else 0.0

async def has_budget_remaining(workspace_id) -> bool:
    try:
        spent = await get_daily_spend_usd(workspace_id)
    except Exception as e:
        log.warning("budget.read_failed_fail_closed", error=str(e))
        return False                              # FAIL CLOSED
    return spent < _daily_cap_usd()
```
Keep `add_to_daily_spend` swallowing write errors (a lost increment is safe).

**Verify**: `grep -n "return False" app/enrichment/budget.py` shows the fail-closed
branch; `grep -n "return 0.0" app/enrichment/budget.py` no longer appears inside an
`except`. `python -m py_compile` → 0.

### Step 2: Add a hard monthly ceiling

Add a monthly counter keyed `ai_budget_month:{workspace_id}:{YYYY-MM}` (TTL ~40 days),
incremented in `add_to_daily_spend` alongside the daily key, and have
`has_budget_remaining` also reject when monthly spend ≥ `ai_monthly_budget_usd`
(the daily cap stays `monthly/30`). This makes the monthly figure a real ceiling
rather than only an implicit 30× daily. (Optional: add a distinct
`ai_hard_monthly_budget_usd` setting if you want the hard cap to differ from the
soft daily basis; otherwise reuse `ai_monthly_budget_usd`.)

**Verify**: `grep -n "ai_budget_month" app/enrichment/budget.py` → present in both
the increment and the check. `python -m py_compile` → 0.

### Step 3: Tests

Create `tests/test_ai_budget_guard.py` with a fake/mocked Redis (model after any
existing test that mocks `get_redis` — `grep -rln "get_redis" tests`). Cases:
under-cap → `True`; over daily cap → `False`; **Redis raises → `False`** (the core
regression); monthly ceiling reached while daily is under → `False`.

**Verify**: `cd apps/api && uv run pytest -q tests/test_ai_budget_guard.py` → all pass.

## Test plan

- New `tests/test_ai_budget_guard.py`, ~4 cases (Step 3), all mock-only (no live Redis).
- Pattern: an existing mock-Redis test in `tests/`.
- Verification: pytest command passes.

## Done criteria

- [ ] `python -m py_compile app/enrichment/budget.py` → 0
- [ ] `uv run ruff check app/enrichment/budget.py` → 0
- [ ] `uv run pytest -q tests/test_ai_budget_guard.py` → all pass, incl. the
      "Redis error → False" case
- [ ] No `return 0.0` inside an `except` block in `budget.py`
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` round-3 row for 011 updated

## STOP conditions

- Excerpts don't match live code (drift) — report.
- A caller depends on `get_daily_spend_usd` never raising (e.g. a dashboard that
  displays spend) — if changing its error contract would break a caller, keep
  `get_daily_spend_usd` returning `0.0`-on-error but move the fail-closed decision
  entirely into `has_budget_remaining` with its own try/except (still achieves the
  goal). Note the choice in the commit.

## Maintenance notes

- A fail-closed guard means a Redis outage now *pauses* enrichment. That is the
  intended trade-off (cost safety > availability of a non-critical feature), but the
  operator should know: watch for `budget.read_failed_fail_closed` in logs as a
  Redis-health signal.
- If per-step live metering is added later, this pre-flight guard stays as a cheap
  first gate.
