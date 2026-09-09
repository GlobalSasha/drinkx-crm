# Plan 020: Gate first-user admin bootstrap and fix the concurrent-signup race

> **Executor instructions**: Follow step by step. Run every verification
> command. Honor STOP conditions. Update this plan's row in `plans/README.md`
> when done.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/api/app/auth/services.py apps/api/app/auth/models.py apps/api/app/config.py`
> If any changed, compare against "Current state" before proceeding; on a
> mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

The system is invite-only *after* the first workspace exists, but the
first-ever authenticated identity is made `admin` of the shared workspace with
**no** invite check (`upsert_user_from_token`). Whoever authenticates first —
before the real DrinkX team — seizes permanent admin of the single shared
workspace (invite others, change roles, read all CRM data). Security depends
entirely on an out-of-band Supabase signup setting, not on app code. Two
independent problems compound it:

1. **No bootstrap gate** — first caller wins admin.
2. **Check-then-act race** — two concurrent first sign-ins both see zero
   workspaces and each create one → split-brain (two admins, two data planes,
   later users silently join only the oldest). For a normal identity the same
   pattern can raise an uncaught unique-violation 500 on the user insert.

This plan closes both: require the first user's email to match a configured
allow-list, and serialize bootstrap with a Postgres advisory lock plus an
`IntegrityError` catch-and-reselect.

## Current state

- `apps/api/app/auth/services.py:137-217` `upsert_user_from_token` — the
  bootstrap branch:
  ```python
  # :139  read oldest workspace
  result = await session.execute(select(Workspace).order_by(Workspace.created_at.asc()).limit(1))
  workspace = result.scalar_one_or_none()
  if workspace is None:            # :144 first-ever user
      workspace = Workspace(name=settings.workspace_name or "DrinkX", plan="free")
      session.add(workspace); await session.flush()
      # ... creates pipeline, stages, seeds sources ...
      role = "admin"              # :177  <-- no invite / allow-list check
  else:
      normalized_email = claims.email.lower().strip()   # :182 invite required
      # ... raises InviteRequired(normalized_email) if no pending invite ...
  user = User(workspace_id=workspace.id, email=claims.email.lower().strip(), ...)  # :202
  session.add(user); await session.flush()              # :210-211  no IntegrityError guard
  ```
- `apps/api/app/auth/services.py:116` — the by-email fallback lookup uses the
  raw claim (`User.email == claims.email`), a related casing bug handled in
  plan 023; do NOT fix it here to keep this plan's diff focused, but be aware
  both touch the same function (coordinate ordering — see Depends/Maintenance).
- `apps/api/app/config.py:170` `automation_http_signing_secret: str = ""` shows
  the settings style; add the new setting near the other auth/workspace
  settings (search for `workspace_name`).
- `InviteRequired` is already defined and raised in this module (`:194`).

## Commands you will need

| Purpose        | Command                                                       | Expected on success |
|----------------|---------------------------------------------------------------|---------------------|
| Compile check  | `cd apps/api && python -m py_compile app/auth/services.py app/config.py` | exit 0    |
| Auth tests     | `cd apps/api && uv run pytest -q tests/test_auth_bootstrap.py tests/test_invite_accept.py` | all pass |

> DB-backed tests need Postgres + `TEST_DATABASE_URL`; if unavailable locally,
> compile check is the local gate and pytest runs in CI. Do not claim tests
> pass if you didn't run them.

## Scope

**In scope**:
- `apps/api/app/config.py` — add `bootstrap_admin_emails` setting
- `apps/api/app/auth/services.py` — gate bootstrap + advisory lock + IntegrityError catch
- `apps/api/tests/test_auth_bootstrap.py` — new tests

**Out of scope**:
- The invite-required branch logic (already correct).
- `apps/api/app/auth/models.py` schema — no new columns needed for THIS plan
  (invite expiry is plan 023).
- Any change to `_apply_pending_invite`.

## Git workflow

- Branch: `advisor/020-bootstrap-gate-and-race`
- Commit style: `fix(auth): gate first-admin bootstrap behind allow-list and lock`
- Do NOT push or open a PR unless the operator asks.

## Steps

### Step 1: Add the bootstrap allow-list setting

In `apps/api/app/config.py`, add near `workspace_name`:
```python
# Comma-separated emails permitted to bootstrap the first workspace as admin.
# When empty in production, bootstrap is refused (fail-closed). Lower-cased on read.
bootstrap_admin_emails: str = ""
```
Add a helper (module function or a `Settings` property) that returns the
normalized set: `{e.strip().lower() for e in bootstrap_admin_emails.split(",") if e.strip()}`.

**Verify**: `cd apps/api && python -m py_compile app/config.py` → exit 0.

### Step 2: Serialize bootstrap with a Postgres advisory lock

At the top of the "new user" section in `upsert_user_from_token` (right before
the "read oldest workspace" query at `:139`), take a transaction-scoped
advisory lock so concurrent first sign-ins serialize:
```python
# Serialize workspace bootstrap so two concurrent first sign-ins can't each
# create a workspace. Arbitrary fixed key; released at transaction end.
await session.execute(text("SELECT pg_advisory_xact_lock(4021)"))
```
(Import `from sqlalchemy import text` if not already imported.) Because the
lock is held to commit, the second caller blocks until the first commits, then
re-reads and sees the now-existing workspace, falling into the invite branch.

**Verify**: `python -m py_compile app/auth/services.py` → exit 0.

### Step 3: Gate the admin bootstrap behind the allow-list

In the `if workspace is None:` branch, before creating the workspace, check
the allow-list:
```python
allow = settings.bootstrap_admin_emails_set()  # the helper from Step 1
normalized_email = claims.email.lower().strip()
if settings.app_env == "production" and (not allow or normalized_email not in allow):
    raise InviteRequired(normalized_email)
