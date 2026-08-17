# Plan 021: Make the automation `http_request` action safe — defer past commit, no double-fire, pin the resolved IP

> **Executor instructions**: Follow step by step. Run every verification
> command. Honor STOP conditions. Update this plan's row in `plans/README.md`
> when done. This plan has three linked but separable fixes (A, B, C); do them
> in order, each is independently verifiable.
>
> **Drift check (run first)**: `git diff --stat 493a962..HEAD -- apps/api/app/automation_builder/services.py apps/api/app/automation_builder/dispatch.py apps/api/app/common/ssrf.py`
> If any changed, compare against "Current state" before proceeding; on a
> mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (but coordinate with round-3 plan 015 automation retry)
- **Category**: security + bug
- **Planned at**: commit `493a962`, 2026-07-18

## Why this matters

The automation `http_request` action makes a live outbound network call inside
an open DB transaction, before the triggering transaction commits. Three
distinct problems:

- **(A) Fires before commit / blocks the request.** `send_template` was
  deliberately moved to a post-commit queue (`dispatch.py`) to avoid exactly
  this; `http_request` was not. So a webhook can be delivered for a lead state
  that later rolls back, and the user-facing action (stage change, public form
  POST) blocks synchronously up to ~40s (10s × up to 4 hops) holding a DB
  connection — an availability lever driven by external request volume, on a
  path reachable from *unauthenticated public form submissions*.
- **(B) Retry double-fires the webhook.** The step-retry invariant assumes a
  failed SAVEPOINT rolls back everything the handler staged. That holds for
  DB-only handlers, but `http_request` already sent its webhook before a
  commit-phase failure; the retry sends it a **second time**.
- **(C) DNS-rebinding TOCTOU.** `is_safe_fetch_url(url)` resolves + validates
  the host, then `httpx` resolves it **again** at connect time; a host can
  resolve to a public IP during the check and to `169.254.169.254`/RFC1918 at
  connect. Because this action sends attacker/author-controlled method + body +
  headers, a successful rebind is a full write to an internal service.

## Current state

- `apps/api/app/automation_builder/services.py:655-702` — step 0 runs
  synchronously inside `async with db.begin_nested():` (`:675`), calling
  `_dispatch_step(...)` (`:682`). This whole block executes inside the caller's
  hot-path transaction (stage_change / form-create / inbox-attach) *before* the
  caller commits.
- `apps/api/app/automation_builder/services.py:1180-1246` — `_http_request_action`:
  ```python
  if not is_safe_fetch_url(url):            # :1185  guard (resolves + validates)
      raise HttpRequestBlocked(...)
  # ... builds signed body/headers ...
  async with httpx.AsyncClient(timeout=_HTTP_REQUEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
      resp = await client.request(method, current_url, ...)   # :1219  re-resolves DNS
      while resp.is_redirect and redirects < _HTTP_REQUEST_MAX_REDIRECTS:
          if not is_safe_fetch_url(next_url): raise ...        # :1232  redirects re-validated
  ```
  `_HTTP_REQUEST_TIMEOUT_SECONDS` / `_HTTP_REQUEST_MAX_REDIRECTS` are module
  constants (search near the top of the file).
- `apps/api/app/automation_builder/dispatch.py` — the post-commit pattern to
  mirror: `PendingDispatch` entries are appended during the action and flushed
  by `flush_pending_email_dispatches(queue)` **after** the caller's
  `session.commit()` (see `services.py:1282,1345`). `http_request` does NOT use
  this deferral for step 0.
- `apps/api/app/common/ssrf.py:22-42` — `is_safe_fetch_url` returns a bool;
  `is_public_host`/IP validation lives here. It resolves the host but does not
  return the pinned IP.
- Retry path: `services.py:1329-1385` — on a transient error the step_run row
  is re-queued (`_is_transient_step_error`, `:116`); the docstring invariant is
  at `:88-98`.

## Commands you will need

| Purpose        | Command                                                                 | Expected on success |
|----------------|-------------------------------------------------------------------------|---------------------|
| Compile check  | `cd apps/api && python -m py_compile app/automation_builder/services.py` | exit 0     |
| Related tests  | `cd apps/api && uv run pytest -q tests/test_http_request_action.py tests/test_automation_reliability.py tests/test_automation_multistep.py` | all pass |

> DB/network tests may need Postgres + mocking; if unavailable locally, compile
> check is the local gate, pytest runs in CI. State clearly what you ran.

## Scope

**In scope**:
- `apps/api/app/automation_builder/services.py`
- `apps/api/app/common/ssrf.py` (add a resolve-and-pin helper for fix C)
- `apps/api/tests/test_http_request_action.py` (extend)

**Out of scope**:
- `send_template` / email dispatch path — already correct; use it only as the
  pattern reference.
- The cascade depth guard (round-2 B4 / round-3 plan 015) — do not re-open it;
  just make sure your retry change doesn't defeat it.
- `web_fetch.py` (round-1 plan 002) — different action, leave it.

## Git workflow

- Branch: `advisor/021-http-request-safety`
- Commit style: one commit per fix, e.g.
  `fix(automation): defer http_request past commit (no pre-commit webhook)`
