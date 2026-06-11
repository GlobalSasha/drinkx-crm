# Plan 004: Dedup contacts, then enforce a UNIQUE constraint (CORR-2)

> **Executor instructions**: Follow step by step. Run every verification command.
> If a STOP condition occurs, stop and report. Update this plan's row in
> `plans/README.md` when done.
>
> **REQUIRES A POSTGRES DB and is DATA-MUTATING.** Step 2 deletes/merges duplicate
> rows. Do NOT run against production without a backup/snapshot and without first
> running Step 1's read-only count on prod data. The migration in Step 3 will FAIL
> if duplicates still exist — that is by design (it proves the dedup worked).
>
> **Drift check (run first)**:
> `git diff --stat a32b1a6..HEAD -- apps/api/app/contacts/ apps/api/app/inbox/processor.py apps/api/app/import_export/diff_engine.py apps/api/app/common/backfill.py`
> On a mismatch with "Current state", STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED-HIGH (deletes duplicate rows; migration fails if data still dirty)
- **Depends on**: none (independent of 003)
- **Category**: bug (data integrity)
- **Planned at**: commit `a32b1a6`, 2026-06-11

## Why this matters

Contact de-duplication is enforced only in application code (check-then-act): the
inbox processor and import diff-engine query for an existing contact, then insert
if absent. Under concurrent workers (two emails for the same lead processed at
once) both can pass the check and insert, creating **duplicate contacts** with the
same email on one lead. There is **no database constraint** to stop it. The fix is
the standard one: dedup existing rows, add a UNIQUE index, and make inserts handle
the conflict.

## Current state

- `apps/api/app/contacts/models.py` — `Contact` has `lead_id` (FK, indexed),
  `email` and `email_normalized` (indexed via `@validates`, nullable), `phone_e164`
  (indexed). **No `UniqueConstraint` / unique index.** Multiple contacts on a lead
  with the same `email_normalized` are currently allowed.
- `apps/api/app/common/backfill.py` — existing one-off backfill module
  (`backfill_normalized_keys`, `_backfill_contacts`). **Use it as the structural
  pattern** for the dedup function (same batching/session style).
- App-level dedup sites that insert contacts (the check-then-act to harden):
  inbox processing path and `apps/api/app/import_export/diff_engine.py` (the
  `contacts.add` branch). Grep `email_normalized` / contact insert in those files
  to find the exact spots.

Chosen uniqueness key: **`(lead_id, email_normalized)`**, as a **PARTIAL** unique
index `WHERE email_normalized IS NOT NULL` — because `email_normalized` is nullable
and we must allow many contacts-without-email on the same lead. Phone is NOT part
of the key (a person may appear with email on one channel, phone on another).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Tests (DB) | `cd apps/api && uv run pytest tests/test_contact_dedup.py -q` | all pass |
| Backfill tests | `cd apps/api && uv run pytest -q -k "backfill or contact"` | all pass |
| Lint/type | `cd apps/api && uv run ruff check app/common/backfill.py && uv run mypy app/common/backfill.py` | exit 0 |
| Migration (DB) | `cd apps/api && uv run alembic upgrade head` | succeeds AFTER dedup; FAILS if dupes remain |

Requires `TEST_DATABASE_URL`. A skipped DB test here is a STOP condition.

## Scope

**In scope:**
- `apps/api/app/common/backfill.py` — add a `dedup_contacts()` function.
- `apps/api/alembic/versions/<next>_contact_email_unique.py` — create (next revision
  after the current head; run `uv run alembic heads` to find it — at plan time the
  head is `0048_lead_lookup_indexes`).
- The contact-insert sites (inbox processor + `import_export/diff_engine.py`) —
  make insert tolerate the constraint (catch `IntegrityError` / use
  `ON CONFLICT DO NOTHING` via `postgresql.insert`).
- `apps/api/tests/test_contact_dedup.py` — create.

**Out of scope:**
- The `Contact` model's columns/validators — no column changes; the unique index is
  added via migration + (optionally) an `Index(..., unique=True)` in `__table_args__`
  to keep model and DB in sync. If you add it to the model, it must be a partial
  index matching the migration exactly.
