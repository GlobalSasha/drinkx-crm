# Next Sprint: Phase 2 Sprint 2.7 — Sentry activation + multi-step automations

Status: **READY TO START** (after Sprint 2.6 merge / deploy / smoke)
Branch: `sprint/2.7-sentry-multistep` (create from main once 2.6 lands)

## Goal

Sprint 2.6 closed CRITICAL stability findings but left two HIGH ones
parked because both depend on a working error-reporting target —
Sentry. The cron swallows in `daily_plan/services.py` +
`scheduled/jobs.py`, the audit-log swallow in `audit/audit.py`, and
the BackgroundTasks-strands-running issue in `enrichment/routers.py`
all log to structlog only. Without a destination that aggregates +
alerts, ops can't know when a daily plan didn't generate or an
enrichment run silently froze.

**Main driver:** activate Sentry (frontend `@sentry/nextjs` +
backend DSN), then unblock the parked work — multi-step automation
chains (Sprint 2.6 G2 skip), tg-channel outbound dispatch (Sprint 2.6
keeps it stubbed), enrichment → Celery (Phase G carryover from
Sprint 1.3).

Net result by close: production has actual visibility into silent
failures + the Automation Builder graduates from one-shot to chains
+ tg messages actually go out + AI Brief progress is real-time.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — Sprint 2.6 close summary
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope + carryover list
- `docs/SPRINT_2_6_OUTBOUND_EMAIL.md` — full 2.6 close + stability audit findings
- `docs/PRD-v2.0.md` §10 (Automation Builder), §11 (Observability)
- Existing surfaces to extend, not replace:
  - `apps/web/lib/sentry.ts` — already has the lazy-require Sentry init guard (Sprint 2.1 G10); G1 activates it
  - `app/scheduled/jobs.py` + `app/scheduled/digest_runner.py` + `app/scheduled/daily_plan_runner.py` — cron swallow sites
  - `app/automation_builder/services.py` + `dispatch.py` — Sprint 2.6 baseline; multi-step builds on top
  - `app/inbox/gmail_client.py` — HTTP client style to mirror for the tg Bot API
  - `app/enrichment/routers.py:67` — `background.add_task(_bg_run, ...)` — the FastAPI BackgroundTasks site to migrate
- Production state at sprint start: 4 app containers + 4 cron entries running, all 2.0–2.6 surfaces live, Sprint 2.6 merged.

## Scope

### ALLOWED

#### G1 — Sentry activation (~1 day)

Frontend:
- `pnpm add @sentry/nextjs` — first net-new dep since Sprint 2.0 / 2.1.
  Document explicitly in the sprint report.
- Activate `apps/web/lib/sentry.ts` — the lazy-require guard already
  exists (Sprint 2.1 G10); flip it from warn-once to live by
  installing the package + setting `NEXT_PUBLIC_SENTRY_DSN`.
- Error boundaries on `/today`, `/pipeline`, `/leads/[id]`,
  `/automations`, `/audit`, `/settings`. Each catches render failures
  + posts to Sentry with route + user_id breadcrumb.
- `app/(app)/layout.tsx` — global `Sentry.captureException` on
  unhandled promise rejection.

Backend:
- `pip install sentry-sdk[fastapi]` (1 new Python dep).
- `app/main.py` — initialize on app startup if `SENTRY_DSN` env
  var is set. Stub mode (empty DSN) keeps existing behaviour.
- Wrap the cron-swallow sites with `sentry_sdk.capture_exception`
  alongside the existing structlog warning. Don't change the
  swallow shape — the parent task continues — just add the report.
- Wrap `audit.log()` swallow with `capture_exception`.
- Wrap the `BackgroundTasks` enrichment failure path so a stranded
  `EnrichmentRun.status='running'` row triggers a Sentry issue
  with the run id as fingerprint.
- Structured fingerprints per cron entry — operators can mute
  noisy ones without losing visibility on others.

Tests (~4 mock-only):
- Sentry init no-op when DSN is empty (stub mode)
- `audit.log()` swallow path calls `capture_exception` once
- `safe_evaluate_trigger` swallow path calls `capture_exception`
- daily-plan cron failure → `capture_exception` fires + structlog
  warning still emits

#### G2 — Multi-step automation chains (~1.5 days)

Backend:
- Migration `0021_automation_steps`:
  - Approach (decided at G2 plan-review based on production
    `automations` row count at that time): either drop the single
    `action_type` / `action_config_json` columns and replace with a
    `steps_json` array, OR keep them as «step 0» legacy and add
    a separate `automation_steps` table. The cheaper path wins.
  - `automation_step_runs` (automation_run_id CASCADE, step_index,
    scheduled_at, executed_at, status, error). One row per step
    per fire.