- Do NOT push or open a PR unless the operator asks.

## Steps

### Fix A — defer `http_request` step 0 past commit

Route a step-0 `http_request` through the same post-commit path as email
instead of executing it inside `begin_nested()`. Two acceptable approaches
(pick the one that fits the existing queue design after reading `dispatch.py`):
1. **Preferred**: when step 0's action type is `http_request`, do NOT dispatch
   it inside the savepoint; instead append it to the post-commit dispatch queue
   (a new `PendingDispatch` kind, or a sibling queue) that
   `flush_pending_*` drains after `session.commit()`.
2. **Simpler fallback**: always schedule `http_request` as a scheduler-driven
   step run (steps 1+ path via the beat scheduler), even when authored as step
   0, so no external call ever happens inside the trigger transaction.

Whichever path, the external call must not run inside the caller's open
transaction.

**Verify**: `python -m py_compile app/automation_builder/services.py` → exit 0;
then add/keep a test asserting that when a trigger's transaction rolls back, no
HTTP request was made (mirror the round-1 SSRF test style: assert the mocked
transport's `called is False`). Run
`uv run pytest -q tests/test_http_request_action.py`.

### Fix B — a commit-phase failure must not re-run the dispatch

In the retry logic (`services.py:1329-1385`), distinguish "dispatch failed
(savepoint rolled back, nothing sent)" from "dispatch succeeded but the commit
failed (webhook already sent)". Only the former may retry the dispatch. Options:
- Gate `http_request` retries behind an idempotency key the receiver can
  dedupe on (include a stable `event_id` in the signed body and in a header),
  and/or
- Mark the step_run as "delivered, commit-pending" after a successful send so a
  subsequent tick does not re-send — it only re-attempts the DB bookkeeping.

Choose the approach consistent with how `PendingDispatch` already guards email
(`dispatch.py` "skip rows whose … " comment at `services.py:1329`).

**Verify**: add a test that simulates a transient commit-time error *after* a
successful send and asserts the webhook is sent exactly once. Run
`uv run pytest -q tests/test_automation_reliability.py`.

### Fix C — resolve once, validate, pin the IP for the connection

In `apps/api/app/common/ssrf.py`, add a helper that resolves the host to an IP,
validates that IP with the existing `is_public_host` logic, and returns the
pinned IP (or raises). Then in `_http_request_action`, connect to the pinned IP
while preserving the original `Host` header and TLS SNI (httpx supports this
via a custom resolver/transport, or by connecting to the IP with
`headers["Host"]` set and `extensions` for SNI). Apply the same resolve-then-pin
to each redirect hop. If pinning cleanly is not feasible without a larger
refactor, at minimum document the residual TOCTOU and keep the redirect
re-validation — but prefer real pinning since this action is write-capable.

**Verify**: `python -m py_compile app/common/ssrf.py` → exit 0; add a test that
a host resolving to a private IP is rejected before any connection.

## Test plan

- Extend `apps/api/tests/test_http_request_action.py`:
  - rollback-of-trigger ⇒ transport never called (Fix A),
  - commit-time transient error after send ⇒ exactly one send (Fix B),
  - host resolving to private IP ⇒ blocked, no connection (Fix C).
- Pattern: the existing SSRF/dispatch tests in
  `test_http_request_action.py` and round-1 `test_web_fetch_ssrf.py`.
- Verification: the three pytest files in "Commands you will need" all pass.

## Done criteria

- [ ] `python -m py_compile app/automation_builder/services.py app/common/ssrf.py` exits 0
- [ ] No `client.request(` executes inside `db.begin_nested()` for `http_request`
      (verify by reading the step-0 path; the call is now post-commit or scheduler-driven)
- [ ] New tests for A, B, C exist and pass (or deferred to CI, explicitly stated)
- [ ] `uv run pytest -q tests/test_http_request_action.py tests/test_automation_reliability.py` passes
- [ ] No files outside the in-scope list modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- The `services.py` step-0 / `_http_request_action` excerpts don't match live
  code (drift) — the automation engine is churning; re-anchor before editing.
- Fix A's queue integration is ambiguous (unclear how to add a non-email
  `PendingDispatch` kind) — STOP and report; do not bolt on a second parallel
  queue mechanism without confirming the design.
- Fix C's IP-pinning would require replacing the httpx client wholesale or
  breaks TLS SNI for CDN-fronted hosts in a test — fall back to documenting the
  residual risk and ship A+B; report C as deferred.

## Maintenance notes

- If any NEW outbound action type is added (SMS, generic API call), it must use
  the same post-commit deferral and IP-pinning — not run inside the trigger
  transaction. Add a shared helper so the next action can't repeat this.
- Reviewer should confirm: (1) no external I/O inside `begin_nested()` on the
  hot path; (2) retry cannot double-send; (3) the SSRF guard validates the same
  IP that is connected to.
- Coordinate with plan 015 (retry/backoff) so a retry can't feed a cascade loop
  (round-2 B4) — the depth guard `_cascade_depth` must still bound re-entry.
