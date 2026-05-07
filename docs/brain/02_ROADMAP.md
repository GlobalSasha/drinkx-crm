# DrinkX CRM — Roadmap

## ✅ DONE

### Phase 0 — UX/UI Design & Prototyping (in `crm-prototype` repo)
- HTML prototypes: index.html, index-soft-full.html, index-soft.html
- B2B reference: index-b2b.html (11-stage pipeline, gates, scoring 0-100, multi-stakeholder, deal type, A/B/C/D, dual-rotting, pilot contract)
- data.js: 131 real DrinkX clients
- v0.6 foodmarkets-audit: +85 candidates
- PRD v2.0 + addition v2.1 (Lead Pool & Sprint System)
- Design system: taste-soft (Plus Jakarta Sans + double-bezel + squircle)

### Phase 1 — Foundation + Auth + AI (in `drinkx-crm` repo)

**Sprint 1.0 — DONE** · `SPRINT_1_0_FOUNDATION.md`
- Monorepo, bare-metal Docker stack on crm.drinkx.tech, GitHub Actions auto-deploy

**Sprint 1.1 — DONE** · `SPRINT_1_1_AUTH.md` + Sprint 1.1.3 follow-on
- Workspace/User/Pipeline/Stage models; alembic 0001
- JWT verifier supports HS256 + ES256/RS256 via JWKS
- Real Supabase + Google OAuth + magic link via `@supabase/ssr`

**Sprint 1.2 — DONE** · `SPRINT_1_2_BACKEND_MERGE.md` + frontend follow-on
- Migration 0002: 5 new tables (leads, contacts, activities, followups, scoring_criteria), 11 B2B stages
- Lead REST + Pool + Sprint claim + transfer; stage transitions with gate engine
- AppShell + /today + /pipeline (drag-drop) + /leads-pool + /leads/[id] (5 tabs)
- 216 leads imported from prototype data

**Sprint 1.3 — DONE** · `SPRINT_1_3_AI_ENRICHMENT.md`
- LLM Provider abstraction: MiMo (primary) + Anthropic + Gemini + DeepSeek with fallback chain
- Sources: Brave + HH.ru + web_fetch with 24h Redis cache
- Migration 0003: `enrichment_runs`; Research Agent orchestrator
- AI Brief tab with hero band, fit_score, score_rationale, signals, decision-makers, next-steps
- DrinkX `profile.yaml` + KB markdown library (segment-tagged playbooks + always-on objections / competitors / icp_definition)
- Cost guards: per-lead rate limit, workspace concurrency cap, daily budget cap

**Sprint 1.4 — DONE** · `SPRINT_1_4_DAILY_PLAN.md`
- **First Celery service in the system** — worker + beat live in production
- Migration 0004: daily_plans, daily_plan_items, scheduled_jobs (UNIQUE on (user_id, plan_date) for upsert)
- Migration 0005: followups.dispatched_at for idempotency
- `priority_scorer.score_lead()` pure function with tunable weights
- `DailyPlanService.generate_for_user()` — score → pack into work_hours → MiMo Flash hints → time-block spread
- Cron beat: `daily_plan_generator` hourly with timezone-local 08:00 filter; `followup_reminder_dispatcher` every 15 min, idempotent
- REST: `/me/today`, regenerate, complete-item; manual UI trigger via Celery `regenerate_for_user`
- Frontend `/today` rewritten with real plan rendering — compact cards (~72px), URL-driven pagination 10/page, time-block sections, hot-lead left rail
- Infra hotfixes (4): Node 22 bump, pnpm pin, Celery mapper-registry, per-task NullPool engine

**Sprint 1.5 — DONE** · `SPRINT_1_5_POLISH_LAUNCH.md` · branch `sprint/1.5-polish-launch` (range `f3e0509..HEAD`, 8 groups)
- Migration 0006: `notifications` (workspace/user FK, kind/title/body, optional lead_id, read_at)
- Migration 0007: `audit_log` (workspace/user FK, action/entity_type/entity_id/delta_json) + admin-only `GET /audit`
- `app/notifications` domain — `notify` / `safe_notify` / mark-read / mark-all-read; bell badge + drawer with 30s polling
- `app/audit` domain — `audit.log()` defensive helper + 4 emit hooks (lead.create, lead.transfer, lead.move_stage, enrichment.trigger); admin-only `/audit` page
- `app/notifications/email_sender.py` + `digest.py` + `templates/daily_digest.html` — daily morning email digest (top-5 plan items / top-5 overdue / top-5 yesterday's briefs); SMTP via aiosmtplib with stub mode while SMTP_HOST=""
- Beat: new entry `daily-email-digest` `crontab(minute=30)` (combined with local-hour=8 filter → fires at 08:30 local time)
- Frontend mobile pass — AppShell hamburger overlay, /today flex-wrap + 44px tap-targets, /leads/[id] stacked rail + select tab switcher, /pipeline list-view fallback below md
- LeadCard header polish — Stage / Priority / Deal type / Score "X/100" / "AI X/10" chips with band colors; Won/Lost banner; functional TransferModal (UUID input)
- AIBriefTab empty-state: "ICP" → "портретом идеального клиента"
- 22 mock-only backend tests, 0 DB / 0 SMTP / 0 network; tsc + next build clean throughout
- 0 new npm dependencies; 1 new Python dep (aiosmtplib)

## 🔜 NEXT

### Phase 2 — Sprint 2.0 — Inbox + Quote + Forms + Bulk Import (~2 weeks)
See `docs/brain/04_NEXT_SPRINT.md` for full scope.

Surface area:
- **Inbox** — Email (IMAP read / SMTP send) + Telegram Business webhook → unified per-lead conversation view
- **Quote / КП builder** — line-items, pricing, render to PDF, attach to lead activity
- **WebForms** — public form builder + capture endpoint → leads pool with attribution
- **Bulk Import / Export** — CSV/XLSX import with column mapping + dry-run preview; export of any list view
- **Knowledge Base CRUD UI** — file-based markdown library from Sprint 1.3 promoted to a real UI

Outstanding deferred work that may bundle into 2.0 or 2.1:
- **Phase G (Sprint 1.3 follow-on)** — move enrichment off FastAPI BackgroundTasks onto Celery (infra exists from Sprint 1.4); WebSocket `/ws/{user_id}` to replace 2s polling
- DST-aware cron edge handling
- pg_dump cron + Sentry DSNs (soft-launch checklist carryover from 1.5)

## 📅 LATER

### Phase 2 — Sprint 2.1+ (~4 weeks)
Apify integration (foodmarkets / horeca scrapers), push notifications +
Telegram bot for managers, multi-pipeline switcher, full Settings panel,
team workspace management.

### Phase 3 (~4 weeks)
MCP server, AI Sales Coach full chat, Visit-card OCR parser,
Vector DB (pgvector) for similar-deals retrieval, Stalled-deal detector,
Pipeline column virtualization (>1000 cards), Apify lead-gen wizard.
