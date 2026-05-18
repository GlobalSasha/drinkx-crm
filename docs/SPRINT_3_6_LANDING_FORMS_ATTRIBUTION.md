# Sprint 3.6 — Landing Forms Attribution

**Status:** 📋 SPEC (pre-implementation)
**Date:** 2026-05-18
**Branch:** `sprint/3.6-landing-forms-attribution` (to create)
**Tracking:** `docs/brain/04_NEXT_SPRINT.md` (will replace after 3.5 merges)

---

## Goal

Surface the multi-landing attribution that Sprint 2.2 captured into the
data model but never exposed in the UI. Managers must be able to see —
at a glance, without opening the Activity feed — which landing brought
each lead and from which ad channel, and to filter the pool by form so
campaign comparisons are possible.

## Why now

The Q3 2026 marketing campaign launches with 3+ landing pages × multiple
ad channels (VK, Яндекс, Reels, LinkedIn, outreach) per the campaign plan.
Without source visibility:

- managers cannot tell a paid-traffic lead from an organic one and treat
  them identically (paid leads usually need faster response);
- marketing cannot evaluate which landing or channel converts (no way to
  slice leads by source on the existing screens);
- a lead from «calculator landing» vs «horeca landing» needs different
  follow-up content but they look identical in the pool.

## What already exists (do NOT rebuild)

Sprint 2.2 shipped the public-form pipeline end-to-end. Verify in
`apps/api/app/forms/`:

- `WebForm` model with `slug`, `name`, `fields_json`, `target_pipeline_id`,
  `target_stage_id`, `is_active`, `submissions_count`.
- `FormSubmission` model with `raw_payload`, `utm_json`, `source_domain`, `ip`.
- `POST /api/public/forms/{slug}/submit` — public unauthed, CORS-wildcarded
  for `/api/public/*`, rate-limited per (slug, IP) in Redis.
- `GET /api/public/forms/{slug}/embed.js` — self-contained JS, no deps.
- `lead_factory.create_lead_from_submission` — projects payload to
  canonical Lead fields (RU + EN keys), writes `lead.source = "form:{slug}"`,
  emits a `form_submission` Activity with `{form_name, source_domain, utm}`
  in `payload_json`, fires the Sprint 2.5 `form_submission` automation
  trigger. Lead lands in `assignment_status="pool"` (ADR-007: no auto-claim,
  no stage advance, no AI auto-actions).
- `/forms` admin page (admin/head only) — list / create / edit / delete /
  toggle-active + embed snippet copy.

The data is there. The UI bindings are not.

## Out of scope (explicit)

- **Tilda / Webflow OAuth integrations.** All landings will be self-coded
  in Claude / v0 — no constructor support needed. The existing public
  endpoint accepts arbitrary JSON keys and works for any custom payload
  shape, which covers the "what if a future landing isn't ours" case.
- **Dashboard with charts.** Per-form stats in this sprint = numeric card
  per form. A `/forms/campaigns` dashboard with charts is a separate
  follow-up sprint after real campaign data accumulates (4–6 weeks
  post-launch).
- **A/B variants per form.** One form = one stats row. Variant tracking
  is a future feature.
- **UTM source normalization** (e.g. `vk` / `vkontakte` / `vk-ad` →
  single canonical bucket). Show raw values in this sprint; normalize
  when the dataset justifies it.
- **Lead deduplication across forms.** If the same email submits two
  different landings, two leads are created (current behaviour). Dedup
  is its own design problem with policy implications (do we merge?
  reassign? credit which campaign?) — out of scope here.

## Gates

### G1 — Lead source surfacing on Lead Card

**Backend** — `apps/api/app/leads/`

- Extend `LeadOut` schema with two read-only enrichments:
  - `source_form_name: str | None` — resolved by joining `web_forms` when
    `lead.source LIKE 'form:%'` (substring match the slug after the
    prefix). NULL otherwise.
  - `latest_utm: dict[str, str] | None` — the most recent
    `form_submission` Activity for this lead, reading
    `payload_json["utm"]`. NULL when no form_submission Activity exists.
