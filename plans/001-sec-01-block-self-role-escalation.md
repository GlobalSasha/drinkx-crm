# Plan 001: Block self-service role escalation in `PATCH /auth/me`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat d68a3e9..HEAD -- apps/api/app/auth/routers.py apps/api/app/auth/schemas.py apps/api/app/auth/services.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `d68a3e9`, 2026-06-11

## Why this matters

`PATCH /auth/me` currently lets **any authenticated user set their own `role`**,
including `"admin"`. The handler even documents the gap (`# Only admin can
promote/demote — for now any user can self-set during onboarding`). Admin role
unlocks workspace settings, AI budget controls, the audit log, bulk import/export,
and team management. This is a direct, trivially-exploitable privilege escalation:
any signed-in manager sends `{"role":"admin"}` and becomes admin.

The fix is safe because **roles are already assigned server-side** and **no
legitimate client sends `role`**:
- On first sign-in the bootstrapping user becomes `admin`; every subsequent user
  joins as `manager` (`apps/api/app/auth/services.py`, around lines 92–177).
- The frontend onboarding flow does **not** send a `role` field (verified by
  grep across `apps/web` — no caller sets `role` in any `PATCH /auth/me` body).

So honoring `role` here is dead weight *and* the vulnerability. We remove it.

## Current state

Files in scope:
- `apps/api/app/auth/routers.py` — defines `PATCH /auth/me` (`update_me`). Contains the vulnerable block.
- `apps/api/app/auth/schemas.py` — `UserUpdateIn` DTO; declares the `role` field.
- `apps/api/app/auth/services.py` — assigns role server-side on sign-in (read-only context; do NOT change).
- `apps/api/app/auth/dependencies.py` — already provides `require_admin` and `require_admin_or_head` (read-only context).

The vulnerable code, `apps/api/app/auth/routers.py:24-53` (today):

```python
@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdateIn,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Update profile fields (used by Onboarding step 2)."""
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None and payload.role in ("manager", "head", "admin"):
        # Only admin can promote/demote — for now any user can self-set during onboarding
        user.role = payload.role
    if payload.timezone is not None:
        user.timezone = payload.timezone
    if payload.max_active_deals is not None:
        user.max_active_deals = payload.max_active_deals
    if payload.specialization is not None:
        user.specialization = payload.specialization
    if payload.working_hours_json is not None:
        user.working_hours_json = payload.working_hours_json
    if payload.phone is not None:
        user.phone = payload.phone or None
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url or None
    if payload.mark_onboarding_complete:
        user.onboarding_completed = True

    await session.commit()
    await session.refresh(user, attribute_names=["workspace"])
    return user
```

The `role` field in `apps/api/app/auth/schemas.py` (today):

```python
class UserUpdateIn(BaseModel):
    """Body for PATCH /auth/me — used by Onboarding step 2 and /settings/profile."""

    name: str | None = None
    role: str | None = None     # <-- remove this line
    timezone: str | None = None
    ...
```

Repo conventions to follow:
- Role-gated endpoints use a FastAPI dependency, e.g. `Depends(require_admin)` —
  see `apps/api/app/settings/routers.py:105` and `apps/api/app/logs/routers.py:29`.
  (Relevant only if you later add an admin role-change endpoint — out of scope here.)
- Tests are DB-backed and call domain code with fixtures (`db`, `user`,
  `admin_user`, `workspace`) — see `apps/api/tests/conftest.py`. There is **no**
  HTTP-client/dependency-override harness; tests call the router coroutine or
  service directly with fixtures.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run the new test | `cd apps/api && uv run pytest tests/test_auth_role_guard.py -q` | all pass |
| Full auth tests | `cd apps/api && uv run pytest tests/test_auth_bootstrap.py -q` | all pass (no regression) |
| Lint | `cd apps/api && uv run ruff check app/auth tests/test_auth_role_guard.py` | exit 0 |
| Typecheck | `cd apps/api && uv run mypy app/auth` | exit 0 |

Note: the DB-backed tests require a reachable Postgres at
`TEST_DATABASE_URL` (default `postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test`).
If Postgres is unavailable the suite **skips** these tests rather than failing —
see the `POSTGRES_AVAILABLE` probe in `conftest.py`. If your new test is skipped
for that reason, that is a STOP condition (you cannot verify the fix); report it.

## Scope

**In scope** (the only files you may modify):
- `apps/api/app/auth/routers.py` — remove the role-honoring block.
- `apps/api/app/auth/schemas.py` — remove the `role` field from `UserUpdateIn`.
- `apps/api/tests/test_auth_role_guard.py` — create.

**Out of scope** (do NOT touch):
- `apps/api/app/auth/services.py` — server-side role assignment is correct; leave it.
- `UserOut` schema — it still exposes `role` for reads; that is fine and required.
- Adding an admin-only "change another user's role" endpoint — that is a separate
  feature. Do not build it here. (Note in your report that the product may need
  one eventually; today no such flow exists and none is required by the frontend.)
- Any frontend file. The frontend never sends `role`; nothing to change.

## Git workflow

- Branch: `advisor/001-sec-block-role-escalation`
- Commit message style is conventional commits (see `git log --oneline`); use e.g.
  `fix(auth): stop honoring self-set role in PATCH /auth/me (SEC-01)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Remove the role-honoring block from `update_me`

In `apps/api/app/auth/routers.py`, delete these three lines from `update_me`:

```python
    if payload.role is not None and payload.role in ("manager", "head", "admin"):
        # Only admin can promote/demote — for now any user can self-set during onboarding
        user.role = payload.role
