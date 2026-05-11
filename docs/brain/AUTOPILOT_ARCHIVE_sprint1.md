# AUTOPILOT.md — sequential roadmap for DrinkX Smart AI CRM

> **For any Claude session:** Read CLAUDE.md first. Then come here. Find the first
> `- [ ]` under the active sprint, do that one item, tick the box, commit, repeat.
> One item = one commit. If blocked, write `> [BLOCKED]` under it.

Conventions: `- [x]` done · `- [ ]` todo · `- [-]` skipped (with reason) ·
`- [⚠]` partial / needs follow-up

Last updated: 2026-05-06 — Sprint 1.2.1 complete (schema migration 0002_b2b_model).

---

## Sprint 1.0 — Foundation (target: 1 week)

Goal: empty but deployable monorepo with Next.js frontend, FastAPI backend,
PostgreSQL via Supabase, Redis via Upstash, and CI to Vercel + Railway.

### 1.0.1 Repo skeleton
- [x] `git init` + initial directory layout
- [x] CLAUDE.md
- [x] AUTOPILOT.md (this file)
- [x] root `.gitignore`
- [x] root `README.md` with one-paragraph intro and links to prototype + PRD
- [x] `pnpm-workspace.yaml` for `apps/*` and `packages/*`
- [x] `package.json` at root with shared scripts (`dev`, `build`, `lint`, `format`)

### 1.0.2 Web app skeleton (apps/web)
- [x] `apps/web/package.json` with Next.js 15, React 19, TypeScript, Tailwind, shadcn/ui
- [x] `apps/web/tsconfig.json` (strict)
- [x] `apps/web/next.config.mjs`
- [x] `apps/web/tailwind.config.ts` with taste-soft tokens (silver canvas, deep sage, etc — see prototype CSS)
- [x] `apps/web/app/layout.tsx` (root layout, font imports, providers)
- [x] `apps/web/app/page.tsx` (placeholder homepage that links to /today, /pipeline)
- [x] `apps/web/app/today/page.tsx` (placeholder)
- [x] `apps/web/app/pipeline/page.tsx` (placeholder)
- [x] `apps/web/lib/api-client.ts` (typed fetch wrapper with auth header)
- [x] `apps/web/.env.local.example` (NEXT_PUBLIC_API_URL, SUPABASE_URL, ...)

### 1.0.3 API skeleton (apps/api)
- [x] `apps/api/pyproject.toml` (uv-managed, Python 3.12+)
- [x] `apps/api/app/main.py` — FastAPI app factory with /health, /version
- [x] `apps/api/app/config.py` — Pydantic Settings (env vars)
- [x] `apps/api/app/db.py` — SQLAlchemy 2.0 async engine + session
- [x] `apps/api/app/auth/` package (empty modules: models, schemas, repositories, services, routers, events)
- [x] `apps/api/app/leads/` package (empty modules)
- [x] `apps/api/app/common/` (base model class with id, timestamps; pagination helpers)
- [x] `apps/api/.env.example`
- [x] `apps/api/Dockerfile`

### 1.0.4 GitHub repo and remote
- [x] Create public GitHub repo `GlobalSasha/drinkx-crm`
- [x] Push initial commit
- [ ] Add branch protection on `main` (require PR review, status checks)

### 1.0.5 Local dev environment
- [x] `infra/docker/docker-compose.yml` — local Postgres 16 + Redis 7 + Mailhog
- [x] Root `Makefile` with `make dev`, `make api`, `make web`, `make db.up`, `make db.migrate`
- [-] Local verification — skipped, verified directly on production server (deploy.sh + /health → 200)

### 1.0.5b Production server (NEW — added on 2026-05-05)
Bare-metal Ubuntu 22.04 at `77.105.168.227` / `crm.drinkx.tech`. Provisioned in one session:
- [x] Apt update, 2GB swap, UFW (22/80/443), fail2ban
- [x] Docker 29.4, Compose v5.1.3
- [x] nginx 1.18 + certbot 1.21, Let's Encrypt cert for crm.drinkx.tech (auto-renews)
- [x] `deploy` user with docker group; SSH key for GitHub Actions
- [x] `/opt/drinkx-crm` cloned from main; `infra/production/.env` with autogen Postgres password
- [x] Full stack running: drinkx-{postgres, redis, api, web} all healthy, all bound 127.0.0.1
- [x] nginx reverse-proxy: `/` → web:3000, `/api/*` → api:8000, `/ws/*` → api:8000 WebSocket
- [x] HSTS + security headers
- [x] `infra/production/deploy.sh` (pull + rebuild + health check)

