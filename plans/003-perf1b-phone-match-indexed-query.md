# Plan 003: Make inbox phone-match use an indexed query (PERF-1 part B)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. Update this plan's
> row in `plans/README.md` when done (unless a reviewer says they maintain it).
>
> **REQUIRES A POSTGRES TEST DB.** This plan changes phone-matching semantics; it
> MUST be verified with DB-backed tests. Do not attempt without a working
> `TEST_DATABASE_URL` (the suite skips DB tests when Postgres is absent — a skip
> here is a STOP condition).
>
> **Drift check (run first)**:
> `git diff --stat a32b1a6..HEAD -- apps/api/app/inbox/message_services.py apps/api/app/leads/models.py apps/api/app/common/phone.py`
> If in-scope files changed, compare against the "Current state" excerpts; on a
> mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (changes which leads match an inbound phone)
- **Depends on**: plans/README "PERF-1 part A" indexes (migration 0048) — already DONE
- **Category**: perf
- **Planned at**: commit `a32b1a6`, 2026-06-11

## Why this matters

When an inbound Telegram/MAX message can't be matched by channel id, `match_lead`
falls back to phone matching by **loading every workspace lead that has a phone
and normalizing each in Python** — an O(N) scan + per-row CPU on every such
message. At a few thousand leads this measurably slows inbound handling.

The fix is to match against an indexed column instead of scanning. The catch
(why this is part B and needs care): the scan uses `normalize_phone` (bare
digits, RU 7/8→10), while the indexed `phone_e164` column is filled by `to_e164`
(true E.164 via the `phonenumbers` lib, or NULL if invalid). They are **different
normalizations**, so a naive swap changes which messages match. This plan makes
the change deliberately and pins the behavior with tests.

## Current state

Files in scope:
- `apps/api/app/inbox/message_services.py` — `match_lead` + `normalize_phone`.
- `apps/api/app/leads/models.py` — `Lead.phone_e164` (indexed, line ~89) and the
  composite indexes added in migration 0048.
- `apps/api/app/common/phone.py` — `to_e164(raw, region="RU")` (read-only context).

The phone fallback today (`message_services.py`, ~line 138-160):

```python
    # Phone fallback — also covers messenger users who shared their number.
    norm = normalize_phone(sender_id)
    if norm:
        res = await session.execute(
            select(Lead.id, Lead.phone)
            .where(Lead.workspace_id == workspace_id)
            .where(Lead.phone.is_not(None))
        )
        for lead_id, lead_phone in res.all():
            if normalize_phone(lead_phone) == norm:
                return lead_id
    return None
```

`normalize_phone` (same file, ~line 77): "Strip everything except digits; collapse
RU leading 7/8 to 10 digits." Returns bare digits like `"9161234567"`.

`to_e164` (`app/common/phone.py`): returns `"+79161234567"` or `None` if invalid.

So `Lead.phone_e164` is `+E.164`; `normalize_phone` output is bare digits. They are
NOT directly comparable.

## The decision (read before coding)

Two viable approaches — **this plan takes Approach A**; if Approach A's
characterization test (Step 3) shows it drops matches that the old loop made,
STOP and report so a human can choose Approach B.

- **Approach A (recommended, simplest):** normalize the sender with the SAME
  function that fills the column, and query the index:
  `where(Lead.workspace_id == ws, Lead.phone_e164 == to_e164(sender_id))`.
  Trade-off: only matches when BOTH sides are valid E.164. Messy/unparseable
  stored numbers (where `phone_e164` is NULL) won't match — but those are also the
  numbers the old digit-loop matched only by luck.
- **Approach B (preserves exact old semantics):** add a new indexed column
  `phone_digits` populated by `normalize_phone` via a `@validates` hook + a
  backfill, and query that. More work + a migration; only do this if Approach A
  loses real matches.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Tests (DB) | `cd apps/api && uv run pytest tests/test_inbox_phone.py tests/test_inbox_matcher.py -q` | all pass |
| New test | `cd apps/api && uv run pytest tests/test_inbox_phone_indexed.py -q` | all pass |
| Lint | `cd apps/api && uv run ruff check app/inbox/message_services.py` | exit 0 |
| Typecheck | `cd apps/api && uv run mypy app/inbox/message_services.py` | exit 0 |

