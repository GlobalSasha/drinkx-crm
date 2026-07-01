# Plan 010: Add ownership/role guards to per-lead task mutations (mirror the comment rule)

> **Executor instructions**: Follow step by step; run every verification command and
> confirm before proceeding. Honor STOP conditions. Update plan 010's row in
> `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/activity`
> On any change to the in-scope files, re-check the excerpts before proceeding.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW (adds a guard that raises 403; only affects cross-owner task edits)
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `9e93b16`, 2026-07-01
- **Extends**: round-2 backlog **B2** (IDOR) to the task/activity mutation surface

## Why this matters

The comment edit path already enforces "author or admin" and even documents *why*
(`update_comment`, `apps/api/app/activity/services.py:181`). The sibling task
mutations — `update_task`, `complete_task`, `reopen_task`, `archive_task`,
`restore_task` — enforce only workspace + lead scoping and **no** owner check.
`complete_task` even receives `user_id` and never uses it for authorization. So any
manager can complete, edit, archive, reopen, or restore any peer's task on any lead,
corrupting the per-user task aggregate that drives `/today` and `/tasks`. This is the
same authorization gap the comment path deliberately closed — closing it on tasks is
consistency, not new policy.

## Current state

- `apps/api/app/activity/services.py`:
  - `update_task` (line 124) — no user/owner check.
  - `update_comment` (line 158) — **the exemplar**; line 181:
    `if activity.user_id != actor.id and actor.role != "admin": raise ActivityForbidden(activity_id)`,
    placed *before* type inspection so status codes don't leak existence.
  - `archive_task` (line 199), `restore_task` (line 221) — no user check.
  - `complete_task` (line 238) — takes `user_id` but never authorizes with it.
  - `reopen_task` (line 256) — no user check.
- `apps/api/app/activity/routers.py` — task endpoints depend on
  `current_user` (line 23 import); the router passes `workspace_id`/`lead_id` but
  not always the actor. Read the router to see each call site.
- Exception type to reuse: `ActivityForbidden` (already raised by `update_comment`;
  find its definition + its HTTP mapping in `routers.py` and mirror it).

**Decision baked in**: authorized actor = the task's creator (`activity.user_id`)
OR `admin`/`head`. (The comment rule uses `admin` only; tasks additionally allow
`head` because task management is a lead-ownership concern the head oversees — keep
this consistent and note it in the docstring.)

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/activity/services.py app/activity/routers.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/activity` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_activity_task_authz.py` | all pass |

## Scope

**In scope:**
- `apps/api/app/activity/services.py` (add guard to 5 task mutations)
- `apps/api/app/activity/routers.py` (thread `actor`/`user` into the calls that lack it)
- `apps/api/tests/test_activity_task_authz.py` (create)

**Out of scope:**
- `update_comment` — already correct; do not touch.
- Read endpoints (list tasks / feed) — visibility is not changing, only mutation.
- `complete_task`'s idempotency behavior (already returns early if `task_done`).
- The lead-level IDOR on PATCH/move-stage/deal/score (that is B2 for leads; separate).

## Git workflow

- Branch: `advisor/010-task-authz`
- One commit; message e.g. `fix(activity): authorize task mutations to owner-or-admin/head (plan 010)`.
- Do NOT push/PR unless instructed.

## Steps

### Step 1: Add a shared authorization helper

In `services.py`, add near the top of the task functions:
```python
def _authorize_task_actor(activity: Activity, actor: User) -> None:
    """Owner (creator) or admin/head may mutate a task. Mirrors update_comment.
    Raise BEFORE inspecting the row's type so status codes don't leak existence."""
    if activity.user_id != actor.id and actor.role not in ("admin", "head"):
        raise ActivityForbidden(activity.id)
```

### Step 2: Call it in all five task mutations

Change `update_task`, `complete_task`, `reopen_task`, `archive_task`,
`restore_task` to accept an `actor: User` parameter and call
`_authorize_task_actor(activity, actor)` immediately after the row is fetched and
before the `if activity.type != task` check (same ordering as `update_comment`).
`complete_task` already receives `user_id`; replace it with the full `actor: User`
so role is available.

**Verify**: `grep -c "_authorize_task_actor" app/activity/services.py` → 6
(1 def + 5 calls). `python -m py_compile app/activity/services.py` → 0.

### Step 3: Thread the actor through the routers

In `routers.py`, each of the five task endpoints already has
`user: User = Depends(current_user)`. Pass `actor=user` into the corresponding
service call. Do not change response models or status codes.

**Verify**: `python -m py_compile app/activity/routers.py` → 0.

### Step 4: Tests

Create `tests/test_activity_task_authz.py` (model after any existing
`tests/test_*` that builds two users + a lead + an activity). Cases:
owner completes/edits/archives/restores → OK; a different manager → `ActivityForbidden`
(403); an `admin` and a `head` acting on another user's task → OK; the guard fires
before the type check (a non-owner hitting a comment id via the task endpoint still
gets 403, not a 400 type error).

**Verify**: `cd apps/api && uv run pytest -q tests/test_activity_task_authz.py` → all pass.

## Test plan

- New `tests/test_activity_task_authz.py`, ~6 cases (Step 4).
- Pattern: an existing activity/service test that constructs users + a lead.
- Verification: the pytest command passes with new tests.

## Done criteria

- [ ] `python -m py_compile app/activity/services.py app/activity/routers.py` → 0
- [ ] `uv run ruff check app/activity` → 0
- [ ] `uv run pytest -q tests/test_activity_task_authz.py` → all pass (≥6 new)
- [ ] `grep -n "user_id: uuid.UUID" app/activity/services.py` no longer shows an
      *unused* `user_id` param in `complete_task` (it now takes `actor`)
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` round-3 row for 010 updated

## STOP conditions

- Excerpts don't match live code (drift) — report.
- `ActivityForbidden` is not defined / not mapped to 403 in the router — read how
  `update_comment`'s forbidden path is mapped and mirror it; if unclear, STOP.
- A task endpoint has no `current_user` dependency to source `actor` from — STOP and
  report (do not add auth to a route that was intentionally unauthenticated).

## Maintenance notes

- If a future "reassign task to another manager" feature lands, revisit whether the
  new assignee should also be an authorized actor.
- Reviewer: confirm the guard is placed *before* the type check in every function
  (the existence-leak ordering matters — see the `update_comment` docstring).
- Pairs with plan 009 (lead-level authorization); if both land, consider promoting
  `_authorize_task_actor` into a shared `app/auth` helper reused by both.