### 1.0.6 CI / CD
- [x] `.github/workflows/deploy.yml` — SSH to crm.drinkx.tech on push to main, runs deploy.sh, verifies /health
- [-] Vercel/Railway — skipped, deployed to bare-metal server (77.105.168.227 / crm.drinkx.tech)
- [ ] `.github/workflows/web.yml` — lint + typecheck + build on PR
- [ ] `.github/workflows/api.yml` — ruff + mypy + pytest on PR

### 1.0.7 Observability
- [ ] Sentry projects for web and api; DSNs in env
- [ ] Structured JSON logging in api (loguru or structlog)
- [ ] Liveness `/health` + readiness `/ready` endpoints

---

## Sprint 1.1 — Auth + Onboarding (1 week)

Goal: a real human can sign in with Google, get a workspace, complete the 4-step
onboarding flow, and land on an empty `/today`.

### 1.1.1 Supabase setup
- [ ] Create Supabase project; copy URL + anon key + service role key into envs
- [ ] Enable Google OAuth provider; configure redirect URLs for local + production
- [ ] Enable email auth as fallback (magic link)
- [ ] Configure Row Level Security default-deny

### 1.1.2 DB schema — Sprint 1 entities
- [x] Alembic init + first migration (`0001_initial`)
- [x] `workspaces` table (with `sprint_capacity_per_week` from PRD-addition v2.1)
- [x] `users` table with `working_hours_json`, `max_active_deals`, `onboarding_completed`, `supabase_user_id`, `specialization`, `timezone`
- [x] `pipelines` table
- [x] `stages` table (with `is_won`, `is_lost`, `probability`, `rot_days`, `color`)
- [x] Seed: default pipeline "Новые клиенты" with 7 stages on workspace creation (services.upsert_user_from_token)

### 1.1.3 Web — auth flow
- [x] `apps/web/middleware.ts` — redirect unauthed users to `/sign-in`
- [x] `apps/web/app/sign-in/page.tsx` (Google button + magic link)
- [x] Session hook + provider (Supabase browser/server/middleware clients in lib/supabase/; api-client auto-attaches Bearer; AppShell shows real user + sign-out)
- [ ] `apps/web/app/onboarding/...` — 4 steps from prototype (deferred — own task):
  - [ ] Step 1: Welcome (after OAuth)
  - [ ] Step 2: profile + role + spec chips + schedule grid + timezone + max_active_deals
  - [ ] Step 3: channels (defer Telegram to Phase 2; Gmail OAuth scope here)
  - [ ] Step 4: done + 4 CTAs
> AUTOPILOT: 1.1.3 ✓ (middleware, sign-in page, session hook, onboarding deferred) — built by Claude Sonnet 4.6 on 2026-05-06

### 1.1.4 API — auth endpoints
- [x] `apps/api/app/auth/jwt.py` — TokenClaims + Supabase JWT verifier (HS256) with stub-mode fallback when SUPABASE_JWT_SECRET is empty
- [x] `apps/api/app/auth/dependencies.py` — `current_user` and `require_admin` deps
- [x] `apps/api/app/auth/services.py` — `upsert_user_from_token` (auto-bootstrap workspace + 7 stages on first sign-in)
- [x] `apps/api/app/auth/schemas.py` — `UserOut`, `WorkspaceOut`, `UserUpdateIn`
- [x] `apps/api/app/auth/routers.py`:
  - [x] `GET /auth/me` — current user with workspace
  - [x] `PATCH /auth/me` — update profile (name, role, spec, working_hours, mark_onboarding_complete)
  - [-] `POST /auth/exchange` — not needed; Supabase JWT used directly via `Authorization: Bearer`
- [x] Workspace bootstrap on first sign-in: creates Workspace + default Pipeline + 7 Stages + makes user admin

