# ADR-022: Outbound webhooks — generic `http_request` automation action first

- **Status**: Accepted (slice A — action only; slice B deferred)
- **Date**: 2026-07-01
- **Related**: plan 017 (round-3 audit), ADR-009 (package-per-domain),
  ADR-007 (AI proposes / human-in-the-loop — n/a here, no AI involved),
  `app/common/ssrf.py` (round-1 plan 002 SSRF guard)

## Context

DrinkX's automation builder has a closed action set: `send_template |
create_task | move_stage` (`app/automation_builder/schemas.py`). There is no
way for a workspace to push CRM events into external systems (Slack, n8n,
Zapier, an ERP). Twenty CRM ships both an HMAC-signed outbound webhook
system tied to record lifecycle events, and a generic HTTP-request
automation action. DrinkX has neither. This blocks "new lead → Slack alert",
"stage → Won → push to ERP", "quote sent → notify ops" — all common asks
from a B2B sales shop wiring the CRM into whatever else they run.

Inbound webhooks already exist (`app/inbox/webhooks.py`, Telegram/Mango).
Outbound HTTP from our server is new attack surface (SSRF): any URL a user
can type into an automation's config could target `169.254.169.254`,
`localhost`, or an internal service unless every request is validated.

## Decision

### 1. Two shapes exist; ship the action first

There are two ways to expose outbound HTTP to a workspace:

1. **A generic `http_request` automation action** — a step in a rule the
   user already builds (`stage_change → http_request`). Reuses the
   existing rule engine (trigger matching, condition evaluation, the
   step-chain scheduler, run/step-run audit trail). No new tables.
2. **Event subscriptions** — a registry of `{event, url, secret}` per
   workspace that fires on record lifecycle events directly, independent
   of the rule builder (closer to Twenty's model).

**We ship (1) only in this slice.** It requires zero new schema, reuses
100% of the existing dispatch/scheduler/retry machinery from Sprint 2.7 G2
and plan 015, and already covers the stated use cases — a `stage_change`
trigger with an `http_request` step *is* "stage → Won → push to ERP". (2)
is deferred to a phase 2 plan once the action has shipped and this ADR is
validated in practice; it needs a management UI and a subscription table
that don't exist yet, and is materially larger scope.

### 2. Security model

- **Signing**: every outbound request carries `X-DrinkX-Signature: sha256=<hex>`,
  an HMAC-SHA256 over the **exact raw request body bytes**, computed with a
  single config-level secret (`AUTOMATION_HTTP_SIGNING_SECRET`, read via
  `app/config.py`). The signature lets the receiver verify the payload
  actually came from this CRM and wasn't tampered with in transit.
- **Per-endpoint secrets are phase 2.** A dedicated `{event, url, secret}`
  subscription table (decision 1) is the natural home for a
  per-destination secret; building that table just to hold one field is
  out of proportion for this slice. **Limitation, tracked explicitly**: all
  `http_request` steps in a workspace share one signing secret. Acceptable
  because (a) the receiver only needs the *same* secret it was given
  out-of-band to verify, one secret per deployment is no worse than a
  single shared webhook secret many SaaS tools already ship, and (b) it
  costs nothing to rotate — it's an env var, not a DB row.
- **SSRF**: every outbound URL — the one configured on the step, and every
  redirect hop the response returns — MUST pass `is_safe_fetch_url` from
  `app/common/ssrf.py` (the same guard the enrichment web-fetch source
  already uses). Redirects are followed manually (`follow_redirects=False`
  on the `httpx.AsyncClient`, then re-validate `resp.headers["location"]`
  before following), exactly mirroring
  `app/enrichment/sources/web_fetch.py`'s existing pattern, capped at 3
  hops. A URL that fails the guard — at config time or at any redirect
  hop — is never requested; the step is recorded `failed` with a
  `blocked_ssrf` reason, no exception escapes to the caller.
- **No allowlist/denylist beyond the SSRF guard.** The guard already
  blocks loopback, private (RFC1918), link-local (incl. cloud metadata
  `169.254.169.254`), reserved, and multicast ranges — that's the bar for
  "not an internal service." We do not add a separate domain allowlist in
  this slice; if abuse patterns emerge later (e.g., users on paid tiers
  should be scoped further) that's a phase-2 policy question, not a
  blocker for a spike.
- **Timeouts, no unbounded retries**: a hard `httpx` timeout (10s) on every
  request. `http_request` steps are NOT added to the transient-retry
  allowlist introduced in plan 015 (`_is_transient_step_error` only covers
  `EmailSendError` / `OperationalError`) — an unreachable third-party
  endpoint is the receiver's problem, not ours to hammer with retries. A
  failed POST (network error, timeout, non-2xx) marks the step `failed`
  once; the existing rerun/test-fire admin tooling (plan 015) already
  lets an operator manually re-trigger if the destination comes back.

### 3. Payload shape

Every outbound call sends a signed JSON envelope:

```json
{
  "event": "automation.http_request",
  "occurred_at": "2026-07-01T12:00:00Z",
  "workspace_id": "<uuid>",
  "data": {
    "lead_id": "<uuid>",
    "automation_id": "<uuid>",
    "body": { /* body_template rendered against the lead, or {} */ }
  }
}
```

`event` is a fixed literal (`automation.http_request`) in this slice — it
identifies the *mechanism*, not a specific lifecycle event, because this
action fires as a step in whatever rule the user built (the rule's own
`trigger` — `stage_change` / `form_submission` / `inbox_match` — is *how*
it got invoked, not part of this contract). True per-entity lifecycle
events (`lead.created`, `lead.stage_changed`, `quote.sent`) are phase 2's
job once the subscription registry exists to declare "I want to hear about
this event specifically," independent of any rule the user has to build
by hand.

`body_template` (from the step's `config`) is rendered via the existing
`render_template_text` — same `{{lead.field}}` substitution `send_template`
already uses — then merged into `data.body`.

### 4. Delivery — async, never inline

`http_request` dispatches through the exact same path every other action
type does: `_dispatch_step`, called either synchronously for step 0 inside
`evaluate_trigger`'s per-automation `SAVEPOINT`, or by the
`automation_step_scheduler` beat task for steps 1+. It is never called
inline on the triggering HTTP request thread (there is no such thread
inline call in this codebase's action dispatch — this reuse guarantees a
slow/timing-out third-party endpoint can't block a lead's stage-change API
call). This slice does **not** add a new Celery task; the existing
post-commit-safe scheduler already satisfies "never block the request,"
so introducing a second async mechanism would be needless duplication.

Plan 015's bounded-retry semantics are *not* reused for `http_request`
failures (see §2) — a network-level failure to an external, third-party
system is a different risk profile than an internal SMTP hiccup, and
auto-retrying a POST to an arbitrary URL multiple times is closer to
abuse than resilience without idempotency keys (out of scope here).

## Consequences

- A workspace can now say "on stage change → POST to X" using only the
  existing rule builder — no new UI, no new table, no new migration.
- The blast radius of a misconfigured or malicious `http_request` step is
  bounded by: the SSRF guard (no internal targets), a hard timeout (no
  hung workers), and no auto-retry (no amplification).
- The shared signing secret is a known, explicitly accepted limitation —
  phase 2 (event-subscription registry) is the place to add per-endpoint
  secrets, `*.updated`/`*.deleted` events, and a settings UI to manage
  destinations. Until then, `http_request` is authoring-time only (an
  admin/head builds the rule in the automation builder), not something an
  end-customer can point at arbitrary infrastructure without operator
  sign-off.
- Frontend exposure (the automations builder UI offering `http_request` as
  a step type) is explicitly deferred — this slice is backend-only; the
  action can be exercised today via the REST API (`POST /api/automations`
  with a `steps_json` entry of `{"type": "http_request", "config": {...}}`)
  and the existing test-fire endpoint.
