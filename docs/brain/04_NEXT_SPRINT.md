# Next Sprint: Phase 2 Sprint 2.5 — Automation Builder

Status: **READY TO START** (after Sprint 2.4 merge / deploy / smoke)
Branch: `sprint/2.5-automation-builder` (create from main once 2.4 lands)

## Goal

Sprint 2.4 shipped the Templates data model + admin CRUD without a
consumer. Sprint 2.5 wires templates into actual outbound flows by
building the **Automation Builder** — a workspace-scoped configuration
of «when X happens, run Y». Plus closes a stack of carryovers from
2.4 that the customer-facing Automation surface depends on (notification
dedupe, invite accept-flow).

Scope is one big new domain (`automations`) plus four polish gates. No
new vendors. No new AI capability beyond «use existing fallback chain
to render template variables», deferred to G1 plan-review.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — Sprint 2.4 close summary
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope + carryover list
- `docs/SPRINT_2_4_SETTINGS_TEMPLATES.md` — full 2.4 close + 14-item carryover list
- `docs/PRD-v2.0.md` §10 (Automation Builder)
- Existing surfaces to extend, not replace:
  - `app/template/*` — template definitions (Sprint 2.4 G4)
  - `app/automation/stage_change.py` — already has pre/post hook plumbing for stage transitions; the trigger source for «when stage changes»
  - `app/forms/*` — form-submission hook is the trigger source for «when a form is submitted»
  - `app/inbox/*` — inbox-match is the trigger source for «when an email matches a lead»
  - `app/notifications/*` — destination for in-app action types
- Production state at sprint start: 4 app containers + 4 cron entries running, all 2.0–2.4 surfaces live, Sprint 2.4 merged.

## Scope

### ALLOWED

#### G1 — Automation Builder core (~2 days)

Backend:
- Migration `0020_automations`:
  - `automations` (workspace_id CASCADE, name, trigger ∈ ('stage_change', 'form_submission', 'inbox_match'), trigger_config_json, condition_json, action_type ∈ ('send_template', 'create_task', 'move_stage'), action_config_json, is_active, created_by SET NULL, created_at, updated_at)
  - `automation_runs` (automation_id CASCADE, lead_id SET NULL, status ∈ ('queued', 'success', 'skipped', 'failed'), error, executed_at) — append-only audit of every fire
- New `app/automation_builder/` package (do NOT extend existing
  `app/automation/` — that one is the stage-change hook engine, this
  is the user-defined builder; different concern, deserves its own
  module). Models / schemas / repositories / services / routers.
- Service: `evaluate_trigger(trigger_type, payload)` looks up matching automations, evaluates condition_json against the lead, schedules the action via Celery.
- Action handlers: `send_template_action(template_id, lead_id, channel)` — renders template via simple `{{lead.field}}` substitution, hands to existing channel sender (email via `app/notifications/email_sender.py`; tg + sms stub mode in v1).
- Trigger wiring (the hard part):
  - `app/automation/stage_change.py` post-hook fans out to `evaluate_trigger("stage_change", {...})`.
  - `app/forms/services.py` after-create-lead hook fires `evaluate_trigger("form_submission", {...})`.
  - `app/inbox/processor.py` after-match hook fires `evaluate_trigger("inbox_match", {...})`.
- Routers: `/api/automations` admin/head gated for writes.

Frontend:
- New `/automations` admin page — table + drawer-style builder.
- Builder UI: trigger picker → condition rule chips → action picker (with template dropdown for `send_template`).
- `automation_runs` history per automation.

Tests (~12 mock-only):
- automation create / list / update / delete with workspace scope
- evaluate_trigger correctly filters by trigger type
- condition_json evaluator (priority eq, score gte, lead.field is null/notnull)
- send_template action renders `{{lead.company_name}}` substitution
- run-history append on every fire (success / skipped / failed)
- role-gate: manager can read, can't create

#### G2 — Notification dedupe + day-grouping (~0.5 day)

Carryover from Sprint 2.4. Two parts:

Backend:
- Add a `dedupe_key` String(120) column to `notifications` (migration `0021_notifications_dedupe`). Index on `(user_id, dedupe_key, created_at desc)`.
- `services.notify` accepts optional `dedupe_key`; if a notification with the same `(user_id, dedupe_key)` exists in the last 1h, skip the insert (return None).
- `daily_plan_ready` cron writes empty plans with `dedupe_key="daily_plan_empty:{date}"`; the dedupe check stops a flood when a manager has nothing scheduled for many consecutive days.

Frontend:
- NotificationsDrawer: group items by day (Сегодня / Вчера / DD.MM.YYYY) with sticky day headers.

Tests (~3 mock-only).

#### G3 — AmoCRM adapter (~1 day)

Sprint 2.1 G5 carryover. Mirror Bitrix24:
- New `app/import_export/adapters/amocrm.py` — auth via long-lived refresh token; OAuth dance handled by ops manually (the prod env already has Bitrix24 manual config — same shape).
- Lead-import job creates a `bulk_import_run` task with format=`amocrm`.
- Tests (~5 mock-only): adapter parser + mapper happy path + auth-failed branch.

#### G4 — Invite accept-flow + notification (~0.5 day)

Sprint 2.4 carryover. `upsert_user_from_token` should:
- Look up `user_invites` row by email on first sign-in.
- Set `accepted_at = now()` if found.
- Fire `safe_notify(kind='invite_accepted', user_id=invite.invited_by_user_id, ...)` so the inviter sees «{name} принял приглашение» in the bell.
- Tests (~3 mock-only).

Depends on G2 — without dedupe the inviter's drawer fills with system
rows the day they invite a batch of people.

#### G5 — Polish + sprint close (~0.5 day)

