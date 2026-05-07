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

## 🔜 NEXT

### Phase 1 — MVP continuation (~1-2 weeks remaining)

**Sprint 1.5 — Polish + Launch (1 week)** ← READY TO START
See `docs/brain/04_NEXT_SPRINT.md` for full scope.

In-app polish:
- In-app notifications drawer
- Email digest (daily morning summary)
- Audit log (who changed what, when) + admin view
- Mobile responsive pass on /today, Lead Card, /pipeline (touch drag-drop)
- Lead Card header polish (score + transfer/won/lost buttons)
- AI Brief empty-state copy fix (ICP → "портрет идеального клиента")
- Pipeline sticky header (extra defense against horizontal scroll)
- Soft launch for DrinkX team

Outstanding deferred work that may bundle into 1.5 if there's time:
- **Phase G (Sprint 1.3 follow-on)** — move enrichment off FastAPI BackgroundTasks onto Celery (Celery infra now exists from Sprint 1.4); WebSocket `/ws/{user_id}` to replace the 2s polling
- DST-aware `daily_plan_generator` edge handling

## 📅 LATER

### Phase 2 (~6 weeks)
Inbox (Email IMAP/SMTP + Telegram Business webhook), Quote/КП builder,
WebForms, Bulk Import/Export, Knowledge Base CRUD UI, Apify integration,
push notifications + Telegram bot, multi-pipeline switcher,
full Settings panel.

### Phase 3 (~4 weeks)
MCP server, AI Sales Coach full chat, Visit-card OCR parser,
Vector DB (pgvector) for similar-deals retrieval, Stalled-deal detector,
Pipeline column virtualization (>1000 cards), Apify lead-gen wizard.
