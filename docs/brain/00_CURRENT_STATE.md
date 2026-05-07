# DrinkX CRM — Current State

Last updated: 2026-05-07 (Sprint 1.4 closed)

## Phase 0 — COMPLETED ✅ (lives in `crm-prototype` repo)

Clickable HTML prototypes deployed at https://globalsasha.github.io/drinkx-crm-prototype/

| File | Description |
|---|---|
| `index.html` | Service-grade prototype, 11+ screens, 7+ modals, 3 drawers — full functionality |
| `index-soft-full.html` | taste-soft hi-fi version (Plus Jakarta Sans + double-bezel) |
| `index-soft.html` | Landing / preview page |
| `index-b2b.html` | **B2B enterprise design reference** — 11-stage pipeline, gate criteria, 0-100 scoring, multi-stakeholder, deal type, A/B/C/D priority, dual rotting, pilot contract |
| `data.js` | 131 real DrinkX clients with full enrichment |
| `drinkx-client-map-v0.6-foodmarkets-audit/` | +85 foodmarkets candidates added 2026-05-06 |
| `docs/PRD-v2.0.md` | 988-line product requirements |
| `build_data.py` | Parses drinkx-client-map → data.js |

---

## Phase 1 — IN PROGRESS (production repo `drinkx-crm`)

Production: https://crm.drinkx.tech (live, healthy, auto-deploys on push)
Repo: https://github.com/GlobalSasha/drinkx-crm

### Production stack (4 app containers + 2 infra)

```
drinkx-api-1       FastAPI + Alembic, port 8000 (127.0.0.1)
drinkx-web-1       Next.js 15 + standalone, port 3000 (127.0.0.1)
drinkx-worker-1    Celery worker (NEW Sprint 1.4) — concurrency=2
drinkx-beat-1      Celery beat (NEW Sprint 1.4) — hourly + 15min cron
drinkx-postgres-1  Postgres 16
drinkx-redis-1     Redis 7
```

nginx outside Docker reverse-proxies HTTPS → containers on localhost.

### ✅ Sprint 1.0 — Foundation (DONE)
- Monorepo, Docker stack, GitHub Actions auto-deploy on push to main (~90s).

### ✅ Sprint 1.1 — Auth (DONE — Supabase live)
- SQLAlchemy 2 async models: Workspace / User / Pipeline / Stage
- JWT verifier supports legacy HS256 AND modern asymmetric ES256/RS256 via JWKS endpoint (10-min cache)
- Auto-bootstrap workspace + 11 B2B stages on first sign-in
- `@supabase/ssr` browser/server/middleware clients, root middleware protects authed routes, `/auth/callback` exchanges OAuth code for session, sign-in with Google + magic link
- `api-client` transparently attaches Bearer token from current Supabase session

### ✅ Sprint 1.2 — Core CRUD with B2B model (DONE — backend + frontend + import)
- Migration 0002: 5 new tables (leads, contacts, activities, followups, scoring_criteria); 11 B2B stages; gate_criteria_json
- Lead REST: CRUD + filters + Lead Pool + race-safe Sprint claim + transfer
- Stage transitions through `app/automation/stage_change.py` with gate engine (hard `check_pipeline_match` + soft `check_economic_buyer_for_stage_6_plus`)
- AppShell sidebar; pages /today, /pipeline, /leads-pool, /leads/[id]; Lead Card with 5 tabs; Pipeline drag-drop
- 216 leads imported from prototype data (131 v0.5 + 85 v0.6 foodmarkets)

### ✅ Sprint 1.3 — AI Enrichment (DONE — Phases A+B+C+D+E+F)
- LLMProvider Protocol + 4 providers (MiMo primary, Anthropic / Gemini / DeepSeek fallback chain)
- Sources: Brave + HH.ru + web_fetch with 24h Redis cache
- Migration 0003: `enrichment_runs` + Research Agent orchestrator
- AI Brief tab on Lead Card with hero band, fit_score badge, score_rationale, growth/risk signals, decision-maker hints, next-steps
- DrinkX `profile.yaml` injected into synthesis prompts; KB markdown library (segment-tagged playbooks + always-on objections / competitors / icp_definition)
- Cost guards: per-lead 1-running rate limit, workspace concurrency cap, daily budget cap (Redis counter)
- Synthesis prompt forbids jargon; MiMo strict-validates params (we keep payload to OpenAI-spec basics)

### ✅ Sprint 1.4 — Daily Plan + Follow-ups (DONE — Phases 1+2+3 + 4 hotfixes)
**First Celery service in the system.**