```
Keep the existing workspace/pipeline/stage/seed creation and `role = "admin"`
afterward. Rationale: in non-production (dev/test) keep the current
first-caller-wins convenience so local setup and existing tests aren't broken;
in production require an explicit allow-list. Confirm the exact env field name
by reading `config.py` (it is `app_env` per other guards).

**Verify**: `python -m py_compile app/auth/services.py` → exit 0.

### Step 4: Catch the unique-violation on user insert

Wrap the user insert (`:210-211`) so a concurrent duplicate insert re-selects
instead of 500ing:
```python
from sqlalchemy.exc import IntegrityError
try:
    session.add(user)
    await session.flush()
except IntegrityError:
    await session.rollback()   # or savepoint rollback — match the session pattern in this module
    result = await session.execute(select(User).where(User.supabase_user_id == claims.sub))
    user = result.scalar_one_or_none()
    if user is None:
        result = await session.execute(select(User).where(User.email == claims.email.lower().strip()))
        user = result.scalar_one()
    return user
```
Read the surrounding transaction handling first — if the caller owns the
transaction, a full `session.rollback()` may be wrong; prefer a `begin_nested()`
savepoint around the insert so only the failed insert is undone. Match whatever
pattern this module/`db.py` already uses. If unsure, STOP and report.

**Verify**: `python -m py_compile app/auth/services.py` → exit 0.

### Step 5: Tests

In `apps/api/tests/test_auth_bootstrap.py` add:
- **Allow-list gate**: with `app_env="production"` and an empty/mismatched
  `bootstrap_admin_emails`, first sign-in raises `InviteRequired`; with the
  email in the allow-list, it creates the workspace and the user is `admin`.
- **Non-prod passthrough**: with `app_env` not production, first sign-in still
  bootstraps admin (existing behavior preserved) — this likely matches an
  existing test; adjust env in the fixture rather than duplicating.

Model setup on the existing tests in that file.

**Verify**: `cd apps/api && uv run pytest -q tests/test_auth_bootstrap.py` →
all pass (or deferred to CI, explicitly stated).

## Test plan

- New/updated tests in `tests/test_auth_bootstrap.py`: prod bootstrap refused
  without allow-list; prod bootstrap allowed with matching allow-list email;
  non-prod bootstrap unchanged.
- Advisory-lock race is hard to unit-test deterministically; document it as
  covered-by-design (the lock serializes) rather than writing a flaky
  concurrency test — note this in the PR.
- Verification: `uv run pytest -q tests/test_auth_bootstrap.py tests/test_invite_accept.py`.

## Done criteria

- [ ] `python -m py_compile app/auth/services.py app/config.py` exits 0
- [ ] `grep -n "pg_advisory_xact_lock" apps/api/app/auth/services.py` shows the lock
- [ ] `grep -n "bootstrap_admin_emails" apps/api/app/config.py` shows the setting
- [ ] `grep -n "IntegrityError" apps/api/app/auth/services.py` shows the catch
- [ ] Auth bootstrap tests pass (or deferred to CI, stated)
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated
- [ ] A note added to `docs/brain/` or the PR body: **set
      `BOOTSTRAP_ADMIN_EMAILS` in prod env before next deploy**, else prod
      first-run is refused (intended fail-closed).

## STOP conditions

- The `services.py` excerpts don't match live code (drift).
- The transaction model is unclear enough that you can't tell whether a
  `rollback()` vs `begin_nested()` savepoint is correct in Step 4 — STOP and
  report; a wrong rollback here can corrupt the request's transaction.
- The env field is not named `app_env` — find the real name; if none exists,
  STOP (don't invent a config surface).

## Maintenance notes

- **Operational**: `BOOTSTRAP_ADMIN_EMAILS` must be set in prod before the
  first real user signs in; document it alongside the other required env vars.
- Coordinate with plan 023 (case-insensitive email lookup + invite expiry) —
  both edit `auth/services.py`; land whichever first, then re-run the other's
  drift check.
- Reviewer should confirm the advisory lock is transaction-scoped (`_xact_`)
  so it always releases, and that non-prod behavior is unchanged (local dev).
