# DrinkX CRM — Current State

Last updated: 2026-05-08 (Sprint 2.0 ready for review; Sprint 1.5 + 2 post-merge hotfixes live)

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
drinkx-worker-1    Celery worker — concurrency=2
drinkx-beat-1      Celery beat — 4 cron entries (post-Sprint-2.0):
                     :00 hourly  → daily_plan_generator
                     :*/15       → followup_reminder_dispatcher
                     :30 hourly  → daily_email_digest (Sprint 1.5)
                     :*/5        → gmail_incremental_sync (Sprint 2.0)
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

### ✅ Sprint 1.5 — Polish + Launch (DONE — merged + live in production)
**8 groups + 2 post-merge hotfixes · merged `4261526` · current main HEAD `434428c`**

Backend:
- Migration `0006_notifications` — `notifications` table + 3 indexes; emit hooks in lead transfer / enrichment success+failure / daily plan ready / followup_due
- Migration `0007_audit_log` — append-only `audit_log` + admin-only `GET /audit`; emit hooks in lead.create / lead.transfer / lead.move_stage / enrichment.trigger
- `app/notifications/email_sender.py` + `digest.py` + `templates/daily_digest.html` — daily morning digest (top-5 plan items, top-5 overdue followups, top-5 yesterday's briefs); stub mode while `SMTP_HOST=""`
- New Celery task `daily_email_digest` + beat entry `crontab(minute=30)`
- 22 mock-only tests (10 notifications + 7 audit + 5 digest), 0 DB / 0 SMTP / 0 network

Frontend:
- AppShell: bell icon + drawer (30s polling) + admin-only "Журнал" link + mobile hamburger overlay
- `/audit` admin page — filter chips + table + pagination
- `/today`, `/leads/[id]`, `/pipeline` — mobile responsive pass (≥375px)
  - `/pipeline` mobile fallback: read-only `PipelineList` grouped by stage
  - `/leads/[id]` mobile: rail stacks above tab content, `<select>` tab switcher
- LeadCard header chips refactor — Stage / "Приоритет X" / Deal type / Score "X/100" / "AI X/10" with color bands; Won/Lost banner; functional Передать modal (UUID input, replaces toast stub); Won/Lost buttons disabled when terminal
- AIBriefTab empty state: "ICP" → "портретом идеального клиента"
- `useMe()` hook against `/auth/me` (frontend now knows backend role)
- `tsc --noEmit` clean; `next build` clean (10 routes, no new warnings)
- 0 new npm dependencies

See `docs/brain/sprint_reports/SPRINT_1_5_POLISH_LAUNCH.md` for the full report.

**Post-merge hotfixes** (committed direct to main after sprint close):
- `9a580cd` `fix(nginx): increase proxy_buffer_size for Supabase 2.x cookie stack` — `/auth/callback` was returning 502 because Supabase JS 2.x cookie chunks (sb-access-token + sb-refresh-token + chunked PKCE auth-token) overflowed the 8K default `proxy_buffer_size`. Bumped to 16k / 32k. Applied manually on VPS first, then mirrored into `infra/production/nginx/crm.drinkx.tech.conf`.
- `434428c` `fix(web): make sidebar logo clickable, links to /today` — desktop sidebar logo was a `<span>`; now wraps in `<Link href="/today">` matching the mobile top-bar pattern.

**Production state at session close:**
- All 6 containers up, api healthy
- Migrations `0006_notifications` + `0007_audit_log` applied
- Beat firing 3 cron entries (daily_plan_generator @ :00 hourly, followup_reminder_dispatcher @ */15, daily_email_digest @ :30 hourly)
- Worker registered all 4 tasks (3 cron + `regenerate_for_user` manual)
- Sign-in flow verified working end-to-end
- Logo home-link verified working

### ✅ Sprint 2.0 — Gmail Inbox sync (READY FOR REVIEW — branch `sprint/2.0-gmail-inbox`, NOT yet merged)
**7 groups, commit range `8745394..ba9c85a` + this G7 commit**

Backend:
- Migration `0008_channel_connections` — workspace+user FKs, channel_type, credentials_json (TEXT plaintext for v1, encryption TODO 2.1), status, extra_json (cursor + audit), last_sync_at + 2 indexes
- Migration `0009_inbox_items_and_activity_email` — `inbox_items` table (workspace+user FKs, gmail_message_id UNIQUE, suggestion JSON, partial-unique on activities.gmail_message_id) + activities adds gmail_message_id / gmail_raw_json / from_identifier / to_identifier + subject widened 300→500
- New `app/inbox/` package: `gmail_client` (async wrapper, auto-refresh, fail-soft), `oauth` (HMAC-signed state, exchange flow), `email_parser` (stdlib-only Gmail-payload walker), `matcher` (contact 1.0 → lead 0.95 → unique-domain 0.7, generic-mailbox skip), `processor` (parse → dedup → match → store, rolls back on any failure), `sync` (history + incremental cores), `services` (list/count/confirm/dismiss with audit hooks), `routers` (REST), `schemas`, `models` (ChannelConnection + InboxItem)
- New Celery tasks: `gmail_history_sync(user_id)` (one-shot 6-month backfill, 2000-msg cap), `gmail_incremental_sync` (every-5-min via Gmail History API), `generate_inbox_suggestion(item_id)` (MiMo Flash via TaskType.prefilter, fail-soft)
- Beat: 4th cron `gmail-incremental-sync */5` (configurable via `GMAIL_SYNC_INTERVAL_MINUTES`)
- AI Brief synthesis injects last 10 email Activities as `### Переписка с клиентом` system-prompt section (cap 2000 chars, body preview 200 chars per email)
- Email-context invariant: ADR-019 — `Activity.user_id` is audit trail, not visibility filter

Frontend:
- New `/inbox` page: pending list with AI suggestion chips (create_lead green / add_contact blue / match_lead gray) or `AI анализирует…` spinner; action buttons (Создать карточку modal, Привязать к лиду dropdown, Игнор optimistic hide); pagination 20/page; empty state with `Подключить Gmail` CTA
- AppShell: `Входящие` promoted out of disabled list with red-dot pending badge (30s poll, 99+ cap), same style as the bell
- Lead Card Activity Feed: new `EmailActivityItem` branch — direction icon ← / →, sender, bold subject, 200-char body preview with `Показать полностью` toggle
- 5 new hooks in `lib/hooks/use-inbox.ts`: useInboxCount, useInboxPending, useConfirmItem, useDismissItem, useConnectGmail

Tests:
- 18 mock-only Sprint 2.0 tests across `test_inbox_matcher.py` (9), `test_email_context_in_brief.py` (3), `test_inbox_services.py` (6). Combined with Sprint 1.5 baseline: 30 mock tests passing, 0 DB, 0 network.
- `pnpm typecheck` + `pnpm build` clean throughout the sprint

Architecture decisions:
- ADR-019 — Email ownership model lead-scoped, not manager-scoped
- Variant 1 ownership = per-user channels in v1 (workspace-level allowed by schema for v2 drop-in)
- Gmail History API (polling), not Push/Pub-Sub
- Auto-attach threshold 0.8; below → human review via inbox_items
- 18-entry hardcoded `_GENERIC_DOMAINS` skip-set
- Raw payload kept inline if < 50KB, dropped otherwise

Known issues / risks (full list in `SPRINT_2_0_GMAIL_INBOX.md`):
1. `credentials_json` stored as plaintext — TODO 2.1 (Fernet/KMS)
2. 2000-message history-sync cap — TODO if a workspace exceeds it
3. `generate_inbox_suggestion` not yet bench-tested with real MiMo
4. `_GENERIC_DOMAINS` hardcoded — TODO promote to per-workspace setting
5. `pnpm-lock.yaml` generated by G4 `pnpm install` not committed (housekeeping)
6. Migrations 0008 + 0009 NOT YET applied on production — first deploy step
7. `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` not yet in production `.env`

### ⏸ NOT YET BUILT
- **Phase 2** — Bulk Import/Export (Sprint 2.1 NEXT), Telegram Business inbox + email send (2.1+), Quote/КП builder, WebForms, Knowledge Base CRUD UI, Apify, multi-pipeline switcher
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
2. **DST edge cases** — `daily_plan_generator` and `daily_email_digest` both match `local hour == 8`. On DST days an hour skips or duplicates. Acceptable.
3. **No retry on per-user LLM failure** in the daily plan cron — that user gets no plan today, error is logged.
4. **`fit_score` last-writer-wins** — orchestrator and the manual scoring tab both write the column. No conflict resolution. Documented since Sprint 1.3.
5. **Tab content overflow on mobile, not exhaustively audited** (Sprint 1.5 group 6) — DealTab / ScoringTab / AIBriefTab / etc. weren't reviewed for hard-coded grids or wide tables at 375px. Point-fix with `overflow-x-auto` on observation.
6. **TransferModal UUID input** (Sprint 1.5 group 7) — no `/api/users` listing endpoint yet, so the manager pastes the recipient's UUID. Backend validates membership and surfaces 400 inline. Replace with a picker once the endpoint lands.
7. **Email digest stub mode not yet verified in production** (Sprint 1.5 group 5) — `SMTP_HOST=""` keeps the digest in stub mode (`[EMAIL STUB]` lines in worker logs). Smoke-test on the morning after deploy.
8. **Soft-launch checklist partially open** — see `SPRINT_1_5_POLISH_LAUNCH.md` for the row-by-row state. Sentry DSNs, pg_dump backups, onboarding doc, end-to-end smoke, and log-volume review are all still ⏸.

Resolved this sprint:
- ~~Stuck `DailyPlan` row from the asyncpg loop bug~~ — flipped to `failed` mid-sprint via the production debugging session; `regenerate_for_user` end-to-end confirmed working (24 items, 27s).

---

## Next
**Phase 2 Sprint 2.1 — Bulk Import / Export.** See `docs/brain/04_NEXT_SPRINT.md`.
