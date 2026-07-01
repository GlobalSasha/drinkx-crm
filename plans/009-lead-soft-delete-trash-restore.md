# Plan 009: Lead delete becomes soft-delete (Trash) with restore; permanent-destroy gated to admin/head; both audited

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> "STOP conditions" item occurs, stop and report — do not improvise. When done,
> update the status row for plan 009 in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/leads apps/api/alembic`
> If any in-scope file changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch, treat
> it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (adds a filter to lead read paths; missing one leaks trashed leads into a list)
- **Depends on**: none (shares an authorization idea with plan 010 — reuse its helper if 010 landed first)
- **Category**: security
- **Planned at**: commit `9e93b16`, 2026-07-01
- **Resolves**: round-2 backlog **B2** (delete path) with the product decision "soft-delete for all + permanent-destroy admin/head only"

## Why this matters

`DELETE /api/leads/{id}` is a **hard cascade delete** callable by any authenticated
user, and it emits **no audit event**. One API call irreversibly erases a lead and
(via `ondelete='CASCADE'`) its notes/activities, with no recovery and no trace of who
did it. Twenty splits this into two operations: a recoverable **soft delete** (Trash /
"Deleted records") available to everyone, and a separate **permanent destroy** gated
behind a distinct privileged capability. The product decision for DrinkX is the same:
everyone can move a lead to Trash and restore it; only `admin`/`head` can permanently
destroy; both actions are audited.

## Current state

- `apps/api/app/leads/models.py` — the `Lead` ORM class.
  - Line 172: `archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)`
    — **already used for pool filtering; do NOT reuse it for delete.** We add a
    distinct `deleted_at` + `deleted_by`.
  - Line 151: `assigned_to` FK to users (nullable).
- `apps/api/app/leads/repositories.py:448`:
  ```python
  async def delete_lead(db: AsyncSession, lead: Lead) -> None:
      await db.delete(lead)          # hard delete
      await db.flush()
  ```
- `apps/api/app/leads/services.py:264`:
  ```python
  async def delete_lead(db, workspace_id, lead_id) -> None:
      lead = await repo.get_by_id(db, lead_id, workspace_id)
      if lead is None:
          raise LeadNotFound(lead_id)
      await repo.delete_lead(db, lead)   # no owner/role check, no audit
  ```
- `apps/api/app/leads/routers.py:314`:
  ```python
  @router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_lead(lead_id, db=Depends(get_db), user=Depends(current_user)):
      try:
          await services.delete_lead(db, user.workspace_id, lead_id)
      except LeadNotFound: ...
      await db.commit()
  ```
- Pool listing already filters archived (pattern to copy for `deleted_at`):
  `apps/api/app/leads/repositories.py:408` — `Lead.archived_at.is_(None)`.
- Alembic head is **0051** (`alembic/versions/20260629_0051_lead_sources.py`); next
  free index is **0052**. Model the new migration file on an existing additive one,
  e.g. `alembic/versions/20260611_0048_lead_lookup_indexes.py`.
- Audit helper: `from app.audit.audit import log as log_audit_event`; signature
  `log(session, *, action, workspace_id, user_id=None, entity_type="", entity_id=None, delta=None)`
  (see `apps/api/app/audit/audit.py:22`). Example call site to mirror:
  `apps/api/app/users/routers.py:93`.
- Role guard already exists: `from app.auth.dependencies import require_admin_or_head`
  (`apps/api/app/auth/dependencies.py:57`).

**Convention**: package-per-domain; services own logic, repositories own queries,
routers own HTTP + `db.commit()`. Match the existing style in these three files.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/leads/models.py app/leads/services.py app/leads/repositories.py app/leads/routers.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/leads` | exit 0 |
| Migration check | `cd apps/api && uv run alembic heads` | single head `0052` after step 1 |
| Tests | `cd apps/api && uv run pytest -q tests/test_lead_soft_delete.py` | all pass |