### 1.1.5 Tests
- [ ] api: pytest fixture for authed client
- [ ] api: test workspace creation + user upsert flow
- [ ] web: e2e (Playwright) "sign in → finish onboarding → land on /today"

---

## Sprint 1.2 — Core CRUD + Lead Pool (2 weeks)

Goal: real pipeline with real leads, real drag-drop, real lead card.
**+ Lead Pool & Weekly Sprint System** (per PRD-addition-v2.1-lead-pool.md).
No AI yet.

### 1.2.1 DB schema — leads layer
- [x] `leads` table (B2B model per ADR-016) — base columns + B2B fields
- [x] **Lead Pool fields:** `assignment_status` ENUM('pool', 'assigned', 'transferred'),
  `assigned_to` (nullable), `assigned_at`, `transferred_from`, `transferred_at`
- [x] `contacts` table (unified ЛПР, with `verified_status`)
- [x] `activities` table (polymorphic per `type`)
- [x] `followups` table
- [x] `scoring_criteria` table per-workspace (ADR-017); `workspaces.sprint_capacity_per_week` already in 0001
- [x] Indexes: `(workspace_id, stage_id)`, `(assigned_to)`,
  `(workspace_id, assignment_status)`, `(is_rotting_stage, is_rotting_next_step)`, GIN full-text on `company_name`

### 1.2.2 API — leads + pipelines
- [x] `app/leads/`: schemas, repository, service, router with `GET/POST/PATCH/DELETE /leads`,
  `GET /leads?stage_id=&assigned_to=&segment=&city=&priority=&deal_type=&q=&page=`
- [x] **Lead Pool endpoints:**
  - [x] `GET /leads/pool?city=&segment=&fit_min=&page=` (only `assignment_status=pool`)
  - [x] `POST /leads/sprint` body: `{cities, segment?, limit}` → returns assigned leads
        Implementation: SELECT N from pool ordered by fit_score DESC NULLS LAST → created_at ASC
        with `FOR UPDATE SKIP LOCKED`, then per-row atomic UPDATE WHERE assignment_status='pool'
  - [x] `POST /leads/{id}/claim` (single manual take from pool)
  - [x] `POST /leads/{id}/transfer` body: `{to_user_id, comment?}`
- [ ] `app/pipelines/`: list + reorder stages
- [x] `app/contacts/`: per-lead nested CRUD
- [x] `app/activities/`: feed endpoints (cursor pagination, composer, complete-task)
- [x] `app/followups/`: list/create/edit/complete; auto-seed on lead create (3 defaults)
- [ ] WebSocket connection at `/ws/{user_id}` (Redis pub/sub)
- [x] Stage change goes through `app/automation/stage_change.py`
- [ ] Notifications: `lead_transferred` event → dispatcher → notify new manager

### 1.2.3 Web — Pipeline screen
- [x] `apps/web/app/pipeline/page.tsx` with TanStack Query hooks
- [x] Filter row: segment chips + city chips + search input (port from prototype)
- [x] Drag-drop with @dnd-kit, optimistic update + rollback on error
- [x] Page-level scroll + per-column scroll (port CSS pattern)
- [-] Won-confirmation modal with detail capture — skipped (Task 6 scope)
- [x] AI Brief drawer on click (port from prototype) — for now reads `lead.ai_data` JSON
- [x] **«Сформировать план на неделю»** button in Pipeline header
- [x] **SprintModal** component (city multi-select + segment + preview N + create)
- [x] **Empty state** for new manager (empty columns show dashed drop zone)
- [-] **TransferModal** in LeadCard menu (⋯ → «Передать менеджеру») — skipped (Task 6 scope)
> AUTOPILOT: 1.2.3 ✓ — built by Claude Sonnet 4.6 on 2026-05-05

### 1.2.3.b Web — Lead Pool page (new sidebar section)
- [x] `apps/web/app/(app)/leads-pool/page.tsx` — table view: компания, город, сегмент, tier, fit_score, статус
- [x] Filters: city, segment, fit_min slider, search by company name
- [x] «Взять в работу» button per row (optimistic UI + race-safe, 409 toast)
- [x] Sidebar nav via AppShell: База лидов, Pipeline, Сегодня (active states)
- [x] `useClaimLead()` hook: POST /leads/{id}/claim, optimistic pool cache remove
- [-] Manager/admin role separation — skipped (no auth yet, Phase 2)
> AUTOPILOT: 1.2.3.b ✓ — built by Claude Sonnet 4.6 on 2026-05-06

