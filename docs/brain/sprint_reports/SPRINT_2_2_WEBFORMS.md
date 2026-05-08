# Sprint 2.2 — WebForms (public lead-capture)

**Status:** ✅ Branch ready for product-owner review · 4/4 groups closed
**Period:** 2026-05-08 (single-day sprint)
**Branch:** `sprint/2.2-webforms` (NOT yet merged to main)
**Commit range:** `32b5d79..HEAD` (G1–G3) + this G4 close

---

## Goal

Phase 2 had two thirds done — Inbox (2.0) gave the team a real conversation
record, Bulk I/O (2.1) gave them a wide pipe in/out of the data model.
The last day-one ergonomic gap was **inbound lead capture from the team's
own landing pages** — Tilda / Senler / typeform-style mailboxes still
required a manager to copy-paste each submission into a CRM card.

Sprint 2.2 closes the gap with a focused WebForms surface:

- a public, unauthenticated `POST /api/public/forms/{slug}/submit`
  endpoint with per-`(slug, ip)` rate-limiting,
- a one-line `<script>` embed that drops on any landing page and
  POSTs back to us,
- an admin-only `/forms` page with field editor, target stage, redirect
  URL and a copy-snippet panel,
- structured Activity-Feed provenance (`form_submission` activity type)
  + a `source` chip on the lead card so the manager sees at a glance
  how every lead arrived.

No new domains, no new vendors, no new AI capability. Smallest sprint
in Phase 2 (~1 day actual).

---

## Groups delivered

| # | Name | Commit | Files | Tests |
|---|---|---|---|---|
| 1 | WebForms schema + admin CRUD (migration 0012, ORM, slug, repo, services, routers) | `32b5d79` | 11 | 6 |
| 2 | Public submit + rate-limit + lead factory + embed.js + scoped CORS | `3f3532a` | 7 | 9 |
| 3 | `/forms` admin page + FormEditor modal + sidebar nav | `eebd455` | 5 | — (build only) |
| 4 | form_submission Activity + ActivityTab render + source chip + report (this) | (this) | 6 | 3 |

**Combined backend test suite (Sprint 2.2 deliverables):** 18 mock-only
tests passed, 0 skipped, 0 DB, 0 Redis, 0 network. Spread across:

- `tests/test_webforms.py` — 9 (slug × 3 + service × 3 + lead-factory × 3)
- `tests/test_public_submit.py` — 9

Combined with Sprint 1.5 / 2.0 / 2.1 baseline (notifications + audit +
inbox + import_export + webforms): **117 mock tests passing**.

**Frontend:** `pnpm typecheck` + `pnpm build` clean throughout. 12
routes prerendered (was 11 — `/forms` added). **Zero new npm
dependencies** (the streak from Sprint 2.0 + 2.1 survives a third
sprint). Zero new Python deps.

---

## Architecture decisions

### `PublicFormsCORSMiddleware` scoped, not a global CORS loosening

A naive fix to "let foreign landing pages POST to us" is to widen the
global CORS allow-list to `*`. That would silently relax the rest of
the API — Pipeline, Inbox, Bulk Update — to any origin, defeating the
restrictive `cors_origins` config that Sprint 1.0 set up.

Instead we wrote `PublicFormsCORSMiddleware` (Starlette
`BaseHTTPMiddleware`) that adds wildcard CORS **only for `/api/public/*`
paths**. The global `CORSMiddleware` stays restrictive for the rest of
the API surface. Add-order matters in Starlette (outermost-first):
the public middleware is added LAST so it runs FIRST and short-circuits
preflight before the restrictive global middleware sees the request.

Bearer Authorization isn't a CORS-credential per spec, so the
`Origin: *` + no-credentials shape is safe — a malicious origin can
POST a submission (which is what we want anyway), but cannot read the
authed admin API.

### Per-`(slug, ip)` rate-limit, not per-IP global

Bot scrubbing one form at high volume should not burn the workspace's
budget across other forms; an honest landing page seeing a spike (Black
Friday, RT mention) should not lock out submissions on the team's other
landing pages. The Redis key encodes `(slug, ip)` so each form gets its
own bucket per remote — `forms:rl:{slug}:{ip}:{minute_bucket}`.

Default 10 req/min/IP/slug is configurable via
`form_rate_limit_per_minute`. Fail-open envelope: any Redis error
returns `True`. Trade-off: losing legitimate leads to a Redis hiccup
is worse than admitting a few extra spam submissions, which a
soft-delete + manager review can recover.

