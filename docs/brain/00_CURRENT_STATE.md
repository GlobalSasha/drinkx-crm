# DrinkX CRM — Current State

Last updated: 2026-05-07 (Sprint 1.3 closed)

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

### ✅ Sprint 1.0 — Foundation (DONE)

- Monorepo: `apps/web` (Next.js 15) + `apps/api` (FastAPI Python 3.12) + `infra/`
- Bare-metal Ubuntu 22.04 server (77.105.168.227 / crm.drinkx.tech)
- Docker stack: Postgres 16 + Redis 7 + API + Web + nginx + certbot TLS
- All services on `127.0.0.1`, exposed only via nginx HTTPS
- GitHub Actions auto-deploy on `git push origin main` (~90s end-to-end)
- `.github/workflows/deploy.yml` runs `deploy.sh` + verifies `/health`

### ✅ Sprint 1.1 — Auth + Onboarding (DONE — including real Supabase)

Backend:
- SQLAlchemy 2 async models: `Workspace`, `User`, `Pipeline`, `Stage`
- Alembic `0001_initial` migration applied to production
- `app/auth/jwt.py` — Supabase JWT verifier supporting BOTH legacy HS256
  AND modern asymmetric ES256/RS256 via the project's JWKS endpoint
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json` with 10-min cache)
- Stub-mode fallback when both `SUPABASE_JWT_SECRET` and `SUPABASE_URL` are empty
- `upsert_user_from_token` — auto-bootstraps Workspace + Pipeline + 11 B2B Stages on first sign-in
- Endpoints live: `GET /api/auth/me`, `PATCH /api/auth/me`

Frontend (Sprint 1.1.3):
- `@supabase/ssr` browser/server/middleware clients (`apps/web/lib/supabase/`)
- `middleware.ts` protects authed routes; redirects unauthed to `/sign-in?next=`
- `/auth/callback` route handler exchanges OAuth code for session; uses
  `x-forwarded-host`/`x-forwarded-proto` to build the redirect URL behind nginx
- Sign-in page wired to real Google OAuth + magic-link email OTP
- `api-client` transparently attaches `Bearer <access_token>` from current session
- AppShell sidebar shows real signed-in user

Real Supabase project linked, Google OAuth provider configured, JWT_SECRET in prod `.env` → stub mode is OFF on production.

### ✅ Sprint 1.2 — Core CRUD with B2B model (DONE — backend + frontend + import)

Backend:
- Migration `0002_b2b_model` with 5 new tables: `leads`, `contacts`, `activities`, `followups`, `scoring_criteria`
- Stage gained `gate_criteria_json` (JSON list); 11 B2B stages + 1 lost stage
- 8-criterion `scoring_criteria` table per workspace (sum to 100)
- Lead schema: B2B fields (`deal_type`, `priority`, `score`, `fit_score`, lead-pool fields, dual rotting flags, pilot contract JSON)
- REST endpoints:
  - Leads: `GET/POST/PATCH/DELETE /api/leads` with all B2B filters
  - Lead Pool: `GET /leads/pool`, `POST /leads/sprint` (race-safe, `FOR UPDATE SKIP LOCKED`),
    `POST /leads/{id}/claim`, `POST /leads/{id}/transfer`
  - Stage transitions: `POST /leads/{id}/move-stage` with gate criteria engine
    (hard `check_pipeline_match` + soft `check_economic_buyer_for_stage_6_plus` per ADR-012)
  - Contacts (4 endpoints), Activities (composer + cursor-paginated feed),
    Followups (CRUD + complete; 3 auto-seeded on lead create)
  - Pipelines: `GET /api/pipelines/` returns Pipeline[] with embedded stages
- `create_lead` auto-assigns `stage_id` to position-0 of default pipeline

Frontend:
- AppShell with sidebar (Today, Pipeline, База лидов; Phase-2 items disabled)
- `/today` — grouped sections (Сегодня / Завтра / Эта неделя / Без срока), priority filter chips, search, empty state with "Сформировать план" CTA
- `/pipeline` — Kanban with @dnd-kit drag-drop, optimistic update + rollback on 409 (gate-block toast), Sprint modal, Brief drawer (Esc/arrow nav, link to Lead Card)
- `/leads-pool` — table with city/segment/fit_min filters, "Взять в работу" with optimistic gray-out + race-loss toast
- `/leads/[id]` — Lead Card with 5 tabs: Сделка, AI Brief, Контакты, Scoring (8 sliders → tier badge), Активность (composer + filtered feed), Pilot (conditional stage>=8). GateModal with violations on 409.
- All hooks auth-aware (Bearer token from Supabase session)
- 216 leads imported from prototype (`scripts/import_prototype_data.py`):
  131 from `drinkx-client-map-v0.5-linkedin-industry-enriched`
  + 85 from `drinkx-client-map-v0.6-foodmarkets-audit/07_foodmarkets_candidates`
  via `scripts/build_foodmarkets_data.py` (YAML-frontmatter parser)
  All in `assignment_status='pool'` for the manager's workspace

### ✅ Sprint 1.3 — AI Enrichment (DONE — Phases A+B+C+D+E)

Backend:
- `app/enrichment/providers/` — `LLMProvider` Protocol + 4 implementations:
  - **MiMo** (Xiaomi, OpenAI-compatible, `api-key:` header) — primary
  - **Anthropic** (Messages API, `x-api-key`) — fallback (note: 403 from RU IP)
  - **Gemini** (v1beta REST) — fallback
  - **DeepSeek** (OpenAI-compatible, Bearer) — fallback
- `complete_with_fallback()` walks `LLM_FALLBACK_CHAIN` on rate-limit / auth / 5xx; surfaces full chain in raised error
- `TaskType` Flash/Pro split: research_synthesis/daily_plan/prefilter → Flash, sales_coach/scoring/reenrichment → Pro
- `app/enrichment/sources/` — Brave (X-Subscription-Token), HH.ru (no-auth), web_fetch (800KB cap, strip HTML, 3-redirect cap), 24h Redis cache
- Migration `0003_enrichment_runs` + `EnrichmentRun` model (lead_id, status, provider/model, tokens, cost_usd, duration_ms, sources_used, result_json, started_at/finished_at)
- Orchestrator: query builder → `asyncio.gather` Brave×3 + HH.ru + optional WebFetch → synthesis → save to `lead.ai_data` + run row. Never raises — failures write `status=failed`.
- `ResearchOutput` Pydantic with permissive defaults (LLMs return Russian role values; UI normalizes)
- `DrinkX profile` (`config/drinkx_profile.yaml`) injected into every synthesis system prompt — product, ICP, fit_score anchors, common objections
- Cost guards:
  - **Per-lead rate limit**: only 1 `running` enrichment per lead — 409 with in-flight `run_id`
  - **Workspace concurrency cap**: max 5 parallel runs per workspace — 429
  - **Daily budget cap**: Redis counter `ai_budget:{workspace_id}:{YYYY-MM-DD}`, cap = `ai_monthly_budget_usd / 30` ≈ $6.66/day default — 429
- REST: `POST /leads/{id}/enrichment` (202 + `BackgroundTasks`), `GET .../latest`, `GET .../`

Frontend:
- AI Brief tab (between Сделка and Контакты): hero band with company_profile + 96px fit_score badge, coffee signals in accent panel (the thesis), growth/risk as balance sheet, decision-maker cards with avatar + role + confidence, numbered next-step list
- Failure modes handled: skeleton during running, banner on failed, `<details>` for raw JSON edge-case
- `useLatestEnrichment` polls every 2s while status=running; mutation invalidates lead query

LLM tone:
- Synthesis prompt explicitly forbids jargon (`ритейлер`, `email-рассылки`, `B2B`, `ROI`, `кофейные технологии`, `кофепойнты`, `стейкхолдеры`, `ICP`, `закупочная команда`, `operational excellence`)
- Asks for the language an account manager would write in
- MiMo payload: `reasoning_effort: "minimal"` + `thinking: {type: "disabled"}` (defensive — disable extended thinking so max_tokens budget stays for the JSON)

### ⏸ NOT YET BUILT

- **Phase F (Sprint 1.3 follow-on)**: Knowledge Base markdown library (`apps/api/knowledge/drinkx/*.md` with YAML frontmatter, tag-based grounding by `lead.segment`)
- **Phase G (Sprint 1.3 follow-on)**: Celery worker for enrichment (currently FastAPI `BackgroundTasks`) + WebSocket `/ws/{user_id}` for real-time progress (currently 2s polling)
- **Sprint 1.4** — Daily Plan generator (Celery beat 08:00/timezone, AI prioritization, follow-up reminder dispatcher)
- **Sprint 1.5** — Polish + Launch (notifications, audit log, mobile pass)
- **Phase 2** — Inbox (email + Telegram), Quote/КП builder, Knowledge Base UI

---

## Open dependencies

User-provided (state at sprint close):
- ✅ Supabase project URL + publishable + secret + JWT secret — in prod
- ✅ Google OAuth provider configured in Supabase
- ✅ MIMO_API_KEY in prod
- ✅ ANTHROPIC_API_KEY in prod (note: 403 from RU IP, fallback only)
- ✅ BRAVE_API_KEY in prod
- ⚠ GEMINI_API_KEY — not configured
- ⚠ DEEPSEEK_API_KEY — not configured (intentional)
- ⏸ Sentry DSNs — empty (file logs + journalctl for now)

Production .env on VPS at `/opt/drinkx-crm/infra/production/.env`.

---

## Known production constraints

1. **Anthropic from RU is dead** — every fallback walk pays the round-trip latency to get a 403 before falling through. Fix candidates: VPN on VPS, drop Anthropic from default chain, or proxy via OpenRouter.
2. **No Celery / WebSocket** — UI polls `/latest` every 2s while a run is in flight. Acceptable at low concurrency.
3. **`fit_score` last-writer-wins** — orchestrator and the manual scoring tab both write to the same column. No conflict resolution.

---

## Next
**Sprint 1.4 — Daily Plan generator.** See `docs/brain/04_NEXT_SPRINT.md`.