### 1.2.4 Web — Today screen
- [x] `apps/web/app/(app)/today/page.tsx` — loads all leads, groups by next_action_at
- [x] Empty state with «Сформировать план →» CTA → opens SprintModal (standalone mode)
- [x] Grouped sections: Сегодня / Завтра / Эта неделя / Без срока
- [x] Filter chips: priority A/B/C/D + search box
- [x] Row click → router.push(`/leads/${id}`)
- [x] `useTodayLeads()` hook: sorts by next_action_at ASC, priority, created_at DESC
- [-] `daily_plans` table integration — skipped (Sprint 1.4, uses live leads for now)
> AUTOPILOT: 1.2.4 ✓ — built by Claude Sonnet 4.6 on 2026-05-06

### 1.2.5 Web — Lead Card
- [x] `apps/web/app/leads/[id]/page.tsx`
- [x] Tabs: Сделка / Контакты / Scoring / Активность / Pilot (conditional stage>=8)
- [x] Left column: follow-ups rail + KB stub
- [x] Activity feed with composer (4 modes: comment/task/reminder/file) + cursor pagination
- [x] DealTab: deal_type, priority, score slider, blocker, next_step (debounced PATCH)
- [x] ContactsTab: 4 role buckets, CRUD, ADR-012 banner
- [x] ScoringTab: 8-slider rollup → score → tier badge
- [x] PilotTab: pilot_contract_json fields (ADR-011)
- [x] GateModal: gate_criteria checklist, force-move, 409 violations
- [x] New hooks: useLead, useUpdateLead, useContacts (CRUD), useActivities (infinite), useCreateActivity, useCompleteTask, useFollowups (CRUD + complete)
- [x] BriefDrawer: 'Открыть полностью →' now uses Next.js Link
> AUTOPILOT: 1.2.5 ✓ — built by Claude Sonnet 4.6 on 2026-05-06

### 1.2.6 Migration script
- [x] `apps/api/scripts/import_prototype_data.py` — one-shot loader that reads the
  prototype's `data.js` file, parses it, and inserts a starter dataset for testing
> AUTOPILOT: 1.2.6 ✓ — built by Claude Sonnet 4.6 on 2026-05-06

### 1.2.7 Tests
- [ ] api: lead CRUD coverage
- [ ] api: stage change hook
- [ ] api: contact CRUD with verified_status
- [ ] web: e2e "create lead → drag to next stage → add comment → mark task done"

---

## Sprint 1.3 — AI Enrichment (2 weeks)

Goal: a new lead's AI Brief actually gets filled by real research over real sources.

### 1.3.1 Provider abstraction
- [x] `app/enrichment/providers/base.py` — `LLMProvider` Protocol, `TaskType` enum, Flash/Pro split
- [x] `MiMoProvider`, `AnthropicProvider`, `GeminiProvider`, `DeepSeekProvider` implementations (httpx, no SDKs)
- [x] `get_llm_provider()` factory + `complete_with_fallback()` with structured logging
- [x] `ResearchOutput` Pydantic schema with fallback defaults everywhere (PRD §7.2)
- [x] 15 tests via `_FakeAsyncClient` — no real network calls
> AUTOPILOT: 1.3.1 ✓ — built by Claude Sonnet 4.6 on 2026-05-06

### 1.3.2 Sources
- [x] `app/enrichment/sources/brave.py` with 24h Redis cache by query hash
- [x] `app/enrichment/sources/hh.py` (HH.ru public API)
- [x] `app/enrichment/sources/web_fetch.py` (httpx with timeout + size cap)
- [x] Per-source 15s timeout, fail-soft

> AUTOPILOT: 1.3.2 ✓ (web_fetch + brave + hh) — built by Claude Sonnet 4.6 on 2026-05-06

### 1.3.3 Research Agent
- [x] `app/enrichment/orchestrator.py` — query builder → parallel fetch →
  synthesis via complete_with_fallback(research_synthesis) → save to lead.ai_data