- `evaluate_trigger` plumbing — when an automation has multiple
  steps, fire step 0 immediately and schedule subsequent steps via
  Celery countdown task.
- New beat entry `automation_step_scheduler` — every 5 min, picks
  up `automation_step_runs` rows where `executed_at IS NULL` and
  `scheduled_at <= now()`, runs the step, flips the row.
- Step types: `delay_hours` (no action, just gates next step's
  schedule) + the existing 3 action types as steps.

Frontend:
- /automations builder modal — switch from single-action picker to
  a step list with «Добавить шаг» CTA. Reorder via dnd-kit (already
  installed via Sprint 2.6 G4 — share the lib).
- RunsDrawer renders a per-step status grid below the parent run.

Tests (~8 mock-only):
- 2-step chain happy path (action → delay → action)
- delay step schedules at correct timestamp
- failure in step 0 stops chain; step 1 stays unscheduled
- failure in step 1 doesn't roll back step 0's effect
- beat scheduler picks up due rows + skips not-yet-due
- multi-clause condition still works at chain entry
- step ordering preserved
- migration 0021 upgrade + downgrade clean

Risk: this gate is the largest in 2.7. If G2 scope creeps, defer
multi-step to 2.8 and use freed time for additional polish in G3+G4.
Document at G2 plan-review.

#### G3 — tg channel outbound dispatch (~1 day)

Backend:
- New `app/telegram/sender.py` — Telegram Bot API client. Same
  tri-state contract as `app/email/sender.py` (True real send /
  False stub mode / raise `TelegramSendError`).
- New env: `TELEGRAM_BOT_TOKEN`. Stub mode when empty.
- `_send_template_action` for `channel='tg'` flips from stub to
  real dispatch path — uses the same post-commit drainer in
  `app/automation_builder/dispatch.py`.
- `lead.tg_chat_id` — needs a column. Migration `0022_lead_tg_chat_id`
  adds nullable VARCHAR(64). `_send_template_action` reads it; if
  null, stages `delivery_status='skipped_no_tg'` Activity (mirror
  the email-no-recipient path).

Frontend:
- LeadCard «Контакты» section — add a tg-handle field (text input,
  saves on blur).
- Activity Feed delivery-status chip already supports the tg
  outbound row shape since Sprint 2.6 G1.

Tests (~5 mock-only):
- send_telegram stub-mode → False, no HTTP call
- _send_template_action tg with no chat_id → skipped_no_tg
- tg send success → status='sent'
- tg send failure → re-raise, drainer catches → status='failed'
- migration 0022 upgrade + downgrade clean

SMS deferred to Sprint 2.8 — pricing + provider evaluation is its
own gate.

#### G4 — Enrichment → Celery + WebSocket (~1.5 days)

The Phase G carryover from Sprint 1.3 — move `_bg_run` off
`fastapi.BackgroundTasks` onto Celery. Closes the Sprint 2.6 audit
finding «BackgroundTasks strands EnrichmentRun rows in `running`
state on failure».

Backend:
- New Celery task `app.scheduled.jobs.enrichment_run` — wraps the
  existing `app/enrichment/orchestrator.py` runner with
  `try/except` that flips the row to 'failed' on any exception.
- `app/enrichment/routers.py:67` — replace `background.add_task`
  with `celery_app.send_task("enrichment_run", args=[run_id])`.
- New WebSocket endpoint `GET /ws/{user_id}` (FastAPI WebSocket).
  Backed by Redis pub/sub — every enrichment progress event
  publishes to channel `enrichment:{user_id}`. Frontend subscribes
  and updates the AI Brief progress in real-time.

Frontend:
- New `lib/hooks/use-enrichment-progress.ts` — opens the WebSocket
  on `/leads/[id]` mount, listens for the run's progress events.
- Replace the current poll-based progress card on `/leads/[id]`
  AI Brief tab with the real-time WebSocket version.

Tests (~6 mock-only):
- Celery task on success transitions row to 'succeeded'
- Celery task on exception transitions row to 'failed' with
  truncated error
- WebSocket publishes progress events to the right channel
- Subscriber gets only its own user_id's events

#### G5 — Polish + sprint close (~0.5 day)

- Sprint report `SPRINT_2_7_SENTRY_MULTISTEP.md`
- Brain memory rotation (00 + 02 + 04)
- Smoke checklist additions: `docs/SMOKE_CHECKLIST_2_7.md`
- Audit emit hooks for `automation_step.{success,failed}` (so ops
  can filter «show me all failed multi-step automations today»).

### NOT ALLOWED (out of scope)

- **SMS provider** — own evaluation gate (Sprint 2.8+).
- **Multi-tenancy** — Phase 3.
- **Workspace-level webhook trigger / action** — still parked.
- **AI-generated message bodies** in templates — still parked.
- **AmoCRM adapter** — still in long-tail backlog.
- **Default pipeline 6–7 stages re-seed** — needs prod stage-id
  audit before migration; not a 2.7 priority.
