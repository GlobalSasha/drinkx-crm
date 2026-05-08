# Next Sprint: Phase 2 Sprint 2.2 — WebForms

Status: **READY TO START** (after Sprint 2.1 merge / deploy / smoke check)
Branch: `sprint/2.2-webforms` (create from main once 2.1 lands)

## Goal

Phase 1 + Sprint 2.0 + 2.1 made DrinkX CRM a working pipeline + a system
of record for the conversation + a wide pipe in/out of the data model.
The next ergonomic gap is **inbound lead capture**: the team's landing
pages still drop submissions into Tilda/Senler/typeform-style mailboxes
and a manager has to copy-paste them into the CRM by hand.

Sprint 2.2 closes that gap with a focused WebForms surface — a form
builder in the admin UI, a public submit endpoint with rate-limiting,
and a one-line embed snippet that drops on any landing page. No new
domains, no new vendors, no new AI capability. Smallest sprint in
Phase 2 (~3 days).

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 2.1 left
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope
- `docs/brain/sprint_reports/SPRINT_2_1_BULK_IMPORT_EXPORT.md` — known
  issues / risks; production checklist carryover (FERNET_KEY,
  package-lock cleanup, Sentry activation)
- `docs/PRD-v2.0.md` §8 (Forms) — original spec
- `docs/brain/03_DECISIONS.md` — ADR-007 (no auto-actions; form
  submissions still land as leads, no auto-assignment / auto-actions)
- Production state at sprint start: 4 app containers + 4 cron entries
  running, manager workflows for Pipeline / Inbox / Import / Export
  all live, Sprint 2.1 merged

## Scope

### ALLOWED

#### 1. Schema + ORM

Migration `0012_web_forms`:

- `web_forms` — id (UUID PK), workspace_id (FK CASCADE), name (str 120),
  slug (str 60, UNIQUE per workspace), fields_json (JSON; list of
  `{key, label, type, required, options[]}`), target_pipeline_id (FK
  SET NULL), target_stage_id (FK SET NULL), redirect_url (str 500),
  is_active (bool), submissions_count (int), created_by (FK SET
  NULL → users), created_at, updated_at.
- `form_submissions` — id, web_form_id (FK CASCADE), lead_id (FK SET
  NULL — keep submission row even if lead deleted), raw_payload (JSON),
  utm_json (JSON), source_domain (str 200), ip_address (str 45 — fits
  IPv6), user_agent (text), created_at.
- Indexes: `(workspace_id, slug)` UNIQUE on web_forms;
  `(web_form_id, created_at DESC)` on form_submissions;
  `(workspace_id, created_at DESC)` on form_submissions.

ORM models in `app/forms/` package — same package-per-domain pattern as
the rest (ADR-009). Schemas + services + routers as per shape.

#### 2. Public submit endpoint

- `POST /api/forms/{slug}/submit` — **NO AUTH**. Open to any origin
  (CORS `*` for this single endpoint, scoped via FastAPI's
  `add_middleware` per-router or per-route override).
- Rate-limit: 10 submissions per IP per minute via Redis counter
  (`forms:rl:{ip_hash}` with `incr` + `expire 60`). Hash IP to avoid
  storing raw addresses in keys. 429 on overflow.
- Body: arbitrary JSON. Server resolves the form by slug, validates
  the payload against `fields_json` (required-field check; type
  coercion is best-effort — strings stay strings, dropdown values
  must be in `options`).
- On success: create a `Lead` in `assignment_status='pool'`, place
  in `target_pipeline_id` + `target_stage_id` if set (else default
  pipeline first stage), source = `form:{slug}`. Create a
  `form_submission` row carrying the raw payload. Increment
  `web_forms.submissions_count`. Return `{"ok": true, "redirect": url}`.
- On rate-limit: 429 with `Retry-After`. On unknown slug: 404. On
  validation error: 422 with field-by-field error list.
- **Activity Feed**: emit `Activity(type='form_submission', payload_json={form_name, source_domain, utm_*})`
  on the new lead so the manager sees attribution at a glance.

#### 3. Embed code generator

- `GET /api/forms/{slug}/embed.js` — returns a JS payload that, when
  loaded on a customer's landing page, renders the form HTML and wires
  the submit handler. Content-Type `application/javascript`.
- The generated JS reads `window.location.search` for UTM params and
  `document.referrer` for source domain, attaches them to the POST
  body. Manager doesn't have to do anything to get UTM tracking.
- Form HTML rendered inline (no external CSS) — minimal styling, layout
  inherits from the host page. `<style>` scoped via a unique class
  prefix to avoid leaking into the host's CSS.
- Submit redirects to `redirect_url` on success, surfaces inline error
  on failure. No iframes (CSP-friendly, easier to debug).
- Cache: `Cache-Control: public, max-age=300` so the script doesn't
  re-fetch on every page view. Bust with `?v=N` if the form definition
  changes.

#### 4. Admin UI — `/forms`

- New top-level route `/forms` — visible to admin + head roles only.
  Manager role gets a "request access" placeholder.
- List view: table of forms (name, slug, target stage, submissions
  count, is_active toggle, edit / archive / copy-embed actions).
- Form builder modal: name + slug (auto-derived from name with a
  manual override) + fields (drag-drop reorder, type from
  text/email/phone/textarea/select), target pipeline + stage,
  redirect URL, is_active toggle.
- Embed code panel: textarea with the `<script>` snippet + «Скопировать»
  button (matches the AI bulk-update prompt UX from Sprint 2.1 G8).