`TEST_DATABASE_URL` must point at a reachable Postgres (default
`postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test`). If the new test is
SKIPPED for lack of a DB, that's a STOP condition.

## Scope

**In scope:**
- `apps/api/app/inbox/message_services.py` — replace the phone-fallback loop.
- `apps/api/tests/test_inbox_phone_indexed.py` — create (characterization + new behavior).

**Out of scope:**
- `app/common/phone.py`, `normalize_phone` itself — don't change normalization rules.
- The channel-id lookups (tg_chat_id / max_user_id) above the phone fallback — they
  already use the 0048 indexes; leave them.
- Approach B's new column — only if Step 3 forces it, and then STOP first.

## Steps

### Step 1: Characterize current behavior (write the safety net FIRST)

Create `tests/test_inbox_phone_indexed.py`. Using the `db`/`workspace` fixtures
(see `tests/conftest.py`), seed leads with a mix of phone formats and assert what
`match_lead` returns TODAY (before changing code), for inputs:
- a clean `+7 916 123-45-67` matching a lead stored as `8(916)123-45-67`,
- a sender that is a valid E.164,
- a sender that is NOT a valid phone (e.g. a messenger handle),
- no matching lead.

Run it against the unchanged code; record the expected lead ids. These assertions
are the contract the refactor must preserve.

**Verify**: `uv run pytest tests/test_inbox_phone_indexed.py -q` → passes against current code.

### Step 2: Replace the loop with an indexed query (Approach A)

In `match_lead`, replace the fallback loop body with:

```python
    e164 = to_e164(sender_id)
    if e164:
        res = await session.execute(
            select(Lead.id)
            .where(Lead.workspace_id == workspace_id)
            .where(Lead.phone_e164 == e164)
            .limit(1)
        )
        hit = res.scalar_one_or_none()
        if hit is not None:
            return hit
    return None
```

Add `from app.common.phone import to_e164` to the imports. Remove the now-unused
`normalize_phone` call here **only if** `normalize_phone` is no longer used
anywhere in the file (grep first; it may be used elsewhere — if so, leave it).

**Verify**: `grep -n "for lead_id, lead_phone" apps/api/app/inbox/message_services.py` → no matches.

### Step 3: Re-run the characterization test and judge

Run the Step 1 test against the new code.
- If all assertions still pass → Approach A preserved behavior. Good.
- If a previously-matching case now returns None (Approach A is stricter) → **STOP
  and report** with the specific case. Do not silently accept lost matches; the
  human decides whether that case matters or whether Approach B is needed.

**Verify**: `uv run pytest tests/test_inbox_phone_indexed.py -q` → all pass, OR STOP.

## Test plan

- `tests/test_inbox_phone_indexed.py`: the 4 characterization cases above, plus an
  explicit assertion that a workspace with N>0 leads matches by a single indexed
  query (you may assert via behavior, not query count).
- Pattern: model on existing `tests/test_inbox_phone.py` / `test_inbox_matcher.py`.

## Done criteria

- [ ] `uv run pytest tests/test_inbox_phone_indexed.py -q` → all pass (NOT skipped)
- [ ] `uv run pytest tests/test_inbox_phone.py tests/test_inbox_matcher.py -q` → no regression
- [ ] `grep -n "for lead_id, lead_phone" apps/api/app/inbox/message_services.py` → no matches
- [ ] `uv run ruff check app/inbox/message_services.py` → exit 0
- [ ] `uv run mypy app/inbox/message_services.py` → exit 0
- [ ] only the two in-scope files modified
- [ ] `plans/README.md` row updated

## STOP conditions

- The new test is skipped (no Postgres) — you cannot verify; report.
- Step 3 shows Approach A loses a match the old loop made — report the case; do not
  proceed to Approach B without sign-off.
- `normalize_phone` turns out to be relied on by other call sites you'd break.

## Maintenance notes

- After this lands, `normalize_phone` may be dead in this file — if so, a follow-up
  can remove it (only if no other module imports it).
- The 0048 index `ix_leads_workspace_*` plus the existing `ix_leads_phone_e164`
  cover this query; no new index needed for Approach A.