(If `uv` is unavailable on this machine, STOP and report — the migration and DB
tests must run in an environment with Postgres, per `.github/workflows/test.yml`.)

## Scope

**In scope:**
- `apps/api/app/leads/models.py` (add two columns)
- `apps/api/alembic/versions/20260701_0052_lead_soft_delete.py` (create)
- `apps/api/app/leads/repositories.py` (soft_delete / restore / destroy + list filter)
- `apps/api/app/leads/services.py` (soft_delete / restore / destroy + 404-on-deleted)
- `apps/api/app/leads/routers.py` (change DELETE semantics, add restore + permanent + trash-list)
- `apps/api/app/leads/schemas.py` (only if a response/DTO field must expose `deleted_at`)
- `apps/api/tests/test_lead_soft_delete.py` (create)

**Out of scope (do NOT touch):**
- `archived_at` semantics — it is the enrichment-pool filter, a different concept.
- The frontend (`apps/web`) — a follow-up plan wires the Trash UI. Backend + audit first.
- Notes/activities cascade config — soft delete does NOT delete children; they stay
  attached and reappear on restore. Do not change `ondelete` anywhere.
- Any other domain's list queries.

## Git workflow

- Branch: `advisor/009-lead-soft-delete`
- Commit per step; conventional-commit style (match `git log`, e.g.
  `feat(leads): soft-delete + trash/restore, permanent-destroy gated (G? / plan 009)`).
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 1: Add `deleted_at` / `deleted_by` columns + migration

In `models.py`, next to `archived_at` (line 172), add:
```python
deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
deleted_by: Mapped[uuid.UUID | None] = mapped_column(
    ForeignKey("users.id", ondelete="SET NULL"), nullable=True
)
```
Create `alembic/versions/20260701_0052_lead_soft_delete.py` with
`down_revision = "0051"` (confirm the exact revision id string inside
`20260629_0051_lead_sources.py`), adding both columns (nullable) and an index
`ix_leads_workspace_deleted_at` on `(workspace_id, deleted_at)`. Downgrade drops
them.

**Verify**: `cd apps/api && uv run alembic heads` → prints a single head `0052`.
`python -m py_compile app/leads/models.py` → exit 0.

### Step 2: Repository — soft_delete, restore, destroy, and a list filter

In `repositories.py`, rename the existing hard `delete_lead` (line 448) to
`destroy_lead` (it stays the true `db.delete`). Add:
```python
async def soft_delete_lead(db, lead, user_id):
    lead.deleted_at = datetime.now(timezone.utc)
    lead.deleted_by = user_id
    await db.flush()

async def restore_lead(db, lead):
    lead.deleted_at = None
    lead.deleted_by = None
    await db.flush()
```
Add `Lead.deleted_at.is_(None)` to the WHERE of every listing query that returns
active leads. **Find them**: `grep -n "select(Lead)" app/leads/repositories.py`
and add the filter to each list/pool/board query (the same places that already
have `assignment_status`/`archived_at` filters). Add a dedicated
`list_trash(db, workspace_id, ...)` that returns only `deleted_at IS NOT NULL`.

**Verify**: `grep -c "deleted_at.is_(None)" app/leads/repositories.py` → ≥ the
number of active-lead list queries (at least 2). `python -m py_compile` → 0.

### Step 3: Service layer — semantics + 404-on-deleted

In `services.py`:
- Replace `delete_lead` (line 264) with `soft_delete_lead(db, workspace_id, lead_id, user_id)`
  → fetch, 404 if missing, call `repo.soft_delete_lead`.
- Add `restore_lead(db, workspace_id, lead_id)` and
  `destroy_lead(db, workspace_id, lead_id)` (the latter calls `repo.destroy_lead`).
- In `update_lead` (line 239) and any single-lead getter used by the detail/edit
  endpoints, treat a row with `deleted_at is not None` as `LeadNotFound` (a trashed
  lead is not editable until restored). Do NOT apply this to `restore_lead`/`destroy_lead`.

