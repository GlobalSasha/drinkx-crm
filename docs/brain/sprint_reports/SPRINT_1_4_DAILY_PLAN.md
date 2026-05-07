# Sprint 1.4 — Daily Plan + Follow-ups Report

**Closed on:** 2026-05-07
**Branch flow:** `sprint/1.4-daily-plan` (Phases 1+2+3) → main → 4 hotfixes pushed directly to main while debugging the prod deploy
**Status:** ✅ Live in production · Celery worker + beat running for the first time on this stack

---

## Scope vs original plan

Original Sprint 1.4 envelope (`04_NEXT_SPRINT.md` at the start of the sprint):
1. Migration `0004` — `daily_plans`, `daily_plan_items`, `scheduled_jobs`
2. ORM models + register in alembic env.py
3. `priority_scorer.py` pure function
4. `daily_plan/services.py` `generate_for_user()` orchestrator
5. Celery worker + beat (first Celery service in the system)
6. `daily_plan_generator` cron (hourly, timezone-filtered)
7. `followup_reminder_dispatcher` cron (every 15 min, idempotent)
8. REST endpoints (`GET /me/today`, regenerate, complete-item)
9. Frontend `/today` rewrite — real plan rendering
10. Infra updates — enable worker + beat in docker-compose

What was delivered:

| # | Scope | Status |
|---|---|---|
| 1–4 | Phase 1 — schema + scorer + service | ✅ `ac36c35` |
| 5–7 | Phase 2 — Celery + cron + dispatcher + audit | ✅ `7ce3a6b` |
| 8–9 | Phase 3 — REST + frontend `/today` | ✅ `c90c902` |
| ↳ | UI density / pagination polish | ✅ `aa365f9` (frontend-design audit) |
| ↳ | docker-compose worker + beat services | ✅ inside `7ce3a6b` |
| ↳ | Hotfixes for the deploy chain | ✅ 4 commits (see "Production blockers" below) |

**Total:** 9 commits on main, ~3500 lines, 45+ new tests.

---

## What shipped

### Phase 1 — Foundation (`ac36c35`)
- Migration `0004` adds `daily_plans` (UNIQUE on `(user_id, plan_date)` for upsert), `daily_plan_items`, `scheduled_jobs`. CAST(:p AS json) pattern; String columns for status/task_kind/time_block (no native ENUM).
- ORM models + `lead` relationship on `DailyPlanItem` with `lazy="raise"` so missing eager-load is loud in dev.
- `priority_scorer.score_lead(lead, stage, now)` — pure function, module-level tunable weights:
  ```
  base = stage.probability                    (0..100)
       + 25 if overdue
       + 15 if due within 24h
       + 10/5/3 for priority A/B/C
       + 20 if rotting (stage or next-step, counted once)
       + fit_score (0..10) × 1
       - 50 if archived/won/lost
       -100 if not assigned
  ```
- `DailyPlanService.generate_for_user()`:
  1. fetch assigned leads + stages
  2. score, sort desc
  3. pack into `working_hours_minutes_today` (default 360 = 6h)
  4. MiMo Flash 1-line hint per item via `complete_with_fallback(daily_plan)` with deterministic fallback on per-item failure
  5. spread items into morning/midday/afternoon time-blocks
  6. upsert via DELETE-then-INSERT inside one transaction (UNIQUE constraint guarantees no double plans)
  7. write status=`failed` with error message on top-level catastrophic blow-ups, never raise to caller
  8. `add_to_daily_spend(workspace_id, total_cost_usd)` rolls hint cost into the existing Sprint 1.3 budget guard
- 25 unit tests (priority scorer + service)

### Phase 2 — Celery + cron (`7ce3a6b`)
- Migration `0005` adds `followups.dispatched_at` for idempotency.
- `app/scheduled/celery_app.py` — Celery app `"drinkx"`, Redis broker+backend, UTC clock, `task_time_limit=600s`, `worker_max_tasks_per_child=200`.
- Beat schedule:
  - `daily-plan-generator` → `crontab(minute=0)` every hour at :00 UTC
  - `followup-reminder-dispatcher` → `crontab(minute="*/15")`