- These are computed in the lead read path. Two options:
  1. SQL JOIN + lateral subquery for `latest_utm` (single round-trip;
     more complex query).
  2. Two follow-up SELECTs after the main lead fetch (simpler; one extra
     query per detail-view load).
  - **Pick (2)** — lead detail load is not a hot path, and the code stays
    readable. Re-evaluate if `/pipeline` ever needs UTM in the list view.
- No changes to writes; this is read-side enrichment only.

**Frontend** — `apps/web/components/lead-card/`

- `LeadCard.tsx` — add a compact chip in the header strip, next to the
  company name: `🌐 Лендинг: <source_form_name>`. Render only when
  `source_form_name` is present. Falls back to a generic
  `📥 Заявка с формы` (no name) when `lead.source` starts with `form:`
  but the form was deleted (FK is SET NULL on delete).
- `DealAndAITab.tsx` — add a new section «Источник» below
  «Параметры сделки», visible only for form-sourced leads:
  - Form name (link to `/forms?focus=<id>` for admin/head, plain text
    for managers).
  - `source_domain` (the URL the form was embedded on at submit time).
  - UTM table — one row per non-empty UTM key in `latest_utm`. Each
    row is a `key | value` pair using existing `Row` component pattern.
  - Collapsible "Raw payload" disclosure for debugging — `<details>`
    element showing pretty-printed `raw_payload` from the latest
    `form_submission` Activity. Hidden by default.

**Tests**
- Backend: extend leads service tests — assert `LeadOut.source_form_name`
  resolves for a form-sourced lead, returns NULL for a manual lead, and
  doesn't crash when the source form has been deleted.
- Frontend: visual review only (no Lead Card snapshots in this codebase
  per recent sprints).

### G2 — Filter by form on /leads-pool and /pipeline

**Backend** — `apps/api/app/leads/repositories.py`

- Add optional `form_id: UUID | None` filter to the existing leads-list
  query path. Translates to `WHERE leads.source = 'form:' || forms.slug`
  on join, OR — simpler — pre-resolve `form_id → slug` in the service
  layer and filter by `lead.source = 'form:<slug>'` directly. The
  source column is indexed-friendly via the existing leads filtering.
- Expose on `GET /leads?form_id=<uuid>` and `GET /leads/pool?form_id=<uuid>`.

**Frontend** — `apps/web/components/leads-pool/` + `apps/web/app/(app)/leads-pool/page.tsx`

- Add a «Источник» dropdown to the leads-pool filter bar. Options:
  - «Все источники» (default, no filter)
  - One entry per active form in the workspace («HoReCa МСК», «АЗС
    landing», ...) — fetched via existing `useForms` hook
  - «Без формы» (filter to `lead.source IS NULL or NOT LIKE 'form:%'`)
    — for the manual / CSV-imported pile.
- Same dropdown is **optional** for `/pipeline`. If trivial, add it; if
  it requires PipelineHeader restructuring, defer to a follow-up. The
  most important surface is `/leads-pool` where fresh form leads land.

### G3 — Per-form stats on /forms admin page

**Backend** — `apps/api/app/forms/services.py` + `routers.py`

- New endpoint `GET /api/forms/{form_id}/stats` returning:
  ```json
  {
    "submissions_7d": 24,
    "submissions_30d": 87,
    "claimed_count": 12,
    "by_stage": {"Новый контакт": 30, "Квалификация": 8, "Discovery": 4}
  }
  ```
- Implementation:
  - `submissions_*d` — `COUNT(*) FROM form_submissions WHERE web_form_id=$1 AND created_at >= NOW() - INTERVAL`
  - `claimed_count` — `COUNT(DISTINCT lead_id) FROM form_submissions WHERE web_form_id=$1 AND lead_id IS NOT NULL AND EXISTS(... assignment_status='assigned')`. Reuses the lead join.
  - `by_stage` — `GROUP BY stage.name` of leads attributed to this form
- Cache for 60s per form (the leads-pool already polls; freshness > 1m
  is fine here).

**Frontend** — `apps/web/app/(app)/forms/page.tsx` + a new
`FormStatsCard.tsx`