- **Stage-replacement preview** in PipelineEditor — Sprint 2.3
  carryover, not 2.7 scope.

## Carryovers from Sprint 2.6 (full list)

Folded into the gate plan above where applicable; rest tracked here:

1. ✅ G1: Sentry activation
2. ✅ G2: Multi-step automation chains
3. ✅ G3: tg channel outbound dispatch (sms deferred to 2.8)
4. ✅ G4: Enrichment → Celery + WebSocket
5. ⏸ pg_dump cron install on host — operator step open since 2.4 G5;
   does not block any code work
6. ⏸ inbox/processor Celery dispatch retry — small follow-on; can
   slot into G5 polish if time permits
7. ⏸ Custom-field render polish (boolean kind, autosave retry,
   keyboard nav) — 2.8 territory

## Risks

1. **G2 migration shape decision.** Multi-step chains touch the
   `automations` schema. If production has many rows by that point,
   the «drop columns + replace with steps_json» approach needs a
   data-migration path. Plan-review at G2 kickoff with the actual
   row count.
2. **Sentry quota.** Free tier is 5k errors/month. The cron + audit
   swallow sites might burn through that fast on a noisy day.
   Configure Sentry-side rate limits / sample rates in G1.
3. **WebSocket on Railway.** Railway's load balancer historically
   has finicky WebSocket support. Validate on staging in G4 before
   the manager-facing AI Brief replaces the poll path.
4. **`@sentry/nextjs` first net-new dep since 2.0.** Bundle size
   impact (~50KB minified). Document in the sprint report;
   acceptable trade-off for surfacing silent failures.
5. **tg channel without `lead.tg_chat_id` collection flow.** G3
   adds the column + LeadCard input but doesn't auto-discover from
   inbox messages — managers have to type it manually. Auto-link
   from the Sprint 2.0 Gmail inbox is a 2.8+ enhancement.

## Stop conditions — post-deploy smoke checklist

Update `docs/SMOKE_CHECKLIST_2_7.md` with:
- [ ] Trigger a deliberate render error on `/today` → Sentry issue arrives
- [ ] Backend: kill the daily-plan task mid-run → Sentry issue arrives with run-id fingerprint
- [ ] /automations: configure a 2-step chain (send_template → wait 1h → create_task) → step 0 fires immediately, step 1 row appears in `automation_step_runs` with future scheduled_at
- [ ] Wait the delay, run beat scheduler manually → step 1 fires
- [ ] Configure a tg-channel automation, lead with tg_chat_id set → real Telegram message arrives
- [ ] Trigger an enrichment run → AI Brief progress UI updates in real-time without page refresh
- [ ] All 8 prior 2.6 + 7 prior 2.5 + 9 prior 2.4 smoke checks still pass

## Done definition

- Migrations 0021 (automation_steps) + 0022 (lead_tg_chat_id)
  apply cleanly via `alembic upgrade head` on staging.
- Sentry actively receiving errors from frontend + backend on
  staging.
- Multi-step chains end-to-end: trigger → step 0 → wait → step 1 →
  run row history shows per-step status.
- tg channel produces real outbound messages when token is set.
- Enrichment runs survive worker restarts (Celery picks up where
  FastAPI BackgroundTasks would have stranded).
- ≥23 new mock tests across G1–G4. Combined baseline ≥135 mock
  tests passing (112 + 23).
- `pnpm typecheck` + `pnpm build` clean.
- Sprint report written, brain memory rotated.
- Net-new deps: 2 (`@sentry/nextjs` frontend + `sentry-sdk[fastapi]`
  backend) — explicitly documented as the conscious infra trade-off.

---

**Out-of-scope but parked here for awareness — fold into 2.8+:**

- SMS provider evaluation (Sprint 2.7 NOT-ALLOWED)
- Multi-tenancy (Phase 3)
- Workspace-level webhook trigger / action
- AI-generated message bodies in templates
- AmoCRM adapter (long-tail since 2.1)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder (Sprint 2.0 deferred)
- Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- Per-stage gate-criteria editor (Phase 3)
- Pipeline cloning / templates marketplace (Sprint 2.3 carryover)
- Cross-pipeline reporting (Phase 3)
- DST-aware cron edge handling
- Stage-replacement preview in PipelineEditor (Sprint 2.3 carryover)
- Workspace AI override → fallback chain (Sprint 2.4 G3 carryover)
- Multi-clause condition UI in the Automation Builder modal
- Default pipeline 6–7 stages confirm
- Custom-field boolean kind + autosave retry + keyboard nav (Sprint 2.6 G4 polish carryover)
- Auto-discover `lead.tg_chat_id` from Gmail inbox (Sprint 2.7 G3 follow-on)