- `app/scheduled/jobs.py` — task entry points; each opens a fresh DB session and writes a `ScheduledJob` audit row (status / affected_count / error[:2000]).
- `app/scheduled/daily_plan_runner.py` — iterates active managers (last_login within 30 days), filters to those whose IANA `user.timezone` local hour == 8, calls `generate_for_user`. Per-user failures are caught and don't kill the tick.
- `app/followups/dispatcher.py` — `run_followup_dispatch` finds Followups due in +24h that aren't dispatched yet, creates `Activity(type='reminder')` for each, stamps `dispatched_at`. Idempotent.
- `infra/production/docker-compose.yml` — `api.environment` extracted to `&api-env` YAML anchor; new `worker` (concurrency=2) and `beat` services share image + env via `<<: *api-env`.
- 13 tests (runner / dispatcher / wiring)

### Phase 3 — REST + frontend (`c90c902`)
- `DailyPlanOut` / `DailyPlanItemOut` (joined `lead_company_name/segment/city`) / `RegenerateOut` Pydantic DTOs.
- Service additions: `get_plan_for_user_date`, `get_today_plan_for_user` (timezone-aware), `list_plans_for_user`, `mark_item_done` (cross-user guard), `request_regenerate` (creates `generating` row + dispatches Celery `regenerate_for_user`).
- New Celery task `regenerate_for_user` — same `generate_for_user` core, no 08:00-local gate (UI manual trigger).
- Routes: `GET /api/me/today`, `GET /api/daily-plans/{date}`, `POST /api/daily-plans/{date}/regenerate` (202), `POST /api/daily-plans/items/{id}/complete`.
- Frontend `/today` rewritten:
  - States: empty / generating (shimmer + 2s poll) / failed (red banner) / ready
  - Time-block sections: Утро / День / После обеда / Вечер / Без времени
  - Item cards with task kind chip + minutes + priority_score + ✓ checkbox + click-to-Lead-Card
  - "🔄 Пересобрать план" button
- Hooks: `useTodayPlan` (refetchInterval=2s while `generating`), `useRegenerate`, `useCompletePlanItem`
- 7 route tests

### Polish (`aa365f9`) — frontend-design audit
- Card density reduced ~110px → ~72px (single primary row + sub-hint line)
- URL-driven pagination (`?page=N`, `PAGE_SIZE=10`); pagination resets on `plan.id` change, not on status flips, so polling doesn't re-trigger reset
- Hot-lead 2px left rail when `priority_score >= 80` (urgency signal at zero horizontal cost)
- Skeleton matches new card height (`h-[72px]`) — no layout shift on `generating → ready`
- `SEGMENT_LABELS` lifted from leads-pool to shared `lib/i18n.ts`
- Done items: 50% opacity + strikethrough; section heading shows `<count> · <done> ✓`

---

## Production blockers (4 hotfixes during deploy)

The Sprint 1.4 merge succeeded (`e10838e`). Three subsequent deploys failed in a row before we found the chain of issues. **Took ~2 hours to debug** because each failure unmasked the next.

### Hotfix 1 — `4dd4b7d`: Node 22 in Dockerfile
Two deploys failed at `pnpm build` with:
```
node:internal/modules/cjs/loader:1031
Error [ERR_UNKNOWN_BUILTIN_MODULE]: No such built-in module: node:sqlite
warn: This version of pnpm requires at least Node.js v22.13
```
Corepack auto-upgraded to **pnpm 11.0.8**, which dropped Node 20 support. Bumped `apps/web/Dockerfile` from `node:20-alpine` to `node:22-alpine`.

### Hotfix 2 — `b720f5d`: pnpm pinned + build-script allow-list
Node 22 unmasked the next pnpm 11 surprise: `[ERR_PNPM_IGNORED_BUILDS]` for `esbuild` / `sharp` / `unrs-resolver`. pnpm 11 default-denies install scripts unless explicitly approved. Two-part fix:
- `packageManager: "pnpm@10.18.0"` in `apps/web/package.json` — corepack now downloads exactly that version; deploys reproducible, no more "latest pnpm" trap
- `pnpm.onlyBuiltDependencies: ["esbuild", "sharp", "unrs-resolver"]` — belt-and-suspenders allow-list

