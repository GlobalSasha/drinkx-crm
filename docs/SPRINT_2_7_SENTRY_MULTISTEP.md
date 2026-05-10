# Sprint 2.7 — Sentry activation + multi-step automations

**Status:** ✅ DONE (G3 + G4 deferred to long-tail by product decision)
**Branch:** `sprint/2.7-sentry-multistep`
**PR:** [drinkx-crm#12](https://github.com/GlobalSasha/drinkx-crm/pull/12)
**Range:** 2026-05-10 → 2026-05-10
**Tracking:** `docs/brain/04_NEXT_SPRINT.md` (pre-sprint spec)

## Goal

Sprint 2.6 closed CRITICAL stability findings but parked two HIGH ones
because both depend on a working error-reporting target — Sentry.
Sprint 2.7 flips that switch and unblocks the Automation Builder
graduation from one-shot to chains.

**Result:** three gates shipped (G1 Sentry, G2 multi-step, G5 close).
G3 (tg outbound) and G4 (Enrichment → Celery + WebSocket) deferred
to the long-tail backlog — neither blocks the next product priority
(Sprint 3.1 Lead AI Agent) and both have natural homes in Sprint 2.8
or later when there's real customer demand for tg dispatch / real-
time enrichment progress.

## Gates

| Gate | Status | Commit | Date | What shipped |
|---|---|---|---|---|
| Sprint 3.1 spec save | ✅ | `65c5bef` | 2026-05-10 | `docs/SPRINT_3_1_LEAD_AI_AGENT.md` saved so a future session can read it verbatim. Includes a fix-up note that the original migration index 0013 is taken — actual index will be 0023+ once 2.7 lands. |
| **G1** Sentry activation | ✅ | `1c4283d` | 2026-05-10 | New `app/common/sentry_capture.py` (single chokepoint + lazy import); new `app/observability.py` (init_sentry_if_dsn extracted from main.py:lifespan for testability); 4 cron-class swallow sites wrap with `capture()` alongside structlog (audit.log, safe_evaluate_trigger, daily_plan_runner, digest_runner); `_bg_run` enrichment failure path catches + flips status='failed' via new `_mark_run_failed` + reports — closes the Sprint 2.6 audit finding «BackgroundTasks strands rows in 'running' on failure». Frontend: new `lib/sentry-capture.ts` runtime helper; `app/global-error.tsx` + `app/(app)/error.tsx` boundaries; `window.onerror` + `unhandledrejection` listeners in providers.tsx. 8 mock tests. |
| **G2** Multi-step automation chains | ✅ | `03bf762` | 2026-05-10 | Migration 0021: `automations.steps_json JSONB NULL` (additive — null = legacy single-action) + `automation_step_runs` table with partial index `(scheduled_at) WHERE executed_at IS NULL`. `_dispatch_action` collapsed into `_dispatch_step(step)`; handlers refactored to `(lead, config, automation_id_str)` so the same code path serves synchronous step 0 and async step N. New `execute_due_step_runs` driven by `automation_step_scheduler` Celery beat task every 5 min. New `GET /api/automations/runs/{run_id}/steps` for the RunsDrawer per-step grid. Frontend: «Цепочка после первого шага» fieldset in the editor with +Пауза/+Шаблон/+Задача/+Стадия + ↑/↓/✕ controls; expandable per-step grid in RunsDrawer for multi-step automations. 13 mock tests. |
| **G3** tg outbound dispatch | ⏭️ DEFERRED | — | — | Long-tail. tg dispatch shape (Telegram Bot API, lead.tg_chat_id column, send_telegram tri-state contract mirroring `send_email`) is well-understood; lands when there's customer demand for outbound tg automations. Templates with `channel='tg'` still stage `delivery_status='pending'` Activity rows (Sprint 2.5 stub stays). |
| **G4** Enrichment → Celery + WebSocket | ⏭️ DEFERRED | — | — | Long-tail. The strand-on-failure problem is already solved at G1 (`_bg_run` now flips the row to 'failed'). The remaining motivation — real-time AI Brief progress UI — is pure UX and the existing 2-second poll is acceptable; Celery + WS lands when manager-facing progress feedback becomes a priority. |
| **G5** Sprint close | ✅ | this commit | 2026-05-10 | Sprint report, smoke checklist 2.7, brain rotation (00 + 02 + 04). |

## New migrations

**0021_automation_steps** — additive, backwards-compatible:
- `automations.steps_json JSONB NULL` — null/empty = legacy single-action automation continues to fire as before; non-empty array = multi-step chain
- New `automation_step_runs` table with `(automation_run_id, step_index, lead_id, step_json, scheduled_at, executed_at, status, error)`. Step 0 (synchronous fire) gets `executed_at` immediately; steps 1+ get `executed_at IS NULL` and `scheduled_at` in the future for the beat scheduler to pick up.
- Indexes: partial `(scheduled_at) WHERE executed_at IS NULL` for the scheduler hot-path; `(automation_run_id, step_index)` for the RunsDrawer per-step grid.

Decision over the «drop columns + replace with steps_json» alternative
documented in [docs/brain/04_NEXT_SPRINT.md](brain/04_NEXT_SPRINT.md):
chose the additive path because zero data migration risk, legacy
reads keep working, and the multi-step path is genuinely opt-in.
Production has only a handful of automations today; the «cheaper
path» the spec mentioned would have meant deleting their
`action_type` and `action_config_json` columns.

## New beat schedule

- `automation-step-scheduler` — `crontab(minute="*/5")` →
  `app.scheduled.jobs.automation_step_scheduler` →
  `execute_due_step_runs(session)` in
  `app/automation_builder/services.py`. Picks up rows where
  `executed_at IS NULL AND scheduled_at <= now()`, fires through
  `_dispatch_step`, per-row commit + savepoint, post-commit email
  drainer (mirrors the synchronous trigger path).

## REST surface delta

- **New:** `GET /api/automations/runs/{run_id}/steps` →
  `list[AutomationStepRunOut]`. Workspace-scoped via the automation
  join.
- **Updated:** `POST /api/automations` and `PATCH /api/automations/{id}`
  accept an optional `steps_json: list[AutomationStep]` field.
  Validation through new `_validate_steps` (raises `InvalidSteps` →
  400 with code `invalid_steps`).
- Audit log delta now records `steps_count` for multi-step rows.

## Test baseline

- **Pre-sprint:** 112 mock tests passing (Sprint 2.6 close).
- **After G1:** 112 → 120 (+8 sentry-capture tests). 4 existing
  automation_builder + email_sender tests adapted to the new
  `_dispatch_step` / `_send_template_action` signature.
- **After G2:** 120 → 133 (+13 multi-step tests in
  `tests/test_automation_multistep.py`).
- **After G5:** 133 (no new tests — pure documentation work).

Critical-path coverage (G1+G2): **38/38 passing** when run as a
focused subset (`pytest tests/test_email_sender.py
tests/test_automation_builder_service.py
tests/test_automation_multistep.py tests/test_sentry_capture.py`).

Pre-existing 14 fastapi-import failures (env-related — celery /
redis / asyncpg not in local hostpy) unchanged. Per-file run
isolates correctly; full-suite cross-test sys.modules state-leak is
a pre-existing infrastructure issue, not a regression introduced by
2.7.

`pnpm typecheck` clean throughout. `pnpm build` not re-run on G5
close (no UI delta in this gate).

## Net-new dependencies

**0 in this PR.** `sentry-sdk[fastapi]>=2.19.2` was already pinned in
`apps/api/pyproject.toml` since Sprint 2.1 G10 — G1 just wired the
init path. Frontend `@sentry/nextjs` is **still not installed** —
the lazy-require guard in `apps/web/lib/sentry.ts` keeps it
warn-once until an operator runs `pnpm add`. Documented in the
operator follow-on section below.

## Architecture decisions

- **Step storage as `steps_json JSONB` on automations, not a
  separate steps table.** Additive on the row keeps reads cheap
  (one row, no join), and the legacy `action_type` /
  `action_config_json` columns continue to drive single-action
  automations unchanged. The «drop columns + replace» alternative
  from the original spec was deemed riskier than its savings —
  zero data migration is the bigger win.
- **Frozen `step_json` on `automation_step_runs`.** Editing a
  parent automation's `steps_json` mid-chain must NOT change an
  in-flight chain's behaviour. The scheduler reads from the frozen
  snapshot, not the live parent row.
- **`delay_hours` is a no-op at dispatch time.** Its hours roll
  forward into subsequent steps' `scheduled_at` via
  `_compute_schedule_offsets`. The scheduler doesn't queue rows for
  delay steps — they have no side-effect to fire. Cap at 720h (30
  days) to keep typo'd 8760-hour delays from poisoning the queue.
- **Handler signature collapse.** `_dispatch_action(automation,
  lead)` → `_dispatch_step(automation_or_None, lead, step)`. The
  three action handlers (`_send_template_action`,
  `_create_task_action`, `_move_stage_action`) now take `(lead,
  config, automation_id_str)` so the same code path serves both the
  synchronous step 0 fire and the beat scheduler's step N fire
  (where the parent automation row may have been deleted —
  `automation_id_str` is read from the parent run instead).
- **`automation_step_scheduler` runs every 5 min, not every 1 min.**
  Multi-step delays are typically hours, not minutes. 5 min worst-
  case latency on a 24h-delay step is invisible to operators.
- **Step 0 failure stops the chain; step N>0 failure is owned by
  the scheduler.** Step 0 unwinds via SAVEPOINT (parent run row
  status='failed', steps 1+ unscheduled). Step N+ failures don't
  roll back step 0's effect — that already committed. Failed step
  rows stay `status='failed'` indefinitely; admin reruns the
  parent automation manually if recovery is wanted.
- **`Sentry.capture_exception` is no-op when `init()` was never
  called.** That's the production default while DSN is empty.
  `app/common/sentry_capture.py` wraps the call so tests can
  monkeypatch one symbol; lazy-imports `sentry_sdk` so import-time
  cost stays at zero when telemetry is off.

## Risks deferred to Sprint 2.8+

1. **No retry on step N failure.** Failed scheduler rows stay failed.
   Sprint 2.8 could add a `retry_count` column + a backoff schedule.
2. **No pause-mid-chain UI.** Operators have to delete the pending
   `automation_step_runs` row from the DB by hand if they want to
   abort an in-flight chain. Sprint 2.8+ if customers ask.
3. **dnd-kit reorder in builder deferred.** Plain ↑/↓ buttons work
   today; the dnd-kit lib is already on the page from Sprint 2.6
   G4 if a future sprint wants to share it.
4. **Multi-clause condition UI** — single clause still works at
   chain entry (same as Sprint 2.5). N-clause AND/OR is backend-
   ready; UI is the missing piece.
5. **G3 (tg outbound dispatch)** parked. Migration 0022
   (`lead.tg_chat_id`), `app/telegram/sender.py`, LeadCard input
   field — all still in scope when picked up.
6. **G4 (Enrichment → Celery + WebSocket)** parked. The
   strand-on-failure issue is closed by G1's `_mark_run_failed`;
   the only remaining motivation is real-time UI progress, and the
   2-second poll is acceptable today.

## Operator follow-on

Three things need to happen on the production VPS after this PR
merges and auto-deploys:

1. **Frontend Sentry pkg** — `cd /opt/drinkx-crm/apps/web && pnpm add @sentry/nextjs`. ~50KB minified bundle cost (acceptable trade-off; documented). Until the package is installed, `lib/sentry.ts` keeps logging a one-shot warning when `NEXT_PUBLIC_SENTRY_DSN` is set — frontend telemetry stays off but the rest of the CRM is unaffected.

2. **Sentry DSNs in `.env`** — set `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` (frontend) in `/opt/drinkx-crm/infra/production/.env`. Both default to empty (telemetry off — current production state). Once set, redeploy via `deploy.sh` and the lifespan handler picks them up on api startup; the React boundaries pick up the frontend DSN at runtime.

3. **Sentry rate limits / sample rates** — free tier is 5k events/month. Configure project-side rate limits in the Sentry dashboard if cron-class noise burns through that fast. Per-fingerprint mute is available (each swallow site has a stable fingerprint — see G1 commit message).

These are operator steps, not blockers. The merge is safe with all three deferred — telemetry just stays off until the env vars are set.

## Closing checklist

- [x] G1 ships
- [x] G2 ships
- [x] G3 deferred + documented in 02_ROADMAP.md
- [x] G4 deferred + documented in 02_ROADMAP.md
- [x] G5 docs complete (this report + smoke checklist + brain rotation)
- [x] PR #12 merged to main (auto-deploy fires)
- [ ] Smoke checklist 2.7 run on production after deploy (operator step)
- [ ] Operator runs the 3 follow-on items above when ready
