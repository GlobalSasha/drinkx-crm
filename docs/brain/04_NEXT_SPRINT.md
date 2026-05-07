# Next Sprint: Phase 1 Sprint 1.4 — Daily Plan + Follow-ups

Status: **READY TO START**
Branch: `sprint/1.4-daily-plan`

## Goal

Every morning, every active manager opens `/today` and sees a prioritized,
time-boxed plan: which leads to call, in which order, why, with a one-line
hint. Follow-up reminders auto-create tasks 24h before due. Both run on
Celery beat (the first long-running scheduled work in the system).

PRD reference: §6.5 (Daily Plan), §6.10 (Follow-ups).

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 1.3 left us
- `docs/brain/01_ARCHITECTURE.md` — AI module #2 (Daily Plan Generator)
- `docs/brain/03_DECISIONS.md` — ADR-007 (AI proposes, human approves; auto-email reminders are drafts), ADR-018 (MiMo for bulk → daily plans use MiMo Flash)
- `docs/PRD-v2.0.md` §6.5 if it has the original PriorityScorer math
- `docs/brain/sprint_reports/SPRINT_1_3_AI_ENRICHMENT.md` — for the LLM provider/factory pattern this sprint reuses
- Prototype `crm-prototype/index-soft-full.html` — Today screen visual reference

## Scope

### ALLOWED

**Schema migration** (`alembic 0004_daily_plan_followup_celery`):
- `daily_plans` table:
  - `id` UUID PK, timestamps
  - `workspace_id` UUID FK CASCADE, indexed
  - `user_id` UUID FK CASCADE, indexed
  - `plan_date` DATE — local-date in user's timezone
  - `generated_at` DateTime(tz)
  - `status` String(20) — `pending` | `generating` | `ready` | `failed`
  - `generation_error` Text NULL
  - `summary_json` JSON — `{total_minutes, count, urgency_breakdown}`
  - UNIQUE constraint `(user_id, plan_date)` so re-runs replace one plan
- `daily_plan_items` table:
  - `id` UUID PK, timestamps
  - `daily_plan_id` UUID FK CASCADE, indexed
  - `lead_id` UUID FK SET NULL — soft link
  - `position` Integer (sort order in the plan)
  - `priority_score` Numeric(6, 2) — output of PriorityScorer
  - `estimated_minutes` Integer (default 15)
  - `time_block` String(20) NULL — `morning` | `midday` | `afternoon` | `evening`
  - `task_kind` String(30) — `call` | `email` | `meeting` | `research` | `follow_up`
  - `hint_one_liner` Text — LLM-generated one-line nudge
  - `done` Boolean default false
  - `done_at` DateTime(tz) NULL
- `scheduled_jobs` table (small audit log of Celery runs):
  - `id` UUID PK, timestamps
  - `job_name` String(80) — `daily_plan_generator` | `followup_reminder_dispatcher`
  - `started_at`, `finished_at` DateTime(tz)
  - `status` String(20) — `succeeded` | `failed` | `skipped`
  - `affected_count` Integer default 0
  - `error` Text NULL

**New backend modules:**
- `apps/api/app/scheduled/` (currently empty package):
  - `__init__.py` exports the registered tasks
  - `celery_app.py` — Celery app factory, broker = Redis, backend = Redis, beat schedule registry
  - `jobs.py` — Celery tasks: `daily_plan_generator()`, `followup_reminder_dispatcher()`
  - `beat_schedule.py` — declarative schedule (one entry per cron)
- `apps/api/app/daily_plan/`:
  - `models.py` — `DailyPlan`, `DailyPlanItem`
  - `schemas.py` — `DailyPlanOut`, `DailyPlanItemOut`, `MarkDoneIn`
  - `repositories.py` — query latest plan for user/date
  - `services.py` — `generate_for_user(user_id, plan_date)` orchestrator
  - `priority_scorer.py` — pure function `score_lead(lead, now) -> float`
  - `routers.py` — `GET /me/today`, `GET /daily-plans/{date}`, `POST /daily-plans/{date}/regenerate`, `POST /daily-plans/items/{id}/complete`
- `apps/api/app/followups/dispatcher.py`:
  - `run_dispatch(now)` — iterates followups with `due_at` between (now-15min) and (now+24h), creates `Activity(type='task'|'reminder')`, idempotent via `dispatched_at` flag (add column to `followups`)

**Priority scorer** (PRD §6.5 + ADR-018):
```
score = stage.probability                      # 0..100, baseline
      + 25 if next_action_at is overdue
      + 15 if next_action_at within 24h
      + 10 if priority == 'A'
      +  5 if priority == 'B'
      +  3 if priority == 'C'
      + 20 if rotting_stage_or_next_step
      + (lead.fit_score or 0) * 1.0            # 0..10 nudge
      - 50 if archived / won / lost
```
Tunable weights live in `app/daily_plan/priority_scorer.py` constants — easy to swap later.

**Daily plan generator flow** (Celery task):
1. Resolve all active managers per workspace (where `User.role` ∈ `{manager, head, admin}` and `last_login_at` within 30 days).
2. For each user: collect `Lead` rows where `assigned_to == user.id` AND `assignment_status == 'assigned'` AND not archived/won/lost.
3. Score each lead via `priority_scorer.score_lead()`.
4. Sort desc, take top N where `sum(estimated_minutes) <= work_hours_minutes_today` (from `User.working_hours_json`, fall back to 6h × 60min).
5. For each item, call `complete_with_fallback(daily_plan)` (MiMo Flash) with:
   - System: short DrinkX profile + "Ты пишешь однострочную подсказку для менеджера: что сделать с этим лидом сегодня"
   - User: lead summary + last activity + AI Brief excerpt + next_action_at