- [x] `enrichment_runs` table (migration 0003) + ORM model + service layer with cost tracking (cost_tokens, cost_usd, duration_ms)
- [x] Output via Pydantic `ResearchOutput` with fallback defaults
- [x] Router: POST /leads/{id}/enrichment (202), GET /latest, GET list — BackgroundTasks
- [-] Celery task — deferred to Phase E
- [-] WebSocket progress events — deferred to Phase E

> AUTOPILOT: 1.3.3 ✓ (orchestrator + DB persistence; Celery + WS deferred to 1.3.E) — built by Claude Sonnet 4.6 on 2026-05-06

### 1.3.4 Knowledge Base + business profile
- [x] `knowledge/drinkx/*.md` initial files (playbook_horeca, playbook_retail, playbook_retail_discount, playbook_qsr, objections_common, competitors, icp_definition) — Phase F
- [x] `config/drinkx_profile.yaml` populated with real DrinkX info (product, ICP, fit_score anchors, objections, signals)
- [x] `profile.py` — `load_profile()` lru_cache + `render_profile_for_prompt()` prepended to synthesis system prompt
- [x] Loader (lru_cache in-process, not Redis): `app/enrichment/kb.py` — `load_kb()`, `select_for_segment()`, `render_kb_for_prompt()` — Phase F
- [x] Tag matcher selects relevant files for the synthesis prompt by `lead.segment` — Phase F

### 1.3.5 Cost control
- [ ] Quality pre-filter (regex stop-list + mini-LLM go/no-go)
- [x] Rate limit: max 1 in-flight enrichment per lead (409 if already running) — Phase E
- [x] Rate limit: max 5 parallel jobs / workspace — `concurrency.py` + `is_at_concurrency_limit()` → 429
- [x] Daily budget guard — `budget.py`, Redis key `ai_budget:{workspace_id}:{YYYY-MM-DD}`, cap = monthly/30; `has_budget_remaining()` guard before trigger; `add_to_daily_spend()` on every succeeded run → 429
> AUTOPILOT: 1.3.4 (profile) + 1.3.5 (cost guards: budget + concurrency) ✓ — built by Claude Sonnet 4.6 on 2026-05-06
> AUTOPILOT: 1.3.4 (KB) ✓ (Phase F — KB files + lru_cache loader + segment tag matcher + score_rationale) — built by Claude Sonnet 4.6 on 2026-05-07

### 1.3.6 Web — enrichment UI
- [x] AI Brief tab in LeadCard (between Сделка and Контакты) — Phase E
- [x] "Запустить enrichment" / "Обновить" trigger button — Phase E
- [x] Polling every 2s while status=running (TanStack refetchInterval) — Phase E
- [x] Running skeleton + elapsed timer — Phase E
- [x] Failed banner with "Попробовать снова" — Phase E
- [x] Empty state CTA — Phase E
- [x] ResultBody: profile, scale/geo/formats, growth/risk chips, fit_score badge, urgency, DM hints, next_steps, sources — Phase E
- [x] 409 → toast "Enrichment уже запущен" + refetch — Phase E
- [x] BriefDrawer: "Запустить enrichment" affordance when ai_data empty — Phase E
- [ ] Lead create → POST returns lead with `enrichment_run_id`
- [ ] Subscribe to progress via WebSocket → render the source list with checkmarks
- [ ] On done → reload AI Brief panel

### 1.3.7 Tests
- [ ] api: vcr-style fixtures for Brave/HH responses
- [ ] api: orchestrator handles single-source failures
- [ ] api: cache hit on repeated company_name within 24h

---

## Sprint 1.4 — Daily Plan + Follow-ups (1 week)

Goal: every morning every user gets a personalized prioritized plan; follow-up
reminders auto-generate tasks.

### 1.4.0 Schema + scorer + generator (Phase 1)
- [x] Migration `0004_daily_plan`: `daily_plans`, `daily_plan_items`, `scheduled_jobs`
- [x] ORM models `DailyPlan`, `DailyPlanItem`, `ScheduledJob` registered in alembic env.py
- [x] `priority_scorer.score_lead()`: stage.probability + time/priority/rotting/fit weights, penalties for terminal/unassigned
- [x] `daily_plan/services.generate_for_user()`: score→pack→hint(LLM/fallback)→time_block→upsert
- [x] 14 priority scorer unit tests + 11 service tests (all passing)
> AUTOPILOT: 1.4.0 ✓ (Phase 1 — schema + ORM + scorer + generator; Celery/REST/frontend Phase 2/3) — built by Claude Sonnet 4.6 on 2026-05-07