- Lead-level dedup (that's a different, already-shipped feature).

## Steps

### Step 1: Count duplicates (read-only — run on prod data too before deploying)

Write a one-off query / test that reports, per workspace, how many `(lead_id,
email_normalized)` groups have >1 row where `email_normalized IS NOT NULL`. Record
the number. If it's zero everywhere, Step 2 is a no-op (but keep it — prod may
differ). **Run the equivalent SELECT against the production DB before the deploy**
so you know whether the migration will need the dedup to have run.

**Verify**: query runs, prints a count.

### Step 2: Add and test `dedup_contacts()`

In `app/common/backfill.py`, add `async def dedup_contacts(db, *, batch_size=...)`
following the existing `_backfill_contacts` pattern. For each `(lead_id,
email_normalized)` group with >1 row (email not null): keep the OLDEST (lowest
`created_at`, tie-break by id), and for the others — reassign anything that FKs to
them if applicable, then delete. (Contacts are referenced by `leads.primary_contact_id`;
before deleting a duplicate, if a lead's `primary_contact_id` points at a
soon-to-be-deleted dup, repoint it to the kept row.) Return rows deleted.

**Verify**: `uv run pytest tests/test_contact_dedup.py -q` — a test that seeds 2
duplicate contacts on one lead, runs `dedup_contacts`, asserts exactly 1 remains
and `primary_contact_id` (if it pointed at the dup) now points at the survivor.

### Step 3: Migration — dedup then create the partial unique index

Create the next migration (revises the current head). `upgrade()`:
1. Run the dedup inline (raw SQL or call into a SQL block) so the index can be
   created safely even on a DB where the app-level backfill wasn't invoked. A
   pure-SQL dedup using a window function is robust:
   ```sql
   DELETE FROM contacts c USING (
     SELECT id, row_number() OVER (
       PARTITION BY lead_id, email_normalized ORDER BY created_at, id
     ) AS rn
     FROM contacts WHERE email_normalized IS NOT NULL
   ) d
   WHERE c.id = d.id AND d.rn > 1;
   ```
   (If `leads.primary_contact_id` may reference a deleted row, repoint those first
   with an UPDATE — write it; don't skip it.)
2. Create the partial unique index:
   ```python
   op.create_index(
       "uq_contacts_lead_email_normalized",
       "contacts",
       ["lead_id", "email_normalized"],
       unique=True,
       postgresql_where=sa.text("email_normalized IS NOT NULL"),
   )
   ```
`downgrade()` drops the index (does not un-dedup).

**Verify**: against a DB seeded with duplicates, `uv run alembic upgrade head`
succeeds and the index exists; a second insert of the same `(lead_id, email)` then
raises `IntegrityError`.

### Step 4: Make app-level inserts conflict-tolerant

At the contact-insert sites (inbox processor + `import_export/diff_engine.py`
`contacts.add` branch), wrap the insert so a unique-violation is swallowed as
"already exists" rather than crashing the whole operation — either catch
`sqlalchemy.exc.IntegrityError` and continue, or use
`postgresql.insert(...).on_conflict_do_nothing(index_elements=[...])`. Keep the
existing check-then-act as the fast path; the constraint is the backstop.

**Verify**: a test that calls the insert path twice concurrently (or sequentially
within one session after the constraint exists) and asserts no exception escapes
and exactly one row exists.

## Done criteria

- [ ] `uv run pytest tests/test_contact_dedup.py -q` → all pass (NOT skipped)
- [ ] `uv run alembic upgrade head` succeeds on a DB seeded with duplicate contacts
- [ ] partial unique index `uq_contacts_lead_email_normalized` exists and rejects a duplicate insert
- [ ] inserting an existing `(lead_id, email)` via the app path does not raise
- [ ] `uv run pytest -q -k "contact or inbox or import"` → no regression
- [ ] ruff + mypy clean on touched files
- [ ] `plans/README.md` row updated

## STOP conditions

- DB tests skip (no Postgres) — report.
- Step 1 finds a LARGE number of duplicates on prod (e.g. thousands) — report before
  running the destructive dedup; a human should review the merge policy first.
- A duplicate contact is referenced by FKs you didn't anticipate (beyond
  `primary_contact_id`) — STOP and report rather than cascade-deleting blindly.

## Maintenance notes

- After this, the app-level check-then-act in the dedup sites is an optimization,
  not the guarantee — the DB constraint is. A reviewer should confirm both inbox
  and import paths handle the conflict gracefully (no 500s on a race).
- If a future feature legitimately needs two contacts with the same email on one
  lead (it shouldn't), this constraint is what they'll hit first.