6. Build `DailyPlan` row with `status=ready` and child `DailyPlanItem` rows. Replace any prior plan for the same `(user_id, plan_date)` (UNIQUE constraint handles).
7. Use the existing budget guard (`add_to_daily_spend`) so daily plans don't blow the AI budget.

**Cron schedule (`beat_schedule.py`):**
- `daily_plan_generator` — runs hourly at minute 0; each run skips workspaces whose timezone-local time is not 08:00. Cheap to run; one workspace per hourly slice ensures correctness across timezones.
- `followup_reminder_dispatcher` — runs every 15 minutes, no timezone filter (reminders don't care about local morning).

**Frontend:**
- `apps/web/app/(app)/today/page.tsx`:
  - Replace the placeholder "create lead" empty state with the real plan
  - Header: greeting, date in user timezone, total minutes / total tasks
  - Time-blocked rendering: morning / midday / afternoon / evening sections
  - Each item: lead company, hint_one_liner, task_kind chip, estimated minutes,
    "✓ Готово" button (POST `/daily-plans/items/{id}/complete`)
  - "🔄 Пересобрать план" button (admin/head/manager) → POST `.../regenerate` → optimistic running spinner + invalidate
  - Empty state preserved when no plan generated yet (with "Сформировать сейчас" CTA)
- `apps/web/lib/hooks/use-daily-plan.ts` — `useTodayPlan()`, `useRegeneratePlan()`, `useCompletePlanItem()`
- TS types: `DailyPlan`, `DailyPlanItem`, `TimeBlock`, `TaskKind`

**Infra updates:**
- `infra/production/docker-compose.yml`: enable the commented-out `worker` service for Celery worker (`celery -A app.scheduled.celery_app worker -l INFO`)
- Add a `beat` service (`celery -A app.scheduled.celery_app beat -l INFO`) — single-replica, no fancy scheduler backend needed yet
- Both share the API image; just override the CMD
- `redis_url` already in env — Celery uses it as broker + result backend

**Tests required:**
- pytest: `priority_scorer` unit tests for each weight component (overdue, rotting, archived, fit_score, priority A/B/C/D)
- pytest: `daily_plan.services.generate_for_user` happy path with mocked LLM
- pytest: `daily_plan_generator` skips users not at 08:00 local
- pytest: `followup_reminder_dispatcher` is idempotent (run twice → one Activity per Followup)
- pytest: `regenerate` endpoint replaces a prior plan (unique constraint test)
- pytest: budget guard fires when daily AI spend exceeded → plan status=`failed` with reason
- web Playwright (or skipped if browser env not in CI): `/today` renders 5 mocked items with correct time-block grouping

**Environment additions:**
- None new — Celery uses existing `REDIS_URL`. `MIMO_API_KEY` already wired.

### FORBIDDEN

- WebSocket for daily plan progress (Phase G of Sprint 1.3 covers this; daily plan can render with simple invalidate-on-complete)
- Mobile / push notifications (Sprint 1.5)
- Sales Coach chat (Phase 3)
- Vector DB / similar-deal retrieval (Phase 3)
- Anything in `apps/api/app/auth/` beyond reading `user.timezone` and `user.working_hours_json`
- Replacing the LLM provider stack — reuse `complete_with_fallback`

## Tests required

(See list under "Backend modules" above — 7 backend test groups + 1 web e2e)

## Deliverables

- Migration `0004` on production
- Celery worker + beat services running on the prod docker-compose stack
- `/today` shows a generated plan after the next 08:00 cron tick
- `docs/brain/sprint_reports/SPRINT_1_4_DAILY_PLAN.md` written
- Update `docs/brain/00_CURRENT_STATE.md`
- Update `docs/brain/02_ROADMAP.md`
- Update `docs/brain/04_NEXT_SPRINT.md` → Sprint 1.5 Polish

## Stop conditions

- All tests pass → report written → committed → STOP
- No push to main without product-owner approval
- No scope creep into Sprint 1.5 items

---

## Recommended task breakdown (one PR per group)

1. **Schema** — migration 0004 + DailyPlan/DailyPlanItem/ScheduledJob models + tests
2. **PriorityScorer** — pure function + unit tests (no DB; just deterministic math)
3. **Daily-plan service + LLM hint** — generate_for_user pipeline, mocked LLM tests
4. **Celery setup + beat schedule** — celery_app, beat_schedule, daily_plan_generator + followup_reminder_dispatcher tasks; idempotency tests
5. **REST endpoints** — `/me/today`, regenerate, mark-done; route tests
6. **Frontend Today** — real data wiring, time-block grouping, complete button, regenerate
7. **Infra** — uncomment worker + beat services in docker-compose; `deploy.sh` smoke; first scheduled run

---

## Followups parked (Sprint 1.3 phases F + G)

These are NOT part of Sprint 1.4 but make sense to bundle if there's
spare time once Celery is up:
- **Phase F** — Knowledge Base markdown library + tag-based grounding for synthesis prompts
- **Phase G** — Move enrichment orchestrator off `BackgroundTasks` and onto Celery (now that Celery exists for daily plans). Add WebSocket `/ws/{user_id}` for real-time progress; replace 2s polling.

Both nice-to-have. Skip them if 1.4 runs long.