### `embed.js` once-loaded guard, not idempotent rendering

A landing page that includes the embed twice (e.g. once in header
once in footer) would otherwise render two forms, doubling fields and
firing duplicate submissions. The embed sets a
`window.__drinkxFormLoaded_<safe-slug>` flag and bails on subsequent
loads. Per-slug, so a single landing page can host multiple distinct
DrinkX forms without collision.

### Soft-delete returns 410 Gone, not 404 Not Found

When a manager deletes a form in the admin UI, the row stays in the DB
with `is_active=False` so historical submissions remain attributable
and `FormSubmission.web_form_id` doesn't dangle. The public submit
endpoint returns `410 Gone` for an inactive form (semantically: «this
endpoint existed and won't again») and the embed.js endpoint returns
a JS-shaped 410 comment so the host page's `<script>` tag doesn't
crash with an HTML-parse error.

The admin confirm-delete modal explicitly explains this: «embed-код
вернёт 410 Gone, лиды перестанут приходить, история подач сохранится».

### `form_submission` is a separate Activity type, not a plain comment

The lead's Activity Feed needs to surface where the lead came from —
form name, source domain, UTM campaign — independent of whatever
freeform note the customer typed into the form. We could have shoved
all of that into a single `comment` activity, but then:

1. Manager-edited comments would erode the provenance.
2. Filter chips couldn't separate «show me only form-arrival events»
   from «show me only manager comments».
3. The render template for a comment is plain text; the form arrival
   wants structured chips (form name bold, source domain mono, UTM
   labelled).

So we emit two activities when a notes payload arrives — one
`type='comment'` carrying the customer's text, one
`type='form_submission'` carrying `{form_name, form_slug,
source_domain, utm}`. When the payload has no notes, only the
`form_submission` activity lands — we don't fabricate an empty
comment row.

Added `form_submission` to the `ActivityType` enum and to the
ActivityTab filter chips («Заявки»). DB column is `String(30)` so no
migration required.

---

## Known issues / risks

1. **`target_stage_id` cross-workspace validation lives client-side**
   only (the `usePipelines()` query is workspace-scoped, so the picker
   never offers another workspace's stages). Backend trusts the FK to
   reject genuinely bad IDs but doesn't actively check workspace
   ownership of `target_pipeline_id` / `target_stage_id`. **TODO Sprint
   2.3:** add a service-layer check on form create/update that the
   pipeline + stage belong to the same workspace.

2. **Notification spam during bot abuse.** Every successful submission
   fires a fan-out admin notification. A rate-limit miss + a flood of
   non-honeypotted bot submissions would page every admin in the
   workspace. The rate-limit is the first line of defence (per-`(slug,
   ip)`, 10/min default), but a distributed scraper across many IPs
   would still slip through. **TODO:** add a notification debounce
   (max one «Новая заявка с формы X» per admin per 5 min) or a
   rate-limit on notifications themselves.

3. **CORS preflight smoke test deferred to staging.** The scoped
   middleware is unit-tested by inspecting the route mount, but the
   actual `OPTIONS /api/public/forms/{slug}/submit` round-trip from a
   foreign origin needs a staging deploy with real DNS to verify.

4. **Sentry `@sentry/nextjs` package still not installed** (carryover
   from Sprint 2.1 G10). The browser-side init guard is wired (DSN
   check + lazy require), but the package isn't in the lockfile. One
   `pnpm add @sentry/nextjs` away from active.

5. **Public endpoint has no honeypot or CAPTCHA.** Rate-limiting alone
   stops casual bots; a determined scraper can still flood with
   distinct IPs. Manager review via soft-delete + re-claim from pool
   recovers, but this should be revisited if we see real abuse — a
   timing-honeypot field («fill in less than 1.5s = bot») is a 10-line
   diff in `embed.js`.

6. **`apps/web/package-lock.json` housekeeping** — closed in Sprint 2.1
   G10 (committed `5d9052e`). No carryover.

---

## Production readiness checklist

- [ ] **Migration `0012_webforms` applies cleanly.** Auto-applies via
      the api Dockerfile entrypoint
      (`uv run alembic upgrade head && uv run uvicorn`). Verify
      `alembic_version` rows after first deploy show `0012`.

- [ ] **Smoke test (staging then prod):**
      1. Sign in as admin → open `/forms` → «+ Новая форма».
      2. Add fields (`company`, `email`, `phone`), set redirect URL,
         save.
      3. Switch to «Встроить» tab → copy embed snippet.
      4. Paste snippet on a test landing page.
      5. Open landing in an incognito window, fill form, submit.
      6. Verify: redirect happens (or success message shown).
      7. Open `/leads-pool` in admin window → new lead present with
         `source: form:<slug>` chip.
      8. Open lead card → Activity Feed has a «Заявка с формы» row
         with form name + source domain + (optional) UTM source.

- [ ] **CORS preflight verified.** From a foreign-origin landing page,
      browser dev tools should show
      `OPTIONS /api/public/forms/{slug}/submit` → 200 with
      `Access-Control-Allow-Origin: *`. Other API endpoints should
      still 4xx without proper origin.

- [ ] **Rate-limit verified.** 11th request within 60s from the same
      IP to the same slug returns 429. 11th request from a different
      slug (same IP) is allowed (per-`(slug, ip)` semantics).

- [ ] **Soft-delete verified.** Delete a form, then submit to its slug
      → 410 Gone. The admin list still hides it (filter is
      `is_active=true`); historical submissions still resolvable via
      `GET /api/forms/{form_id}/submissions`.

- [ ] **Notification fan-out verified.** A successful submission fires
      a system-kind notification to every admin in the workspace
      (visible in the bell drawer with link to the new lead).

---

## Files changed (cumulative across G1–G4)

```
apps/api/
  alembic/env.py
  alembic/versions/20260508_0012_webforms.py
  app/activity/models.py                  # form_submission added to ActivityType (G4)
  app/auth/dependencies.py                # require_admin_or_head
  app/config.py                           # form_rate_limit_per_minute
  app/forms/__init__.py
  app/forms/embed.py                      # generate_embed_js + once-loaded guard
  app/forms/lead_factory.py               # create_lead_from_submission + form_submission Activity (G4)
  app/forms/models.py                     # WebForm + FormSubmission ORM
  app/forms/public_routers.py             # /api/public/forms/{slug}/{submit,embed.js}
  app/forms/rate_limit.py                 # check_rate_limit (Redis INCR + EXPIRE)
  app/forms/repositories.py
  app/forms/routers.py                    # /api/forms admin REST
  app/forms/schemas.py                    # FieldDefinition + WebFormOut + FormSubmissionOut
  app/forms/services.py                   # create_form (slug retry × 3) + get_or_404 + update + soft_delete
  app/forms/slug.py                       # generate_slug — stdlib-only RU translit + 6-char suffix
  app/main.py                             # PublicFormsCORSMiddleware + forms_public_router mount
  app/scheduled/celery_app.py             # forms domain side-effect import (model registry)
  tests/test_public_submit.py             # 9 tests
  tests/test_webforms.py                  # 9 tests (6 G1 + 3 G4)

apps/web/
  app/(app)/forms/page.tsx                # admin list page
  components/forms/FormEditor.tsx         # modal with «Настройки» + «Встроить» tabs
  components/layout/AppShell.tsx          # «Формы» nav item (admin/head gated)
  components/lead-card/ActivityTab.tsx    # form_submission render + filter chip (G4)
  components/lead-card/LeadCard.tsx       # source chip in header (G4)
  lib/hooks/use-forms.ts
  lib/types.ts                            # FieldDefinition + WebFormOut + FormSubmissionOut

docs/brain/
  00_CURRENT_STATE.md                     # Sprint 2.2 marked DONE (G4)
  02_ROADMAP.md                           # Sprint 2.2 → DONE, 2.3 promoted (G4)
  04_NEXT_SPRINT.md                       # rewritten for Sprint 2.3 — Multi-pipeline switcher (G4)
  sprint_reports/SPRINT_2_2_WEBFORMS.md   # this report
```

23 files touched, ~3500 net lines added.

---

## Next sprint pointer

**Phase 2 Sprint 2.3 — Multi-pipeline switcher.** See
`docs/brain/04_NEXT_SPRINT.md`. Workspaces will gain support for
multiple voronkas (sales / partners / refunds / …); the manager
switches between them in `/pipeline` via a dropdown; `/today` and
`/leads-pool` continue to show leads across all of the user's
pipelines.

Outstanding deferred work to fold into 2.3+ housekeeping:

- AmoCRM adapter (Sprint 2.1 G5 deferred)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder, Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 2000-msg cap)
- `target_stage_id` cross-workspace validation (Sprint 2.2 carryover)
- Notification debounce on form-submission fan-out (Sprint 2.2 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- `pnpm add @sentry/nextjs` activation (Sprint 2.1 carryover)
- pg_dump cron + Sentry DSNs (Sprint 1.5 soft-launch carryover)