```

Leave every other field assignment intact. The handler keeps updating name,
timezone, max_active_deals, specialization, working_hours_json, phone, avatar_url,
and onboarding completion.

**Verify**: `grep -n "user.role = payload.role" apps/api/app/auth/routers.py` → no matches (exit 1).

### Step 2: Remove `role` from the `UserUpdateIn` schema

In `apps/api/app/auth/schemas.py`, delete the `role: str | None = None` line from
`class UserUpdateIn`. (Pydantic ignores unknown fields by default, so a client that
still sends `role` gets a 200 with the field silently ignored — no 422, no role
change.) Update the class docstring's wording if it implies role can be set; do not
otherwise edit the file.

**Verify**: `grep -n "role" apps/api/app/auth/schemas.py` → matches only inside
`UserOut` (the read DTO), NOT inside `UserUpdateIn`.

### Step 3: Add a regression test

Create `apps/api/tests/test_auth_role_guard.py`. Model its fixture usage on the
existing DB-backed tests (use the `db` and `user` fixtures from `conftest.py`).
Call the `update_me` router coroutine directly. The test must prove a manager
cannot escalate:

Target shape (adapt imports/signatures to what the codebase actually exposes —
confirm the `update_me` parameter order against `routers.py`):

```python
"""SEC-01 regression: PATCH /auth/me must not let a user change their own role."""
from __future__ import annotations

import pytest

from app.auth.routers import update_me
from app.auth.schemas import UserUpdateIn


@pytest.mark.asyncio
async def test_self_role_escalation_is_ignored(db, user):
    # `user` fixture is role="manager"
    assert user.role == "manager"

    # Even if a client forges a role field, it must not stick.
    payload = UserUpdateIn.model_validate({"role": "admin", "name": "Hacker"})
    result = await update_me(payload=payload, user=user, session=db)

    assert result.role == "manager", "manager must not be able to self-promote to admin"
    assert result.name == "Hacker", "legitimate profile fields still update"
```

Notes for the executor:
- After Step 2, `UserUpdateIn` no longer declares `role`, so
  `UserUpdateIn.model_validate({"role": "admin", ...})` parses fine but drops the
  unknown `role` key — which is exactly the behavior under test. Keep the test as
  written; it asserts the *outcome* (role unchanged), which is robust whether the
  field is dropped at parse time or ignored in the handler.
- If `update_me`'s real signature differs (param names/order), match the live
  signature. Do not change the handler to fit the test.

**Verify**: `cd apps/api && uv run pytest tests/test_auth_role_guard.py -q` → 1 passed.

## Test plan

- New file `apps/api/tests/test_auth_role_guard.py`, one test:
  `test_self_role_escalation_is_ignored` — a manager calling `update_me` with a
  forged `role: "admin"` ends with `role == "manager"`, while a normal field
  (`name`) still updates. This is the exact SEC-01 regression.
- Structural pattern: the DB-backed fixture style in `apps/api/tests/conftest.py`
  (`db`, `user`). For an example of a test that mutates a user via domain code,
  see any test using the `user` fixture, e.g. `tests/test_users_service.py`.
- Verification: `cd apps/api && uv run pytest tests/test_auth_role_guard.py tests/test_auth_bootstrap.py -q` → all pass.

## Done criteria

ALL must hold:

- [ ] `grep -n "user.role = payload.role" apps/api/app/auth/routers.py` → no matches
- [ ] `grep -n "role" apps/api/app/auth/schemas.py` → matches only in `UserOut`, not `UserUpdateIn`
- [ ] `cd apps/api && uv run pytest tests/test_auth_role_guard.py -q` → 1 passed (NOT skipped)
- [ ] `cd apps/api && uv run pytest tests/test_auth_bootstrap.py -q` → all pass (no regression in role bootstrap)
- [ ] `cd apps/api && uv run ruff check app/auth tests/test_auth_role_guard.py` → exit 0
- [ ] `cd apps/api && uv run mypy app/auth` → exit 0
- [ ] Only the three in-scope files are modified (`git status`)
- [ ] `plans/README.md` status row for 001 updated to DONE

## STOP conditions

Stop and report (do not improvise) if:

- The `update_me` handler or `UserUpdateIn` schema does not match the "Current
  state" excerpts (the code drifted since 2026-06-11).
- The new test is **skipped** because Postgres is unavailable — you cannot verify
  the fix without it; report that the operator must provide a test DB.
- You discover a *legitimate* caller (frontend or another service) that actually
  depends on setting `role` via `PATCH /auth/me`. (Audit found none; if you find
  one, the safe-removal assumption is false — stop and report.)
- `test_auth_bootstrap.py` starts failing — that means server-side role assignment
  was affected, which is out of scope.

## Maintenance notes

- If the product later needs admins to change *other* users' roles, add a
  dedicated endpoint gated by `Depends(require_admin)` (pattern:
  `apps/api/app/settings/routers.py:105`) — never reopen self-set on `/me`.
- Reviewer should confirm: no frontend code regressed (it never sent `role`), and
  `UserOut.role` still serializes for reads (the profile/team UI displays it).
- The audit's other security findings (SEC-04, SEC-05, SEC-09, DIR-03) are
  tracked in `plans/README.md` and intentionally NOT addressed here.