- Render the stats card under each form row in the existing list. Layout:
  «48 заявок за 7д · 87 за 30д · 12 в работе · Conversion to Quality: 18%»
- Conversion to Quality = `(by_stage values past stage 1) / total submissions`.
- Loading skeleton when `stats` is undefined; muted "—" state when no
  submissions yet.

### G4 — Self-coded landing documentation

**New file** — `docs/landings.md`

Audience: a marketer or designer using Claude/v0 to spin up a landing
page. Must be readable in 5 minutes; must include working snippets.

Sections:

1. **Что вы получите**: одна форма → одна заявка в CRM, видно «откуда
   пришла» — на карточке лида и в фильтре пула.
2. **Создать форму в CRM**: admin → /forms → «Новая форма» → имя +
   slug + поля (минимум `phone`, `email`) → copy slug.
3. **Pattern A1: статический HTML с embed.js** — full snippet:
   ```html
   <div id="drinkx-form"></div>
   <script src="https://crm.drinkx.tech/api/public/forms/horeca-msk/embed.js"></script>
   ```
   Pros / cons: instant, styled by us. Use when the landing is static
   HTML and the manager just wants a working form.
4. **Pattern A2: React / Next.js (v0 / Claude-generated)** — full
   working example component:
   ```tsx
   const SLUG = "horeca-msk";
   const API = "https://crm.drinkx.tech/api/public/forms";
   export default function LeadForm() {
     // form state, submit handler that POSTs JSON to
     // `${API}/${SLUG}/submit` with {phone, email, ...}
     // + UTM passthrough block (read from URL once on mount)
   }
   ```
   Pros / cons: full Tailwind control, native React state, no iframe.
   Use when the landing is a real React app.
5. **UTM passthrough**: how to capture `utm_source`, `utm_medium`,
   `utm_campaign`, `utm_content`, `utm_term` from the landing URL and
   include them in the submission body under a `utm` key. The CRM
   reads `payload.utm` and stamps `FormSubmission.utm_json` from it.
6. **Тестовый прогон**: how to verify the submission landed — open
   `/leads-pool` filtered by your form name, see the new lead within
   ~5s, open the lead → verify the «🌐 Лендинг: ...» chip + UTM table.
7. **CORS / rate limits**: `/api/public/*` is wildcard-CORS by design.
   Rate limit is per (slug, IP) — burst protected against bot abuse.
   No origin allowlist required.

## Pre-PR gates per checkbox

Per `CLAUDE.md`:
- Frontend: `npm run typecheck` + `npm run lint` + `pnpm build` (Next.js
  15 typed-routes mandate).
- Backend: `python -m py_compile` on touched modules, `pytest --collect-only`,
  then targeted tests for `LeadOut` enrichments and the stats endpoint.

Commit messages reference the gate, e.g.
`feat(leads): G1 — source_form_name + latest_utm on LeadOut`.

## Smoke checklist (post-merge, before announcing to the marketing team)

1. Create a test form in `/forms` with slug `smoke-test`, fields `phone`
   + `email`.
2. Copy the embed snippet, paste into `~/Desktop/test-landing.html`,
   open in browser, submit a fake lead.
3. `/leads-pool` filtered by «smoke-test» → the new lead is visible.
4. Open the lead → «🌐 Лендинг: <name>» chip is in the header, the
   «Источник» section shows form name + source_domain + UTM table
   (UTM empty unless added to URL).
5. Open the form's row in `/forms` → stats card shows
   «1 заявка за 7д · 0 в работе».
6. Submit again with UTM in the URL: `?utm_source=test&utm_campaign=smoke`
   → reopen the new lead → UTM table reflects the values.

## Open questions / decisions deferred

- **Should `/pipeline` show the source chip on the pipeline card?**
  The Lead Card Redesign sprint deliberately removed metadata from the
  kanban surface (see G2 of Sprint 3.5 — DROPPED). Same decision likely
  applies: keep the pipeline card pure, surface attribution only inside
  the lead detail view. Confirm during G1 review.
- **Self-coded React snippet's UTM block — utility helper?** If the
  marketing team uses the example more than 2-3 times we should extract
  a hosted JS helper. For now inline JS is fine and educates the team.