Backend:
- Migration 0004: `daily_plans`, `daily_plan_items`, `scheduled_jobs` (UNIQUE(user_id, plan_date) for upsert)
- Migration 0005: `followups.dispatched_at` for idempotency
- `priority_scorer.score_lead()` pure function with module-level tunable weights (overdue + due_soon + priority A/B/C + rotting + fit_score; archived/unassigned penalties)
- `DailyPlanService.generate_for_user()` — score → pack into work_hours → MiMo Flash 1-line hints (deterministic fallback) → time-block spread → upsert; budget guard reused from Sprint 1.3
- Celery `"drinkx"` app on Redis broker+backend, UTC clock, `task_time_limit=600s`
- Cron beat:
  - `daily-plan-generator` hourly at :00, picks workspaces where `user.timezone`-local hour == 08:00
  - `followup-reminder-dispatcher` every 15 min, creates `Activity(type='reminder')` for followups due in +24h, idempotent via `dispatched_at`
- Audit: `ScheduledJob` row per cron tick (status / affected_count / error)
- REST: `GET /api/me/today`, `GET /api/daily-plans/{date}`, `POST /api/daily-plans/{date}/regenerate` (202 + Celery), `POST /api/daily-plans/items/{id}/complete`

Frontend:
- `/today` rewritten with real plan rendering: states empty/generating(shimmer+2s poll)/failed/ready
- Time-block sections: Утро / День / После обеда / Вечер / Без времени
- Compact card design (~72px target via single primary row + sub-hint), URL-driven pagination 10/page (`?page=N`); "hot lead" 2px left rail when `priority_score >= 80`
- "🔄 Пересобрать план" button triggers Celery `regenerate_for_user`

Infra:
- `infra/production/docker-compose.yml`: api env extracted to `&api-env` YAML anchor; new `worker` (concurrency=2) and `beat` services share image + env
- `apps/web/Dockerfile`: bumped to `node:22-alpine` (corepack auto-upgraded to pnpm 11 which dropped Node 20)
- `apps/web/package.json`: pinned `packageManager: pnpm@10.18.0` + `onlyBuiltDependencies` allow-list (corepack reproducibility)

### ⏸ NOT YET BUILT
- **Sprint 1.5** — Polish + Launch (notifications drawer, email digest, audit log, mobile pass, Lead Card header polish, AI Brief copy fix, Pipeline sticky header, soft launch)
- **Phase 2** — Inbox (email + Telegram), Quote/КП builder, Knowledge Base UI, Apify, multi-pipeline switcher
- **Phase 3** — MCP server, Sales Coach chat, OCR визиток, pgvector

---

## Production blockers resolved during Sprint 1.4

Four hotfixes had to land **on top of** the Sprint 1.4 merge before everything was actually live. Documented in `SPRINT_1_4_DAILY_PLAN.md` for posterity:

1. `4dd4b7d` — Node 22 in `apps/web/Dockerfile` (pnpm 11 dropped Node 20)
2. `b720f5d` — `packageManager: pnpm@10.18.0` + `onlyBuiltDependencies` (corepack reproducibility + build-script allow-list)
3. `e5b8fe9` — Side-effect model imports in `app/scheduled/celery_app.py` (worker process doesn't import `app.main`, mapper registry was incomplete)
4. `8d2e644` — Per-task NullPool engine in Celery jobs (each `asyncio.run()` creates a new event loop; reusing the global asyncpg pool across loops crashed with "Future attached to a different loop")

---

## Open dependencies / production env state

User-provided keys in `/opt/drinkx-crm/infra/production/.env`:
- ✅ `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWT_SECRET`
- ✅ Google OAuth provider configured in Supabase
- ✅ `MIMO_API_KEY` (primary)
- ✅ `ANTHROPIC_API_KEY` (fallback — note: 403 from RU IP, never fires in practice)
- ✅ `BRAVE_API_KEY`
- ⚠ `GEMINI_API_KEY` — not configured
- ⚠ `DEEPSEEK_API_KEY` — not configured (intentional)
- ⏸ Sentry DSNs — empty (file logs + journalctl + ScheduledJob audit table for now)

---

## Known issues / risks

1. **Anthropic always 403 from RU IP** — fallback chain wastes one round-trip before falling through to Gemini/DeepSeek. Documented since Sprint 1.3.
2. **Stuck `DailyPlan` row** from the asyncpg loop bug (before `8d2e644` deployed). Manager's row may still be `status='generating'` until next regenerate replaces it. UI handles this correctly (polls every 2s); just needs another click on "Пересобрать план".
3. **`/today` plan generation not yet end-to-end-confirmed with screenshot** in the new (post-`8d2e644`) build. Worker + beat are healthy and logs show clean ticks; user-side verification pending.
4. **DST edge cases** — `daily_plan_generator` matches local 08:00 exactly. On DST days an hour skips or duplicates. Acceptable.
5. **No retry on per-user LLM failure** in the daily plan cron — that user gets no plan today, error is logged. Sprint 1.5 candidate.
6. **`fit_score` last-writer-wins** — orchestrator and the manual scoring tab both write the column. No conflict resolution. Documented since Sprint 1.3.

---

## Next
**Sprint 1.5 — Polish + Launch.** See `docs/brain/04_NEXT_SPRINT.md`.
