# Plan 016: Stop silently "succeeding" on tg/sms automation templates — reject at save or mark the step skipped

> **Executor instructions**: Follow step by step; run every verification command.
> Honor STOP conditions. Update plan 016's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/automation_builder`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `9e93b16`, 2026-07-01

## Why this matters

A `send_template` action on a non-email (tg/sms) template writes an Activity with
`delivery_status='pending'` and returns **without any provider call**, and the step is
recorded as **success**. So a manager who configures an automation with a Telegram or
SMS template sees "success" while the message is never sent — a false positive that is
strictly worse than a visible failure, and sticky `pending` Activities accumulate.
Until real tg/sms dispatch exists, the honest behavior is to either reject such
templates when the rule is saved, or mark the step `skipped` (with a reason) rather
than `success`.

## Current state

`apps/api/app/automation_builder/services.py` around line 835:
```python
# Non-email channels (tg / sms) — Sprint 2.5 stub stays.
...
payload["outbound_pending"] = True          # ~line 839 — no provider call
# Activity written delivery_status='pending'; step recorded as success
```
- Step run status literal includes `skipped` already:
  `StepRunStatus = Literal["pending","success","skipped","failed"]`
  (`apps/api/app/automation_builder/schemas.py:17`) — so "skipped" is a first-class
  outcome we can use with no migration.
- Template channel is on the template record (`app/template/`); a rule references a
  template. Rule creation/validation is in
  `apps/api/app/automation_builder/services.py` (the `create_automation` /
  `_validate_*` path) and the action config is validated at ~line 99-113.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/automation_builder/services.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/automation_builder` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_automation_channel_visibility.py` | all pass |

## Scope

**In scope:**
- `apps/api/app/automation_builder/services.py` (the send-template action path + optionally rule-save validation)
- `apps/api/tests/test_automation_channel_visibility.py` (create)

**Out of scope:**
- Implementing real tg/sms dispatch (that's a feature, not this fix).
- The email path (works correctly).
- The Activity model / delivery_status column.

## Git workflow

- Branch: `advisor/016-channel-visibility`
- One commit: `fix(automation): tg/sms template steps report skipped, not false success (plan 016)`.

## Steps

### Step 1: Mark the step `skipped` with a reason instead of `success`

In the `send_template` action path, when the resolved template's channel is not email
(tg/sms), set the step-run outcome to `skipped` with an explicit reason
(e.g. `"channel_not_implemented:tg"`) instead of `success`, and keep the Activity but
label it so it doesn't read as "sent" (or don't write a sticky `pending` Activity at
all — pick one and document it). Do not raise (that would fail the whole run); a
`skipped` outcome is the honest state.

**Verify**: `grep -n "skipped\|channel_not_implemented" app/automation_builder/services.py`
→ present in the send path. `python -m py_compile` → 0.

### Step 2 (recommended): Reject tg/sms templates at rule save time

In the rule create/update validation (`_validate_*` near line 99-113), if a
`send_template` action/step references a non-email template, raise a 400-mapped
validation error ("channel not yet supported for automations"). This stops the
misconfiguration at authoring time (best UX) while Step 1 keeps any already-saved
rules honest at runtime. If template channel isn't easily resolvable at validation
time (needs a DB fetch), keep Step 1 only and note it.

**Verify**: `grep -n "def _validate" app/automation_builder/services.py` path raises
on non-email template. `python -m py_compile` → 0.

### Step 3: Tests

Create `tests/test_automation_channel_visibility.py`. Cases: a `send_template` step on
a tg/sms template → step outcome `skipped` (not `success`) with a reason; an email
template → still `success`; (if Step 2 done) creating a rule with a tg/sms template →
validation error. Model after existing automation service tests.

**Verify**: `cd apps/api && uv run pytest -q tests/test_automation_channel_visibility.py` → all pass.

## Test plan

- New `tests/test_automation_channel_visibility.py`, ~3 cases (Step 3).
- Pattern: existing automation service tests.
- Verification: pytest command passes.

## Done criteria

- [ ] `python -m py_compile app/automation_builder/services.py` → 0
- [ ] `uv run ruff check app/automation_builder` → 0
- [ ] `uv run pytest -q tests/test_automation_channel_visibility.py` → all pass
- [ ] A tg/sms `send_template` step is recorded as `skipped` (not `success`)
- [ ] No files outside scope modified (`git status`)
- [ ] `plans/README.md` round-3 row for 016 updated

## STOP conditions

- Excerpts don't match live code (drift) — report.
- Marking the step `skipped` breaks a downstream assumption that every non-failed step
  is `success` (e.g. multi-step chain progression keys on `success`) — if a `skipped`
  step would wrongly halt or wrongly continue a chain, STOP and confirm the intended
  chain semantics for `skipped`.

## Maintenance notes

- When real tg/sms dispatch lands, remove the reject/skip and wire the provider call;
  the tests here should then flip to asserting a real dispatch.
- Relates to plan 015 (`skipped` as a first-class outcome) — keep the reason strings consistent.
