# Plan 023: Auth hardening — case-insensitive email lookup + invite expiry

> **Executor instructions**: Follow step by step. Run every verification
> command. Honor STOP conditions. Update this plan's row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/api/app/auth/services.py apps/api/app/auth/models.py`
> Compare against "Current state" before editing; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: coordinate with plan 020 (same file, `auth/services.py`)
- **Category**: security + bug
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

Two independent auth-flow weaknesses:

1. **Case-sensitive email lookup / lockout.** New users and invites are stored
   and matched **lower-cased**, but the by-email fallback lookup compares the
   **raw** claim. If the IdP returns any upper-case in the address (a
   cross-provider second sign-in at the same address), the stored lower-cased
   `User.email` won't match → an existing member is treated as new → hits
   `InviteRequired` and is locked out.
2. **Invites never expire.** `UserInvite` has no `expires_at`; the accept
   lookup matches any `accepted_at IS NULL` row regardless of age. A forgotten
   invite to a since-reassigned mailbox is a standing, unbounded access grant.

Both are small, targeted fixes.

## Current state

- `apps/api/app/auth/services.py:114-117` — the raw-claim fallback lookup:
  ```python
  if user is None:
      # 2. Or by email (e.g. they signed in via different OAuth at the same address)
      result = await session.execute(select(User).where(User.email == claims.email))
      user = result.scalar_one_or_none()
  ```
  Everywhere else uses `claims.email.lower().strip()` (`:182`, `:204`).
- `apps/api/app/auth/services.py:183-194` — the pending-invite lookup filters
  `UserInvite.accepted_at.is_(None)` with no age bound.
- `apps/api/app/auth/models.py:121-154` — `UserInvite` has `created_at`,
  `accepted_at`, `suggested_role`, `email`, `workspace_id` — but no
  `expires_at`.
- Migration style: see `apps/api/alembic/versions/` (latest head is
  `20260716_0056_lead_commercial_model.py`; the chain is linear 0052→0056).

## Commands you will need

| Purpose        | Command                                                        | Expected on success |
|----------------|----------------------------------------------------------------|---------------------|
| Compile check  | `cd apps/api && python -m py_compile app/auth/services.py app/auth/models.py` | exit 0 |
| Migration head | `cd apps/api && uv run alembic heads`                          | single head         |
| Auth tests     | `cd apps/api && uv run pytest -q tests/test_invite_accept.py tests/test_auth_bootstrap.py` | all pass |

> DB tests / alembic need Postgres; if unavailable locally, compile is the
> local gate and CI runs the rest. State what you actually ran.

## Scope

**In scope**:
- `apps/api/app/auth/services.py` — case-insensitive email compare + invite
  expiry filter
- `apps/api/app/auth/models.py` — add `expires_at` column
- `apps/api/alembic/versions/` — new migration adding `user_invites.expires_at`
- `apps/api/app/auth/` invite-creation code — set `expires_at` on new invites
  (find where `UserInvite(...)` is constructed; likely in `services.py`
  `invite_user`)
- `apps/api/tests/test_invite_accept.py` — tests

**Out of scope**:
- Bootstrap gate/lock (plan 020) — don't duplicate.
- The admin invite UI (frontend) — surfacing expiry there is a follow-up.

## Steps

### Step 1: Case-insensitive email fallback lookup

At `services.py:116` replace the raw compare:
```python
from sqlalchemy import func
# ...
result = await session.execute(
    select(User).where(func.lower(User.email) == claims.email.lower().strip())
)
```
Normalize the claim once at the top of the function if cleaner.

**Verify**: `python -m py_compile app/auth/services.py` → exit 0.

### Step 2: Add `expires_at` to `UserInvite`

In `models.py` add:
```python
expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```
(nullable so existing rows are valid; a NULL `expires_at` means "no expiry" —
treat legacy rows as non-expiring, or backfill in the migration to
`created_at + interval '14 days'` — pick non-expiring for legacy to avoid
locking out anyone mid-flight, and document it).

**Verify**: `python -m py_compile app/auth/models.py` → exit 0.

### Step 3: Migration

Create a new alembic revision (down_revision = current head
`20260716_0056_lead_commercial_model`) adding the nullable
`user_invites.expires_at` column. Model it on an existing add-column migration
in `apps/api/alembic/versions/`.

**Verify**: `uv run alembic heads` → single head (the new one). (Deferred to CI
if no local DB.)

### Step 4: Set expiry on new invites + filter on accept

- Where `UserInvite(...)` is created (invite_user), set
  `expires_at=datetime.now(timezone.utc) + timedelta(days=14)`.
- In the pending-invite lookup (`services.py:183-194`), add:
  ```python
  UserInvite.accepted_at.is_(None),
  or_(UserInvite.expires_at.is_(None), UserInvite.expires_at > datetime.now(timezone.utc)),
  ```
  (import `or_` from sqlalchemy). NULL `expires_at` stays valid (legacy rows).

**Verify**: `python -m py_compile app/auth/services.py` → exit 0.

### Step 5: Tests

In `tests/test_invite_accept.py` add: an invite with `expires_at` in the past
is NOT honored (user hits `InviteRequired`); an invite with `expires_at` in the
future IS honored; a legacy invite with `expires_at IS NULL` IS honored. For
the email-casing fix, add a test that an existing user whose stored email is
lower-case is found when the claim email has upper-case (no `InviteRequired`).

**Verify**: `cd apps/api && uv run pytest -q tests/test_invite_accept.py` → all
pass (or deferred to CI, stated).

## Done criteria

- [ ] `python -m py_compile app/auth/services.py app/auth/models.py` exits 0
- [ ] `grep -n "func.lower(User.email)" apps/api/app/auth/services.py` shows the fix
- [ ] `grep -n "expires_at" apps/api/app/auth/models.py` shows the column
- [ ] New migration exists; `uv run alembic heads` is a single head (or deferred to CI)
- [ ] Invite expiry + email-casing tests exist and pass (or deferred to CI)
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- The `services.py` excerpts don't match live code (drift, likely from plan 020
  landing first) — re-anchor to the new line numbers.
- `UserInvite` is constructed in a place you can't find with
  `grep -rn "UserInvite(" apps/api/app` — STOP and report rather than guessing
  where to set `expires_at`.

## Maintenance notes

- The 14-day TTL is a default; if the team wants a different window, make it a
  config setting rather than a magic number.
- Follow-up (not in scope): surface `expires_at` in the admin invite list UI so
  admins see/resend expired invites.
- Reviewer: confirm legacy NULL-expiry invites still work (no mass lockout).
