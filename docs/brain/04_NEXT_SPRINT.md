# Next Sprint: Phase 2 Sprint 2.6 — Real outbound dispatch + UX polish

Status: **READY TO START** (after Sprint 2.5 merge / deploy / smoke)
Branch: `sprint/2.6-outbound-dispatch` (create from main once 2.5 lands)

## Goal

Sprint 2.5 shipped the Automation Builder end-to-end with one
critical caveat: `action_type=send_template` stages an Activity row
with `outbound_pending=true` instead of actually delivering the
message. That's the main driver for 2.6 — wire the channel-aware
sender so an admin who configures «when stage moves to Pilot, send
welcome.txt via email» actually sees an email arrive.

Plus a UX polish bundle that's been carrying since 2.3 / 2.4 (Pipeline
header, LeadCard modal-on-Lost, mobile fallback, Custom-field
rendering on the LeadCard right-rail) — the kind of work that's been
parked because the data layer was the priority through 2.5.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — Sprint 2.5 close summary
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope + carryover list
- `docs/SPRINT_2_5_AUTOMATION_BUILDER.md` — full 2.5 close + carryover list
- `docs/PRD-v2.0.md` §10 (Automation Builder)
- Existing surfaces to extend, not replace:
  - `app/automation_builder/services.py:_send_template_action` — the place to flip from stub to real dispatch
  - `app/notifications/email_sender.py` — Sprint 1.5 SMTP wrapper, stub-mode-aware
  - `app/template/models.py` — `MessageTemplate.channel` discriminates email / tg / sms
  - `app/scheduled/celery_app.py` — beat scheduler; multi-step chains will need a new entry
  - `apps/web/components/lead-card/LeadCard.tsx` — `window.confirm` on Lost lives here
  - `apps/web/components/pipeline/` — header polish + mobile fallback
- Production state at sprint start: 4 app containers + 4 cron entries running, all 2.0–2.5 surfaces live, Sprint 2.5 merged.

## Scope

### ALLOWED

#### G1 — Real outbound dispatch for `send_template` (~1 day)

Backend:
- `app/automation_builder/services.py:_send_template_action` —
  current behaviour: stages an Activity with `outbound_pending=true`.
  G1 changes:
    1. Render template via existing `render_template_text` (already
       in place).
    2. Route by `template.channel`:
        * `email` — call `email_sender.send(...)` using the lead's
          primary email address from `lead.email`. Stub-mode
          (`SMTP_HOST=""`) keeps the existing behaviour: log the
          payload, set `outbound_pending=false`, mark
          `delivery_status='stub'`.
        * `tg` / `sms` — log via structlog,
          `delivery_status='stub_no_provider'`, no actual send.
          Real providers land in 2.7+.
    3. Stage the Activity row with the resolved status (success
       / stub / failed) so the lead's feed shows what happened.
    4. Append a delivery row to `automation_runs.error` if dispatch
       fails — the run row already exists; just enrich it.
- New `app/automation_builder/dispatch.py` — small dispatcher that
  routes a (channel, recipient, body) triple. Keeps the action
  handler thin.
- Defensive: wrap dispatch in try/except. Failures → run row's
  `status='failed'` + `error=str(exc)[:500]`. The action handler
  doesn't propagate the exception so other automations in the same
  fan-out still fire.

Frontend:
- LeadCard Activity Feed: add a tiny chip next to outbound-comment
  rows showing the delivery status («отправлено» / «черновик» /
  «ошибка»). Renders from `payload_json.delivery_status`.
- /automations RunsDrawer: surface the failure error in the row
  (truncate to 80 chars, full text on hover via `title`).

Tests (~6 mock-only):
- email channel + SMTP stub-mode → status='stub'
- email channel + real SMTP_HOST → calls email_sender.send + status='success'
- tg channel → always status='stub_no_provider'
- sms channel → always status='stub_no_provider'
- dispatch failure → automation_run row's status='failed' with error
- unknown lead.email (None) for email channel → status='skipped' with «no recipient» reason

#### G2 — Multi-step automation chains (~1.5 days)

Backend:
- Migration `0021_automation_steps`:
  - Drop the single `action_type` / `action_config_json` columns from
    `automations` (or keep them as «step 0» legacy with a new
    `steps_json` array). TBD at G2 plan-review — pick the cheaper path.
  - Add `automation_step_runs` (automation_run_id CASCADE,
    step_index, scheduled_at, executed_at, status, error). One
    row per step per fire.
- `evaluate_trigger` plumbing — when an automation has multiple
  steps, fire step 0 immediately and schedule subsequent steps via
  Celery countdown task.
- New beat entry `automation_step_scheduler` — every 5 min, picks up
  due `automation_step_runs` rows where `executed_at IS NULL` and
  `scheduled_at <= now()`, runs the step, flips the row.