- Sidebar nav item «Формы» (admin/head only — same role-gating pattern
  as «Журнал»).

#### 5. Lead-card source attribution

- Lead Card → existing Activity Feed gets a new branch for
  `type='form_submission'` (mirrors the email branch from Sprint 2.0
  G5): icon + form name + source domain + UTM chips, no body.
- `lead.source` displays as `form:{slug}` in the Lead Card chip strip
  alongside priority / deal type / score chips.

### FORBIDDEN

- Drag-drop visual form designer with live preview — Sprint 2.3+
- Captcha / bot-detection — Sprint 2.3+ (rely on rate-limit for v1)
- File-upload fields — Sprint 2.3+ (need S3-compatible storage first)
- Outbound webhooks (form submission triggers a webhook to a third-party)
  — Sprint 2.3+
- Payment fields — never (PCI scope)
- Multi-step / wizard forms — Sprint 2.3+
- A/B test variants per form — Phase 3
- Anything that requires a new payment / subscription account
- New npm dependencies — keep the streak (0 new since Sprint 2.0)

## Tests required

- pytest mock-only suites for the new domain (`app/forms/`):
  - submission validation against `fields_json` (required, type, enum)
  - source attribution (UTM extraction from query string, Referer →
    source_domain)
  - rate-limit counter behavior (mock Redis, verify counter increments
    + 429 after threshold)
  - embed.js generation (asserts the script body includes the right
    field names + slug)
- pytest integration: at least one DB-backed test for the new tables
  (web_forms + form_submissions migration smoke)
- Web Playwright skip-if-env: form public submit → lead lands in pool
- Manual: load embed.js on a real landing page (any production-looking
  HTML) → fill the form → confirm a Lead row appears with the right
  source + UTM JSON

## Deliverables

- Migration 0012 applied on production (auto-via Dockerfile entrypoint)
- `/api/forms/...` endpoints live (submit, embed.js, admin CRUD)
- `/forms` admin route in production
- One real form created on a real DrinkX landing page, embed snippet
  copied, one submission lands in pool with attribution
- `docs/brain/sprint_reports/SPRINT_2_2_WEBFORMS.md` written
- `docs/brain/00_CURRENT_STATE.md` updated
- `docs/brain/02_ROADMAP.md` — Sprint 2.2 → DONE, Sprint 2.3 → NEXT
- `docs/brain/04_NEXT_SPRINT.md` rewritten for Sprint 2.3

## Stop conditions

- All tests pass → report written → committed → push only with
  explicit product-owner approval
- No scope creep into Sprint 2.3 / Phase 3 items (especially: no
  drag-drop form designer, no captcha, no file-upload, no webhooks)
- No new npm dependencies
- No new payment vendor

---

## Recommended task breakdown (~one PR per group)

This list is provisional — refine at sprint start with product owner.

1. **Schema + ORM + admin CRUD scaffold** — migration 0012, `app/forms/`
   models + schemas + services + admin routers (list / create / update
   / archive). Mock-only tests for service-layer validation.
2. **Public submit endpoint + rate-limit + lead creation** — `POST
   /api/forms/{slug}/submit` with CORS open, Redis counter, Lead
   creation in pool, Activity emit, form_submission row.
3. **embed.js generator** — `GET /api/forms/{slug}/embed.js`,
   inline HTML + JS, UTM + Referer extraction, scoped CSS class
   prefix, cache headers.
4. **Admin UI** — `/forms` page (list + builder modal + embed panel),
   sidebar nav for admin/head, source attribution on Lead Card.
5. **Activity Feed integration + cumulative tests + sprint close** —
   `form_submission` activity branch in Lead Card, end-to-end tests,
   sprint report, brain doc updates.

After all merged: schedule a Phase 2 Sprint 2.2 retro before opening 2.3.

---

## Followups parked from earlier sprints

- **Sprint 2.1 carryovers**:
  - `apps/web/package-lock.json` removal (Sprint 2.2 G1 housekeeping)
  - AmoCRM adapter (`app/import_export/adapters/amocrm.py` slots into
    the same plumbing G4 used for Bitrix24)
  - `pnpm add @sentry/nextjs` + DSN activation if production needs
    real telemetry
  - E2E UX smoke for /import / /export / AI bulk-update flows on
    staging — Sprint 2.1 was structurally verified only
- **Sprint 2.0 carryovers**:
  - `_GENERIC_DOMAINS` per-workspace setting (matcher.py)
  - Gmail history-sync 2000-message cap → resumable / paginated job
  - `GOOGLE_CLIENT_ID/SECRET` activation if any new manager wants to
    connect Gmail (graceful 503 until then)
- **Phase G (Sprint 1.3 follow-on)** — move enrichment off FastAPI
  BackgroundTasks onto Celery; WebSocket `/ws/{user_id}` for real-time
  enrichment progress; replace the 2s polling
- **DST-aware daily plan / digest cron** — handle hour-skip and
  hour-duplicate edge cases
- **TransferModal user picker** — replace UUID input with a
  workspace-users picker once `GET /api/users` lands
- **Tab content overflow audit at 375px** — DealTab / ScoringTab /
  AIBriefTab / ContactsTab / ActivityTab / PilotTab not exhaustively
  reviewed for mobile in Sprint 1.5 G6
- **Cron retry on per-user LLM failure** (Sprint 1.4 carryover)
- **Anthropic 403-from-RU mitigation** — possibly add a
  reachable-fallback skip rule so the chain doesn't waste a round-trip
  on every call
- **pg_dump cron** + onboarding doc + log-volume review (Sprint 1.5
  soft-launch tail)