### Hotfix 3 — `e5b8fe9`: Celery worker mapper-registry hydration
Worker fired `followup_reminder_dispatcher` and crashed with:
```
sqlalchemy.exc.InvalidRequestError: When initializing mapper Mapper[Lead(leads)],
expression 'Contact' failed to locate a name ('Contact')
```
Worker process never imports `app.main` (only `app.scheduled.celery_app`), so the chain that side-effect-imports every domain's models module never ran. SQLAlchemy mapper registry was incomplete; string-based forward references like `Lead → Contact / Activity / Followup` couldn't resolve.

Fix: side-effect imports for every domain's models at the top of `celery_app.py`. Same pattern we used in the 131-leads import script (`5a4f78d`).

### Hotfix 4 — `8d2e644`: Per-task NullPool engine
After mapper fix, worker fired again and immediately raised:
```
RuntimeError: Task <Task pending> got Future attached to a different loop
```
Each Celery task wraps its work in `asyncio.run()` — a NEW event loop per invocation. The global SQLAlchemy `AsyncEngine` caches an asyncpg connection pool whose connections are bound to the FIRST loop. Reusing them on a fresh loop crashes.

This was also why the user's manual "Сформировать" left a `DailyPlan` row stuck at `status='generating'` — the `regenerate_for_user` task crashed inside the orchestrator path. The frontend then polled `/me/today` every 2s forever (visible in api logs as a wall of `GET /me/today HTTP/1.1 200 OK`).

Fix: `_build_task_engine_and_factory()` helper builds a per-invocation engine with `NullPool`. Connections are created and closed inside the task; no cross-loop reuse possible. `engine.dispose()` in `finally` for clean release. Small connection-setup latency, fine for short cron work. The global engine in `app.db` stays untouched and continues serving the API where loops are long-lived per worker.

---

## Production state at sprint close

| Container | Status |
|---|---|
| `drinkx-api-1` | ✅ Up, healthy |
| `drinkx-web-1` | ✅ Up |
| `drinkx-worker-1` | ✅ Up (NEW — first Celery service) |
| `drinkx-beat-1` | ✅ Up (NEW — first cron scheduler) |
| `drinkx-postgres-1` | ✅ Up 44h, healthy |
| `drinkx-redis-1` | ✅ Up 44h, healthy |

| Concern | State |
|---|---|
| Migrations 0004 + 0005 | ✅ Applied |
| Beat firing tasks | ✅ Confirmed in logs (11:45 / 12:00 ticks) |
| Worker mapper registry | ✅ Fixed in `e5b8fe9` |
| asyncpg cross-loop | ✅ Fixed in `8d2e644` |
| First successful `followup_reminder_dispatcher` | ✅ 12:00 tick: `affected=0` (no due followups in window) |
| First `daily_plan_generator` | ✅ 12:00 tick fired; no users at 08:00 local at 12:00 UTC, so 0 plans generated — expected |
| Frontend `/today` empty state | ✅ Renders |
| Manual regenerate button | ⚠ Not yet end-to-end-tested with screenshot confirmation in the new build (the user had a stuck `generating` row from the loop bug; that needs to be cleared or auto-flipped to `failed` by the next regenerate) |
| `/today` compact cards + pagination | ✅ Live in build, screenshot pending |

## Tests on `main`

- 14 priority scorer unit tests
- 11 daily plan service tests
- 4 daily plan runner tests
- 5 followup dispatcher tests
- 2 celery wiring tests
- 7 route tests
- (plus all 76 from Sprint 1.0–1.3 staying green)

Pre-existing failure (`test_factory_raises_when_all_fail`) from Sprint 1.3 still present — unrelated to this sprint.

---

## Decisions made during the sprint

