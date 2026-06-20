# Plan 005: Gate workspace-wide revenue/pipeline analytics to admin+head

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update this plan's row in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a81462c..HEAD -- apps/api/app/leads/routers.py`
> If `leads/routers.py` changed since this plan was written, compare the
> "Current state" excerpts against the live code; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `a81462c`, 2026-06-20

## Why this matters

`GET /api/leads/utm-stats` returns **won-deal revenue per acquisition channel for the whole workspace**, and `GET /api/leads/stage-dwell` returns full pipeline-bottleneck stats. Both are gated only by `Depends(current_user)` — any `manager` can call them directly. The parallel management-reporting endpoints under `/api/team/*` are all gated `require_admin_or_head`, and `/api/audit` and `/api/settings/ai` are admin-only. So a plain manager can read company financials (total won revenue by channel, conversion) that the rest of the app deliberately hides from them. This is a confidentiality inconsistency; the fix aligns these two routes with the rest of the reporting surface.

## Current state

- `apps/api/app/leads/routers.py` — leads API. The two analytics routes are declared just before the `/{lead_id}` path-param routes. As of `a81462c`:

```python
# apps/api/app/leads/routers.py:188
@router.get("/stage-dwell", response_model=list[StageDwellOut])
async def lead_stage_dwell(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[StageDwellOut]:
    ...

# apps/api/app/leads/routers.py:203
@router.get("/utm-stats", response_model=list[UtmSourceStatOut])
async def lead_utm_stats(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[UtmSourceStatOut]:
    ...
```

- The guard to use already exists:

```python
# apps/api/app/auth/dependencies.py:57
async def require_admin_or_head(
    user: Annotated[User, Depends(current_user)],
) -> User:
    if user.role not in ("admin", "head"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, ...)
    return user
```

- **Exemplar** — every `/api/team/*` route already does exactly this: see `apps/api/app/team/routers.py` (e.g. the dashboard route uses `Depends(require_admin_or_head)`). Match that shape.
- **Convention**: routes take the authed user via a dependency; swapping `current_user` → `require_admin_or_head` keeps `user` available (it returns a `User`).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/leads/routers.py` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q -k "leads_router or role_guard or scoping"` | all pass |
| Whole module | `cd apps/api && uv run pytest -q tests/test_leads_router_scoping.py tests/test_auth_role_guard.py` | all pass |

(CI installs deps with `uv sync` and runs `uv run pytest -q` from `apps/api` — see `.github/workflows/test.yml`.)

## Scope

**In scope:**
- `apps/api/app/leads/routers.py` (the two route signatures only)
- `apps/api/tests/test_leads_router_scoping.py` (add tests; create if the role case isn't there)

**Out of scope (do NOT touch):**
- The analytics SQL in `apps/api/app/leads/analytics.py` — already workspace-scoped; only the route guard changes.
- The frontend `apps/web/app/(app)/forecast/page.tsx` — it consumes these via hooks; gating the API is enough. (If the forecast page must stay manager-visible, that's a product decision — see STOP conditions.)

## Git workflow

- Branch: `advisor/005-restrict-pipeline-revenue-analytics`
- Conventional-commit style, e.g. `fix(security): gate utm-stats/stage-dwell to admin+head`.
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 1: Ensure the guard is imported

In `apps/api/app/leads/routers.py`, confirm `require_admin_or_head` is imported from `app.auth.dependencies` (the file already imports `current_user` from there). If absent, add it to that import.

**Verify**: `grep -n "require_admin_or_head" apps/api/app/leads/routers.py` → at least one match (the import).

### Step 2: Swap the dependency on both analytics routes

In both `lead_stage_dwell` and `lead_utm_stats`, change the `user` parameter dependency from `Depends(current_user)` to `Depends(require_admin_or_head)`. Leave everything else identical.

**Verify**: `grep -n "Depends(require_admin_or_head)" apps/api/app/leads/routers.py` → 2 matches.

### Step 3: Add a role-guard regression test

In `apps/api/tests/test_leads_router_scoping.py`, add a test asserting a `manager`-role user receives 403 from both endpoints and an `admin` (or `head`) receives 200. Follow the role-assertion pattern already used in `apps/api/tests/test_auth_role_guard.py` (it shows how to build a user of a given role and assert the 403).

**Verify**: `cd apps/api && uv run pytest -q -k "utm_stats or stage_dwell"` → the new tests pass.

## Test plan

- New tests in `tests/test_leads_router_scoping.py`:
  - `manager` → 403 on `/leads/utm-stats` and `/leads/stage-dwell`.
  - `admin` (or `head`) → 200 on both.
- Pattern to follow: `tests/test_auth_role_guard.py` (role construction + 403 assertion).
- Verification: `cd apps/api && uv run pytest -q tests/test_leads_router_scoping.py` → all pass, including the 2+ new cases. Note: tests needing a live Postgres are skipped via `POSTGRES_AVAILABLE`; the role-guard assertion should be written to run without a DB (the 403 fires in the dependency, before any query).

## Done criteria

- [ ] `python -m py_compile app/leads/routers.py` exits 0
- [ ] `grep -n "Depends(require_admin_or_head)" apps/api/app/leads/routers.py` → exactly 2 matches
- [ ] `grep -n "Depends(current_user)" apps/api/app/leads/routers.py` no longer matches the two analytics routes (it still matches other routes — that's fine)
- [ ] New role-guard tests pass
- [ ] No files outside the in-scope list modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report (do not improvise) if:
- The "Current state" excerpts don't match the live code (drift).
- The product intent turns out to be "managers SHOULD see channel revenue" — then this is a deliberate product decision, not a bug; report rather than force the guard.
- The forecast page (`apps/web`) breaks for a legitimate manager use after gating — report so the team decides whether `/forecast` is a leadership-only surface.

## Maintenance notes

- If a new workspace-wide analytics route is added to `leads/routers.py`, it should default to `require_admin_or_head` unless explicitly meant for all roles.
- Reviewer: confirm no other route returns cross-rep financials under `current_user`.