- Step types: `delay_hours` (no action, just gates the next step's
  schedule) + the existing 3 action types as steps.

Frontend:
- /automations builder modal — switch from single-action picker to
  a step list with «Добавить шаг» CTA. Reorder via dnd-kit (the
  same lib custom-fields will use in G4 — pull lib in once for both).
- RunsDrawer renders a per-step status grid below the parent run.

Tests (~8 mock-only):
- 2-step chain happy path (action → delay → action)
- delay step schedules at correct timestamp
- failure in step 0 stops chain; step 1 stays unscheduled
- failure in step 1 doesn't roll back step 0's effect
- beat scheduler picks up due rows + skips not-yet-due
- multi-clause condition still works at the chain entry
- step ordering preserved
- migration 0021 upgrade + downgrade clean

Risk: this gate alone is the largest in 2.6. If G2 scope creeps,
defer multi-step to 2.7 and use the freed time for additional polish
in G3+G4. Document the decision in the G2 plan-review note.

#### G3 — Pipeline + LeadCard polish (~1 day)

Carryovers bundled into one frontend gate. No new backend.

- `apps/web/components/pipeline/` header: accent button → `+Лид`
  primary, Sprint button → outline secondary. Visual de-emphasis on
  Sprint since it's a manager flow not a daily one.
- Default pipeline seed (`app/pipelines/models.DEFAULT_STAGES`) —
  confirm the 12-stage list maps to the current ICP (drop / merge
  redundant stages, target ~6-7). Light migration `0022_seed_stages`
  if the live workspaces need a re-seed; otherwise just a code change.
- `apps/web/app/(app)/settings/page.tsx` — fold the 3 «Скоро»
  sections (Профиль / Уведомления / API) under a `<details>`
  disclosure. Reduces visual noise without removing the placeholders.
- `apps/web/components/lead-card/LeadCard.tsx` — `window.confirm`
  on Lost → styled modal matching the rest of the LeadCard (Plus
  Jakarta Sans, soft shadow, double-bezel — see
  `apps/web/components/settings/PipelineEditor.tsx` for a copyable
  reference).
- Mobile pipeline fallback (<md): `apps/web/app/(app)/pipeline/page.tsx`
  exposes a list-view as fallback today; G3 polishes the actual
  vertical card layout (compact cards, swipe-to-stage, no
  drag-and-drop on touch — long-press for context menu).

Tests (~3 mock-only — frontend mostly, light backend):
- pipelines.repositories.list returns ≤7 default stages after
  re-seed (confirms the migration if shipped)
- LeadCard Lost-modal acceptance (component test if framework-ready)
- mobile breakpoint snapshot stays stable (snapshot test)

#### G4 — Custom-field render on LeadCard + dnd-kit reorder (~0.5 day)

Carryover from Sprint 2.4 G3 — custom_attribute_definitions exist
since migration 0018, lead_custom_values too, but no UI consumes them.

Backend:
- New endpoint `GET /api/leads/{id}/custom-values` — list values
  for a lead joined with the matching definition. Already implicit
  via `LeadCustomValue.definition` relationship; just expose.
- `PUT /api/leads/{id}/custom-values/{def_id}` — upsert one value
  per (lead, definition). Already exists at the service layer
  (`app.custom_attributes.services.upsert_value`); just expose at
  the router.

Frontend:
- New right-rail section in LeadCard «Дополнительные поля» — list
  every workspace definition + render the matching value (or empty
  state to fill in). Inline edit per kind (text input / number / date /
  select).
- Settings → Кастомные поля: replace the v1 up/down position
  buttons with dnd-kit reorder. Pull `@dnd-kit/sortable` once (G2
  also wants it for step ordering — share the install).

Tests (~3 mock-only):
- list_values_for_lead joins definitions correctly
- upsert via PUT endpoint roundtrips
- reorder PATCHes positions in batch (or per-row)

#### G5 — Polish + sprint close (~0.5 day)

- Audit emit hooks for `automation.dispatch.{success,failed}` (so
  ops can filter «show me all the failed sends today» in /audit).
- Sprint report `SPRINT_2_6_OUTBOUND_DISPATCH.md`.
- Brain memory rotation (00 + 02 + 04).
- Smoke checklist additions: `docs/SMOKE_CHECKLIST_2_6.md`.

### NOT ALLOWED (out of scope)

- **Real tg / sms providers.** v1 keeps them in stub_no_provider
  state. Picking a Telegram bot library + an SMS provider is its own
  evaluation gate that lands in 2.7+.
- **Workspace-level webhook trigger / action** — still parked.
- **AI-generated message bodies** in templates — still parked.
- **AmoCRM adapter** — still in long-tail backlog after 2.5 G3 skip.
- **Multi-tenancy** — Phase 3.
- **Sentry activation** — still parked. (`pnpm add @sentry/nextjs` +
  DSN env vars.)

## Carryovers from Sprint 2.5 (full list)