- **Per-task engine with NullPool** instead of trying to re-use the global engine across event loops. Cleaner separation; small latency cost is fine for cron.
- **Polling every 2s** for `/me/today` while `generating` instead of WebSocket — keeps Phase 3 simple. WebSocket can land alongside Phase G of Sprint 1.3 if/when needed.
- **DELETE-then-INSERT upsert** for plan replacement instead of MERGE / ON CONFLICT — the `UNIQUE(user_id, plan_date)` constraint is the contract; explicit deletion avoids stale `daily_plan_items` rows.
- **Hourly beat tick + per-user timezone filter** instead of one cron per timezone — single source of truth, easy to reason about.
- **Tunable weights as module-level constants** in `priority_scorer.py` — Sprint 1.5+ can move them to a settings table when there's a real need.
- **FastAPI BackgroundTasks for enrichment kept**, Celery for daily_plan only. Phase G of Sprint 1.3 (move enrichment off BackgroundTasks) is now trivial — the Celery infra exists; just wire the orchestrator into a task.
- **`packageManager` field in package.json** — non-negotiable from now on. Without it, every `corepack enable` is a roulette wheel against pnpm major releases.
- **frontend-design skill is mandatory** for any UX-impacting frontend work. The audit on `/today` (`aa365f9`) demonstrably improved density and visual hierarchy.

---

## Known issues / risks

1. **Stuck `DailyPlan` row from the loop bug** — the user has at least one row with `status='generating'` from before `8d2e644` deployed. Either: (a) trigger another regenerate (will replace via UNIQUE upsert), or (b) write a one-shot SQL to flip such rows to `'failed'`. Low priority — UI handles `failed` correctly.
2. **DST / timezone edges** — `daily_plan_generator` runs hourly and matches local 8am exactly. On DST transition days, an hour gets skipped or duplicated. Acceptable for now.
3. **No retry on per-user failure** in the daily plan cron — if one user's LLM call times out, that user gets no plan today. Logged but silent. Sprint 1.5 could add a retry queue.
4. **Worker concurrency=2** — fine for two cron jobs. If we add more (Phase G enrichment migration), bump to 4 and split into separate queues by task type.
5. **No frontend "regenerate this lead's hint" button** — only full-plan regenerate. Probably fine; LLM hints are cheap, full regen is fast.
6. **`docker-compose.yml` uses `version` not specified** — Compose v2 doesn't need it, but if anyone resurrects v1 it'll break. Cosmetic.

---

## Files changed (cumulative)

```
apps/api/alembic/versions/
  20260507_0004_daily_plan.py
  20260507_0005_followups_dispatched_at.py
apps/api/app/daily_plan/
  __init__.py
  api_schemas.py
  models.py
  priority_scorer.py
  routers.py
  schemas.py
  services.py
apps/api/app/followups/dispatcher.py
apps/api/app/followups/models.py            (+ dispatched_at column)
apps/api/app/scheduled/
  __init__.py
  celery_app.py                             (Celery app + beat schedule + side-effect model imports)
  daily_plan_runner.py
  jobs.py                                   (task entry points + per-task NullPool engine)
apps/api/app/main.py                        (registered daily_plan_router)
apps/api/alembic/env.py                     (registered DailyPlan models)
apps/api/tests/
  test_priority_scorer.py
  test_daily_plan_service.py
  test_daily_plan_runner.py
  test_followup_dispatcher.py
  test_celery_wiring.py
  test_daily_plan_routes.py
apps/web/app/(app)/today/page.tsx           (full rewrite, then redesigned for compact cards + pagination)
apps/web/lib/hooks/use-daily-plan.ts
apps/web/lib/types.ts                       (+ DailyPlan / DailyPlanItem / TimeBlock / TaskKind / DailyPlanStatus / RegenerateResponse / DailyPlanSummary)
apps/web/lib/i18n.ts                        (extracted SEGMENT_LABELS for shared use)
apps/web/Dockerfile                         (node:22-alpine)
apps/web/package.json                       (packageManager + onlyBuiltDependencies)
infra/production/docker-compose.yml         (worker + beat services, &api-env anchor)
AUTOPILOT.md                                (1.4.* items ticked)
```

---

## Next sprint

See `docs/brain/04_NEXT_SPRINT.md` — **Sprint 1.5 — Polish + Launch**.