### 1.4.1 Celery beat
- [ ] `app/scheduled/jobs.py` — central registry
- [ ] `daily_plan_generator` runs at 08:00 in each workspace's timezone
- [ ] `followup_reminder_dispatcher` runs every 15 minutes

### 1.4.2 Daily plan generator
- [x] REST endpoints: GET /me/today, GET /daily-plans/{date}, POST /daily-plans/{date}/regenerate (202), POST /daily-plans/items/{id}/complete
- [x] Web: Today page reads from daily_plans (replaces live-lead grouping)
- [x] regenerate_for_user Celery task (no 08:00 gate, manual trigger)
- [x] 7 route tests (AsyncMock + mocked Celery send_task)
> AUTOPILOT: 1.4.2 (REST) + 1.4.3 (frontend Today) ✓ — built by Claude Sonnet 4.6 on 2026-05-07

### 1.4.3 Follow-up reminders
- [ ] Cron iterates `followups` with `due_at <= now() + 24h`
- [ ] Creates `activities` entries (type=task or type=reminder) and notifications
- [ ] If `reminder_kind = auto_email` — generates a draft, requires manager approve
  before send (NEVER auto-send in v1)

### 1.4.4 Activity feed real-time
- [ ] WebSocket `activity.created` events → invalidate query
- [ ] Optimistic posts from composer with rollback on server reject

### 1.4.5 Tests
- [ ] Time-frozen test of plan generation
- [ ] Reminder dispatcher idempotent (reruns don't double-create)

---

## Sprint 1.5 — Polish + Launch (1 week)

Goal: DrinkX team can actually use this for real work.

- [ ] Notifications: in-app drawer + email digest (morning brief + weekly report)
- [ ] Audit log table + admin UI
- [ ] Empty states + error boundaries (port from prototype)
- [ ] Mobile responsive pass on Today and Lead Card
- [ ] Performance: Pipeline column virtualization (>200 cards)
- [ ] Accessibility pass (keyboard nav for drag-drop, contrast, focus rings)
- [ ] Soft launch checklist (production env vars, domain, sentry alerts, on-call rotation)

---

## Phase 2 — Inbox + Advanced (after MVP, ~6 weeks)

Tracked here only as a placeholder so we don't lose context. Each item gets a
sprint when we get there.

- [ ] Email IMAP idle (incoming) + SMTP (outgoing) per user
- [ ] Telegram Business webhook + match-by-username/phone
- [ ] Quote/КП builder with PDF generation
- [ ] WebForm public submit endpoint + admin builder
- [ ] Bulk Import/Export with all formats (YAML/CSV/Excel/Markdown ZIP)
- [ ] Knowledge Base CRUD UI + version history
- [ ] Apify integration as enrichment source
- [ ] Push notifications + Telegram bot delivery channel
- [ ] Multi-pipeline switcher
- [ ] Settings: team management, channel CRUD, AI provider config, custom-fields

---

## Phase 3 — Scale + Polish (~4 weeks)

- [ ] MCP server over FastAPI (so Claude Desktop / Cursor can drive the CRM)
- [ ] Public signal monitoring (HH.ru watcher per pipeline company)
- [ ] NL search over pipeline (whitelisted views only)
- [ ] AI Sales Coach chat sidebar
- [ ] Visit-card OCR parser
- [ ] Vector DB for "find similar past deals"
- [ ] Stalled-deal detector with reasons
- [ ] Apify-driven lead-gen wizard in UI

---

## Open decisions to revisit when relevant

1. MCP-server timing — Phase 2 vs v1.5
2. Multi-tenancy isolation — Postgres RLS vs schema-per-workspace
3. Vector DB on v1.0 — Pinecone / pgvector / defer
4. Quote line items — fixed-product catalog or freeform
5. WebForm publishing — REST vs embed-script
6. Telegram Business account ownership at DrinkX
7. Hosting in Russia — Selectel/Timeweb fallback if Vercel/Railway blocked
