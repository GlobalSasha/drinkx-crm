# Plan 017: Outbound webhooks + a generic "call HTTP endpoint" automation action (design/spike + thin first slice)

> **Executor instructions**: This is a **design/spike** plan, not a full build. Produce
> the ADR + the thin first slice described below, run the listed verifications, and
> STOP at the boundaries. Update plan 017's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 9e93b16..HEAD -- apps/api/app/automation_builder apps/api/app/main.py`

## Status

- **Priority**: P2
- **Effort**: M (spike + thin slice; full feature is larger and deferred)
- **Risk**: MED (outbound HTTP from the server → SSRF surface; must reuse the existing SSRF guard)
- **Depends on**: none (benefits from plan 015's reliability work if it lands first)
- **Category**: direction
- **Planned at**: commit `9e93b16`, 2026-07-01

## Why this matters

Twenty fires HMAC-signed outbound webhooks on record lifecycle events and has an
explicit HTTP-request automation action, so a workspace can wire the CRM into
Slack/n8n/Zapier/ERP with zero per-integration code. DrinkX has **no** push-integration
surface at all: our automation action set is the closed trio `send_template |
create_task | move_stage` (`apps/api/app/automation_builder/schemas.py:14`), and there
is no event-subscription registry or delivery mechanism. For a sales shop this blocks
otherwise-impossible use cases — "new lead → Slack alert", "stage → Won → push to ERP",
"quote sent → notify ops". This is the single highest-leverage *integration* gap. This
plan does the design and a **thin, safe first slice**, not the whole system.

## Current state

- Automation actions are a closed union: `ActionType = Literal["send_template",
  "create_task","move_stage"]` (`schemas.py:14`), validated at
  `apps/api/app/automation_builder/services.py:99-113`; dispatched by `_dispatch_step`.
- Triggers exist for `stage_change | form_submission | inbox_match`
  (`automation_builder/models.py:27`) with fan-out hooks already wired (e.g.
  `app/automation/stage_change.py` POST_ACTION).
- **Inbound** webhooks exist (`app/inbox/webhooks.py`) but there is no **outbound**
  delivery anywhere (`grep -rn "outbound\|webhook.*send\|deliver" apps/api/app` → only
  inbound handlers + internal SMTP).
- An SSRF guard already exists and is used by the enrichment fetch (round-1 plan 002 —
  `is_safe_fetch_url` in the enrichment sources). **Reuse it** for any outbound HTTP.
- Celery + a post-commit dispatch pattern already exist
  (`app/automation_builder/dispatch.py` — post-commit email queue) to model async
  delivery on.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Compile | `cd apps/api && python -m py_compile app/automation_builder/services.py` | exit 0 |
| Lint | `cd apps/api && uv run ruff check app/automation_builder` | exit 0 |
| Tests | `cd apps/api && uv run pytest -q tests/test_http_request_action.py` | all pass |

## Deliverables

### A. ADR: `docs/adr/ADR-0XX-outbound-webhooks.md`

Write a short ADR deciding:
- **Two shapes, one mechanism**: (1) a generic `http_request` **automation action**
  (fires as a step in a rule the user already builds) and (2) event **subscriptions**
  (a registry of `{event, url, secret}` that fire on record lifecycle events). Decide
  whether to ship both or start with the action only (recommended: **action first** —
  it reuses the existing rule engine and needs no new subscription table).
- **Security**: HMAC-SHA256 signature header (`X-DrinkX-Signature`) over the raw body
  with a per-endpoint secret; mandatory SSRF validation via the existing guard on every
  URL (and on redirects); an allowlist/denylist decision (internal IPs blocked);
  timeouts + no unbounded retries (bounded, dead-letter to a step-run `failed`).
- **Payload**: signed JSON envelope `{event, occurred_at, workspace_id, data}`; which
  entities/events are exposed in v1 (recommend `lead.created`, `lead.stage_changed`,
  `quote.sent`).
- **Delivery**: async via Celery / the post-commit queue (never block the request);
  reuse plan 015's retry semantics if present.

### B. Thin first slice: `http_request` automation action

Implement **only** the generic HTTP action as a new step/action type:
1. Extend `ActionType`/`StepType` with `http_request` and validate its config
   (`{method, url, headers?, body_template?}`) in the `_validate_*` path.
2. Implement `_dispatch_step` handling for `http_request`: build the payload, **call
   the existing SSRF guard on the URL (and every redirect hop)**, sign the body with
   an HMAC secret from config/workspace settings, POST with a hard timeout via `httpx`,
   and record the outcome on the step-run (`success`/`failed` with status+reason). Run
   it through the async/post-commit path — never inline in the triggering request.
3. Do **not** add the event-subscription registry in this slice (that's the ADR's
   "phase 2"); the action already lets a user say "on stage change → POST to X".

**Verify**: `grep -n "http_request" app/automation_builder/schemas.py app/automation_builder/services.py`
→ present; `python -m py_compile app/automation_builder/services.py` → 0.

### C. Tests: `tests/test_http_request_action.py`

Cases (mock `httpx` + the SSRF guard): a valid external URL → POST fired with a valid
`X-DrinkX-Signature`; an internal/blocked URL → **not** fetched, step `failed`
(the critical SSRF assertion — `route.called is False`, mirroring plan 002's test); a
timeout → step `failed`, no crash; signature is computed over the exact body sent.

**Verify**: `cd apps/api && uv run pytest -q tests/test_http_request_action.py` → all pass.

## Scope

**In scope:**
- `docs/adr/ADR-0XX-outbound-webhooks.md` (create — use the repo's ADR numbering)
- `apps/api/app/automation_builder/schemas.py` + `services.py` (the `http_request` action only)
- `apps/api/tests/test_http_request_action.py` (create)

**Out of scope (this slice):**
- The event-subscription registry / table + a settings UI to manage endpoints — ADR
  "phase 2", separate plan.
- Frontend: exposing `http_request` in the automations builder UI — follow-up.
- Any outbound HTTP that bypasses the SSRF guard — forbidden.

## Git workflow

- Branch: `advisor/017-outbound-http-action`
- Commits: one for the ADR, one for the action + tests. Message e.g.
  `feat(automation): generic http_request action + outbound-webhooks ADR (plan 017)`.

## Done criteria

- [ ] `docs/adr/ADR-0XX-outbound-webhooks.md` exists and decides action-vs-subscription,
      signing, SSRF, payload, delivery
- [ ] `http_request` action type validates config and dispatches via the async path
- [ ] Every outbound URL (incl. redirects) passes the existing SSRF guard before any request
- [ ] `uv run pytest -q tests/test_http_request_action.py` → all pass, incl. the
      "blocked URL is never requested" assertion
- [ ] `python -m py_compile app/automation_builder/services.py` → 0; `uv run ruff check` → 0
- [ ] No event-subscription table added in this slice (`git status` shows no new migration)
- [ ] `plans/README.md` round-3 row for 017 updated

## STOP conditions

- The SSRF guard (`is_safe_fetch_url` or equivalent from plan 002) cannot be imported
  from the automation package cleanly — STOP and decide where it should live (promote
  to `app/common`) before shipping outbound HTTP. **Do not ship outbound HTTP without
  the guard.**
- Signing-secret storage is unclear (per-workspace vs per-endpoint) — resolve in the
  ADR before coding B; if it needs a new table, that belongs in phase 2, so for the
  slice use a single config-level secret and note the limitation.
- The action would let a user POST to arbitrary internal services despite the guard —
  STOP and tighten the allowlist.

## Maintenance notes

- Phase 2 (event-subscription registry + management UI + `*.deleted`/`*.updated`
  events) is the natural follow-up once the action ships and the ADR is approved.
- This unblocks the round-2 "real outbound from the lead card" structural gap from the
  integration side.
- Reviewer must treat this as security-sensitive: the SSRF guard + signature + timeout
  are non-negotiable on every outbound call.