Folded into the gate plan above where applicable; rest tracked here:

1. ✅ G1: Real outbound dispatch for `send_template`
2. ✅ G2: Multi-step automation chains
3. ✅ G3: Pipeline header tweak / LeadCard modal-on-Lost / Mobile Pipeline fallback / Settings «Скоро» disclosure / Default pipeline 6–7 stages
4. ✅ G4: Custom-field render on LeadCard + dnd-kit reorder for Custom Fields position
5. ⏸ Stage-replacement preview in PipelineEditor — Sprint 2.3 carryover; couldn't fit in G3 polish bundle
6. ⏸ Multi-clause condition UI in the Automation Builder modal (backend supports n-clause; frontend currently ships single row)
7. ⏸ Workspace AI override → fallback chain wiring (Sprint 2.4 G3 carryover; UI persists, env still wins)
8. ⏸ AmoCRM adapter (carried since 2.1; skipped 2.5 G3)
9. ⏸ `pnpm add @sentry/nextjs` activation (Sprint 2.1 G10 carryover)

## Risks

1. **G2 scope creep.** Multi-step chains touch migration shape +
   Celery beat + frontend builder UI. If the migration design isn't
   straightforward (drop+re-add columns vs JSON-array migration), G2
   could blow past 1.5 days. Plan-review at G2 kickoff: pick path
   based on whether the production `automations` table has any rows
   at that point.
2. **SMTP stub still active in production.** G1's email path falls
   into stub mode if `SMTP_HOST=""`. Verify the prod env BEFORE the
   sprint to know if real delivery is testable end-to-end. If still
   stub-mode, the smoke checklist confirms «stub status surfaces in
   the Activity Feed» instead of «email arrived».
3. **`@dnd-kit/sortable` is a new dep** — first npm install in this
   sprint cycle since Sprint 2.0. The «0 new deps» streak breaks
   here; document explicitly in the sprint report.
4. **Default pipeline re-seed (G3).** If the production workspace
   has historical data on stages that get merged / dropped, the
   migration needs a backfill path. Plan-review G3 with the actual
   production stage IDs in hand.
5. **Carryover bundling in G3.** Five small items in one gate is
   tight. If any single one needs more than 2 hours, peel it off
   into G3.5 or push to 2.7.

## Stop conditions — post-deploy smoke checklist

Update `docs/SMOKE_CHECKLIST_2_6.md` with:
- [ ] /automations — configure a `send_template` automation, trigger it, the lead's Activity Feed shows «отправлено» chip (or «черновик» in stub mode)
- [ ] Real email arrives at the inbox (skip if SMTP still stub)
- [ ] Multi-step chain: 2-step automation → first step fires immediately, second step shows «scheduled» status until the delay elapses
- [ ] LeadCard right-rail «Дополнительные поля» shows all workspace definitions
- [ ] Mobile Pipeline (<375px viewport): vertical card layout renders
- [ ] LeadCard «Закрыть как Lost» opens styled modal (no `window.confirm`)
- [ ] All 9 prior smoke checks (from 2.4) + 7 from 2.5 still pass

## Done definition

- Migration 0021 (automation_steps) applies cleanly via `alembic
  upgrade head` on staging.
- `send_template` produces real outbound messages on email when SMTP
  is configured; stub mode surfaces in the Activity Feed clearly.
- Multi-step chains end-to-end: trigger → step 0 → wait → step 1 →
  run row history shows per-step status.
- Custom-field values render on LeadCard right-rail.
- Pipeline + LeadCard polish bundle merged.
- ≥20 new mock tests across G1–G4. Combined baseline ≥321 mock
  tests passing (301 + 20).
- `pnpm typecheck` + `pnpm build` clean.
- Sprint report written, brain memory rotated.
- Net-new npm deps: 1 (`@dnd-kit/sortable`) — explicitly documented.

---

**Out-of-scope but parked here for awareness — fold into 2.7+:**

- Real tg / sms provider integration (Sprint 2.6 NOT-ALLOWED)
- Multi-tenancy (Phase 3)
- Workspace-level webhook trigger / action (Sprint 2.5 NOT-ALLOWED)
- AI-generated message bodies in templates (Sprint 2.5 NOT-ALLOWED)
- AmoCRM adapter (long-tail since 2.1)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder (Sprint 2.0 deferred)
- Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- `pnpm add @sentry/nextjs` activation (Sprint 2.1 G10 carryover)
- Per-stage gate-criteria editor (Phase 3)
- Pipeline cloning / templates marketplace (Sprint 2.3 carryover)
- Cross-pipeline reporting (Phase 3)
- DST-aware cron edge handling
- Stage-replacement preview in PipelineEditor (Sprint 2.3 carryover)
- Workspace AI override → fallback chain (Sprint 2.4 G3 carryover)
- Multi-clause condition UI in the Automation Builder modal
