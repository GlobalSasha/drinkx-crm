# Plan 018: CEO/company dashboard excludes soft-deleted (trashed) leads

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If
> anything in "STOP conditions" occurs, stop and report — do not improvise.
> When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/api/app/company/repositories.py`
> If that file changed since this plan was written, compare the "Current state"
> excerpts against the live code before proceeding; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

Plan 009 (migration `0052`) added lead soft-delete: a trashed lead gets
`deleted_at` set and disappears from every active-lead list. The lead
lists/pool were updated to filter it (`apps/api/app/leads/repositories.py:286,349,411`),
but the CEO/company overview dashboard was **not** — its queries still filter
only the older `archived_at IS NULL`. So trashing a lead removes it from the
board yet it keeps inflating "новых лидов", stuck counts, per-manager KPIs,
source conversion %, and week-over-week deltas. Two screens then disagree on
how many leads exist. This is a pure correctness fix: add the same
`deleted_at IS NULL` predicate the lead lists already use.

## Current state

- `apps/api/app/company/repositories.py` — CEO-overview aggregation queries
  (raw SQL via `sqlalchemy.text`). Every query filters `archived_at IS NULL`
  but none filters `deleted_at IS NULL`. Affected functions and their lead
  predicates:
  - `pulse_counts` (`:36`): `FROM leads WHERE workspace_id = :wid AND archived_at IS NULL`
  - `stuck_count` (`:52`): `FROM leads l JOIN stages s ... AND l.archived_at IS NULL`
  - `source_breakdown` (`:76`): `FROM leads l ... WHERE l.workspace_id = :wid AND l.archived_at IS NULL AND l.created_at >= :from_`
  - `daily_by_source` (`:104`): same `l.archived_at IS NULL` shape
  - `stuck_leads` (`:125`): `AND l.archived_at IS NULL`
  - `manager_load` (`:159`): `AND l.archived_at IS NULL`
  - `new_leads_per_user` (`:220`): `AND archived_at IS NULL`
  - `portfolio_per_user` (`:311`): `AND l.archived_at IS NULL`
  - `actions_per_user` (`:231`): joins `leads` (via `activities.lead_id`) with
    **no lead-state filter at all** — check the SQL body; if it selects/joins
    `leads`, add `AND l.deleted_at IS NULL`, and if it does not touch `leads`
    at all, leave it (see STOP conditions).
  - `tasks_overdue_per_user` (`:273`): `JOIN leads l ON l.id = a.lead_id` with
    no lead-state filter — add `AND l.deleted_at IS NULL`.

- The soft-delete column exists and is indexed:
  `apps/api/app/leads/models.py:186` `deleted_at: Mapped[datetime | None]`,
  index `ix_leads_workspace_deleted_at` at `:257`.

- **Exemplar to match** — how the active lead lists already write it,
  `apps/api/app/leads/repositories.py:286`:
  ```python
  Lead.deleted_at.is_(None),
  ```
  In this file the queries are raw SQL, so the equivalent text predicate is
  `AND l.deleted_at IS NULL` (or `AND deleted_at IS NULL` where the table is
  unaliased, as in `pulse_counts` and `new_leads_per_user`).

## Commands you will need

| Purpose        | Command                                                    | Expected on success |
|----------------|------------------------------------------------------------|---------------------|
| Compile check  | `cd apps/api && python -m py_compile app/company/repositories.py` | exit 0     |
| Tests (company)| `cd apps/api && uv run pytest -q tests/test_company_managers.py`   | all pass   |
| Grep audit     | `grep -c "deleted_at IS NULL" apps/api/app/company/repositories.py` | ≥ 9 (was 0) |

> Note: DB-backed tests require Postgres and `TEST_DATABASE_URL`. If `uv` /
> Postgres is unavailable locally, the compile check + grep audit are the
> minimum gate; the pytest gate then runs in CI (`.github/workflows/test.yml`,
> `uv run pytest -q`). Do not claim the tests pass if you did not run them —
> say they are deferred to CI.

## Scope

**In scope** (the only files you should modify):
- `apps/api/app/company/repositories.py`
- `apps/api/tests/test_company_managers.py` (add a regression test)

**Out of scope** (do NOT touch):
- `apps/api/app/companies/` — a DIFFERENT domain (CRM company records at
  `/companies`); this plan is only about `company/` (the singular
  `/company` CEO-overview domain). Do not confuse them.
- `apps/api/app/leads/repositories.py` — already correct; do not change.
- Any `archived_at` predicate — keep it; you are ADDING `deleted_at`, not
  replacing anything.

## Git workflow

- Branch: `advisor/018-company-exclude-trashed`
- Commit style (conventional commits, matching `git log`): e.g.
  `fix(company): exclude trashed leads from CEO overview metrics`
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Add `deleted_at IS NULL` to every lead-touching query

For each function listed in "Current state", add the `deleted_at` predicate
next to the existing `archived_at IS NULL` (or, where there is no lead-state
filter, next to the workspace/join condition). Use the correct alias:
- unaliased `FROM leads` (`pulse_counts`, `new_leads_per_user`) →
  `AND deleted_at IS NULL`
- aliased `FROM leads l` / `JOIN leads l` → `AND l.deleted_at IS NULL`

Do not reorder or remove any existing predicate.

**Verify**: `grep -c "deleted_at IS NULL" apps/api/app/company/repositories.py`
→ at least 9 (one per lead-touching query). Then
`cd apps/api && python -m py_compile app/company/repositories.py` → exit 0.

### Step 2: Add a regression test

In `apps/api/tests/test_company_managers.py`, add one test that: creates 2
leads for a workspace, soft-deletes one (set `deleted_at = now()` via the repo
helper `soft_delete` in `leads/repositories.py:459` or by setting the column),
then asserts that `pulse_counts` (or the manager-facing rollup the existing
tests already call) counts only the 1 live lead, not 2. Model the test's
fixture/setup on the existing tests in that same file.

**Verify**: `cd apps/api && uv run pytest -q tests/test_company_managers.py`
→ all pass including the new test. (Deferred to CI if no local Postgres.)

## Test plan

- New test in `apps/api/tests/test_company_managers.py`: "trashed lead is
  excluded from CEO pulse counts" — happy path (2 leads, 1 trashed → count 1).
- Structural pattern: the existing tests in that file (same workspace/lead
  fixtures).
- Verification: `uv run pytest -q tests/test_company_managers.py` → all pass.

## Done criteria

- [ ] `grep -c "deleted_at IS NULL" apps/api/app/company/repositories.py` ≥ 9
- [ ] `python -m py_compile app/company/repositories.py` exits 0
- [ ] New regression test exists in `tests/test_company_managers.py`
- [ ] `uv run pytest -q tests/test_company_managers.py` passes (or explicitly
      recorded as deferred to CI with the reason)
- [ ] No files outside the in-scope list modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report (do not improvise) if:
- The `company/repositories.py` excerpts don't match the live code (drift).
- `actions_per_user` turns out NOT to select or join `leads` at all — then
  there is nothing to filter there; note it and leave that function untouched.
- Adding the predicate makes an existing test fail in a way that suggests a
  test was asserting the buggy (includes-trashed) behavior — report it rather
  than editing the assertion blindly.

## Maintenance notes

- Any NEW aggregate added to `company/repositories.py` must include BOTH
  `archived_at IS NULL` and `deleted_at IS NULL`. Consider a shared SQL
  fragment constant to stop this drifting again.
- Reviewer should check every touched query kept its `archived_at` predicate
  and added `deleted_at` with the right table alias.