**Verify**: `python -m py_compile app/leads/services.py` → 0.

### Step 4: Router — soft DELETE + restore + permanent + trash list, all audited

In `routers.py`:
- Change `DELETE /{lead_id}` (line 314) to call `services.soft_delete_lead(...)`
  passing `user.id`, then emit `log_audit_event(db, action="lead.soft_delete",
  workspace_id=user.workspace_id, user_id=user.id, entity_type="lead",
  entity_id=lead_id)` before `db.commit()`. Mirror the exact call shape in
  `apps/api/app/users/routers.py:93`.
- Add `POST /{lead_id}/restore` (dep `current_user`) → `services.restore_lead`,
  audit `lead.restore`.
- Add `DELETE /{lead_id}/permanent` (dep **`require_admin_or_head`**) →
  `services.destroy_lead`, audit `lead.destroy`.
- Add `GET /trash` (dep `current_user`) → `services.list_trash`.

**Verify**: `python -m py_compile app/leads/routers.py` → 0;
`grep -n "require_admin_or_head" app/leads/routers.py` → matches the permanent route.

### Step 5: Tests

Create `tests/test_lead_soft_delete.py` modeled on an existing service test that
uses the DB fixtures (e.g. `tests/test_pipelines_service.py`). Cover: soft-delete
sets `deleted_at`/`deleted_by`; a soft-deleted lead is absent from `list_pool`/list
and present in `list_trash`; `restore` clears the flags and it returns to lists;
`update_lead` raises `LeadNotFound` on a trashed lead; `destroy_lead` removes the
row; an audit row is written for soft_delete / restore / destroy.

**Verify**: `cd apps/api && uv run pytest -q tests/test_lead_soft_delete.py` → all pass.

## Test plan

- New file `tests/test_lead_soft_delete.py`, ~7 cases (listed in Step 5).
- Structural pattern: whichever existing `tests/test_*_service.py` already builds a
  workspace + lead against the Postgres fixture.
- Verification: the pytest command above passes with the new tests present.

## Done criteria

- [ ] `uv run alembic heads` → single head `0052`
- [ ] `python -m py_compile` on the 4 touched app files → exit 0
- [ ] `uv run ruff check app/leads` → exit 0
- [ ] `uv run pytest -q tests/test_lead_soft_delete.py` → all pass (≥7 new tests)
- [ ] `grep -n "await db.delete(lead)" app/leads/repositories.py` appears **only**
      inside `destroy_lead`
- [ ] `DELETE /{lead_id}/permanent` depends on `require_admin_or_head`; plain
      `DELETE /{lead_id}` depends on `current_user`
- [ ] No files outside the in-scope list modified (`git status`)
- [ ] `plans/README.md` round-3 status row for 009 updated

## STOP conditions

- The excerpts in "Current state" don't match live code (drift) — report.
- A list query using `select(Lead)` is ambiguous about whether it should hide
  trashed leads (e.g. a merge/dedup query) — STOP and ask rather than guess; a
  wrong filter here either leaks trashed leads or breaks merge.
- `uv`/Postgres is unavailable so the migration and tests cannot be verified — STOP;
  do not mark DONE on `py_compile` alone.
- Adding the filter would require touching a file outside `apps/api/app/leads` — report.

## Maintenance notes

- Frontend Trash UI (list `/leads/trash`, restore button, admin-only permanent) is
  a deliberate follow-up — not in this plan.
- If a future feature needs to *count* leads including trashed (e.g. analytics),
  it must opt in explicitly; the default lists now exclude `deleted_at IS NOT NULL`.
- Reviewer should scrutinize that **every** active-lead list query got the filter
  (Step 2) — a missed one is the main regression risk.
- This resolves the *delete* half of round-2 **B2**; the *edit/move-stage* IDOR half
  of B2 is still open (see plan 010 for the task-mutation slice and B2 for leads).