- Audit emit hooks for `automation.{create,update,delete}` + `automation_run.{success,failed}`.
- Sprint report `SPRINT_2_5_AUTOMATION_BUILDER.md`.
- Brain memory rotation (00 + 02 + 04).
- Smoke checklist additions: /automations + invite-accept ping.

### NOT ALLOWED (out of scope)

- **Multi-step automation chains.** v1 is one trigger → one action. Sequential «send email then wait 3 days then create task» lands in a future sprint.
- **Automation marketplace / cross-workspace sharing.** Phase 3.
- **AI-generated message bodies.** v1 only renders existing templates with `{{lead.field}}` substitution. Generative inserts are a separate feature.
- **Custom Webhook trigger / action.** Useful but big surface; lands in 2.6+.
- **Workspace AI override → fallback chain wiring** — still env-first; carries over from 2.4.
- **Custom-field render on LeadCard** — still carries over.
- **Sentry activation** — still parked.

## Carryovers from Sprint 2.4 (full list)

Folded into the gate plan above where applicable; rest tracked here:

1. ✅ G2: notification dedupe + grouping
2. ✅ G4: invite accept-flow + notification
3. ⏸ Pipeline header (accent → +Лид; Sprint → outline) — 2.5 polish or 2.6
4. ⏸ Default pipeline 6–7 stages confirm — light-touch DB seed change
5. ⏸ Settings sidebar «Скоро» collapse — frontend-only
6. ⏸ LeadCard `window.confirm` → modal on Lost
7. ⏸ Mobile Pipeline fallback (<md) — better vertical card layout
8. ⏸ Custom-field render on LeadCard — still deferred (2.5+ polish)
9. ⏸ Stage-replacement preview in PipelineEditor — Sprint 2.3 carryover
10. ⏸ Workspace AI override → fallback chain wiring — Sprint 2.4 G3 carryover
11. ⏸ dnd-kit reorder for Custom Fields position — Sprint 2.4 G3 carryover
12. ⏸ Sentry activation — Sprint 2.1 G10 carryover, parked

## Risks

1. **Trigger-hook fan-out cost.** Every stage_change / form_submission / inbox_match now spends extra time iterating workspace automations. v1 ships with a synchronous evaluator; if any workspace gets >50 automations, profile the hot path before the next sprint.
2. **Template variable schema drift.** G1 needs a single source of truth for «what `{{lead.*}}` keys exist». Use `app/leads/schemas.py:LeadOut.model_fields` at render time so removing a column doesn't silently render «{{lead.deleted_field}}» literally — substitute with a clear «[unknown field]» marker plus a worker log warning.
3. **Notification dedupe + accept-flow ordering.** G4 requires G2 to ship first. The plan above has G2 → G3 → G4; do not reorder.
4. **AmoCRM OAuth refresh.** Bitrix24 has a manual ops dance; AmoCRM is similar. The adapter should run in stub mode if `AMOCRM_REFRESH_TOKEN` is empty — same pattern as the SMTP/Supabase stubs.
5. **2.4 carryover bundling.** Most of the carryover items live as small isolated polish tickets; do NOT smear them across the automation gates.

## Stop conditions — post-deploy smoke checklist

Update `docs/SMOKE_CHECKLIST_2_4.md` (or fork to `_2_5.md`) with:
- [ ] /automations — admin only, table loads, builder modal opens
- [ ] Trigger fires — move a lead's stage, the matching automation runs, history row visible
- [ ] /settings → Команда — invite a teammate, sign in as them, the inviter's bell shows «принял приглашение»
- [ ] All 9 prior smoke checks (from 2.4) still pass

## Done definition

- Migrations 0020 (automations / automation_runs) + 0021 (notifications dedupe_key) apply cleanly via `alembic upgrade head` on staging.
- Automation Builder ships end-to-end: create automation → trigger fires → action executes → run history appears.
- Invite accept-flow writes `accepted_at` and pings the inviter.
- Notification dedupe stops the empty-daily-plan fan-out.
- ≥23 new mock tests across G1–G4. Combined baseline ≥304 mock tests passing (281 + 23).
- `pnpm typecheck` + `pnpm build` clean.
- Sprint report written, brain memory rotated.
- 0 new npm deps target (matches Sprints 2.0 / 2.1 / 2.2 / 2.3 / 2.4).

---

**Out-of-scope but parked here for awareness — fold into 2.6+:**

- AI-generated message bodies in templates (Sprint 2.5 NOT-ALLOWED)
- Multi-step automation chains (Sprint 2.5 NOT-ALLOWED)
- Custom Webhook trigger / action (Sprint 2.5 NOT-ALLOWED)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder (Sprint 2.0 deferred)
- Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- `pnpm add @sentry/nextjs` activation (Sprint 2.1 G10 carryover)
- Sentry DSNs (Sprint 1.5 soft-launch carryover; pg_dump cron CLOSED in 2.4 G5)
- Per-stage gate-criteria editor (Phase 3)
- Pipeline cloning / templates (Sprint 2.3 carryover)
- Cross-pipeline reporting (Phase 3)
- DST-aware cron edge handling
- Custom-field render on LeadCard (Sprint 2.4 carryover)
- Stage-replacement preview in PipelineEditor (Sprint 2.3 carryover)
- Workspace AI override → fallback chain (Sprint 2.4 G3 carryover)
- dnd-kit reorder for Custom Fields position (Sprint 2.4 G3 carryover)
- Pipeline header polish (accent / outline button variants)
- Default pipeline 6–7 stages confirm
- Settings sidebar «Скоро» collapse
- LeadCard `window.confirm` → modal on Lost
- Mobile Pipeline fallback (<md)
