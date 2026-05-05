# DrinkX CRM — Target Architecture

## Stack (Phase 1 target — MVP)

| Layer | Tech | Status |
|---|---|---|
| Frontend | Next.js 15 (App Router) + shadcn/ui + Tailwind + Zustand + TanStack Query | ✅ scaffold live |
| Backend | Python 3.12 + FastAPI async + SQLAlchemy 2.0 + Alembic + Celery | ✅ scaffold live, 4 tables migrated |
| Database | Postgres (Supabase target → bare-metal Postgres 16 currently) | ✅ live |
| Queue | Redis (Upstash target → bare-metal Redis 7 currently) | ✅ live, no celery yet |
| Auth | Supabase Auth + Google OAuth | ⏸ stub mode (real keys pending) |
| Hosting | Vercel + Railway target → bare-metal Ubuntu 22.04 currently (77.105.168.227 / crm.drinkx.tech) | ✅ live |
| Monitoring | Sentry | ⏸ DSN pending |

Decision deviation from PRD: **bare-metal hosting** chosen instead of Vercel+Railway
because user provided own server. Same Docker stack, same architecture, just
different hosting target. See ADR-013 in `03_DECISIONS.md`.

## AI Stack (planned)

| Use case | Primary | Fallback |
|---|---|---|
| Bulk Research Agent | DeepSeek V3 | OpenAI GPT-4o-mini |
| High-fit (≥8) re-enrichment | OpenAI GPT-4o | Gemini 1.5 Pro |
| Sales Coach chat | DeepSeek V3 | — |
| Daily Plan generation | DeepSeek V3 | OpenAI GPT-4o-mini |
| Visit-card OCR | OpenAI GPT-4o vision | Gemini 1.5 Pro |

External data sources for Research Agent:
- Brave Search API (web research)
- HH.ru Public API (vacancies — free)
- Apify (Google Maps, LinkedIn, Yandex Places) — Phase 1.5
- web_fetch (company websites)
- 24h Redis cache by company_name (~40-60% hit rate)

## 5 AI Modules

### 1. Research Agent
Trigger: lead created or manual re-enrichment
Pipeline: Quality pre-filter → Query Builder (LLM) → Parallel Fetch
  (BraveSearch + HH.ru + Apify + web_fetch) → Relevance Filter →
  Synthesis LLM → Save to `lead.ai_data` + WebSocket push to UI

Output schema (Pydantic with fallback defaults — never raise on missing fields):
- company_profile, scale_signals
- growth_signals[], risk_signals[]
- decision_maker_hints
- **fit_score (0–10)** — AI ICP match (NOT the same as Score 0-100)
- next_steps[], urgency, sources_used[]

### 2. Daily Plan Generator
Trigger: Celery cron 08:00 in workspace timezone
Steps: get active leads → PriorityScorer (urgency × deal_size × stage_prob × ai_urgency)
  → pack into work_hours → LLM generates 1-line task hint per item
  → save DailyPlan → notify manager (in-app + email digest)

### 3. AI Assignment Engine
```
Score(manager, lead) =
  (1 - current_load) × 0.4
  + expertise_match(manager, lead) × 0.3
  + time_zone_match × 0.2
  + round_robin_fairness × 0.1
```

Pluggable strategies in `app/assignment/`:
- RoundRobinStrategy
- WorkloadBasedStrategy
- ExpertiseBasedStrategy (sales history + segment)
- HybridStrategy (current default — combination)

**B2B-specific filter:** Deal Type filters eligible managers (Enterprise Direct →
Senior only; Partner deals → managers with `partnerships` spec).

### 4. Sales Coach
Location: FAB button in lead card → drawer with chat
Context injected:
- Current stage + gate status
- Contact roles (Economic Buyer / Champion / Technical / Operational)
- AI Brief
- Knowledge Base (matching segment/tags)
- `config/drinkx_profile.yaml` (company tone + ICP)

**Rule: AI proposes, manager approves. No auto-outbound.**

### 5. Inbox Matching
Channels: Email (IMAP/SMTP/Gmail API), Telegram Business (Premium account),
WhatsApp (Phase 2 via Meta Cloud API)
Match logic: `email → lead.email`, `TG → lead.telegram_id`, `WA → lead.phone`
No match → unmatched bucket → manual assignment

## Backend Package Structure (Krayin pattern, NOT layered)

```
apps/api/app/
  auth/           ✅ scaffolded
  pipelines/      ✅ scaffolded
  leads/          ⏸ Sprint 1.2
  contacts/       ⏸ Sprint 1.2
  activity/       ⏸ Sprint 1.2
  followups/      ⏸ Sprint 1.2
  enrichment/     ⏸ Sprint 1.3
    sources/      brave.py, hh.py, web_fetch.py, apify_*.py
  automation/     ⏸ Sprint 1.2 (stage_change hooks)
  assignment/     ⏸ Sprint 1.4
  inbox/          ⏸ Phase 2
  quote/          ⏸ Phase 2
  template/       ⏸ Phase 2
  forms/          ⏸ Phase 2
  knowledge/      ⏸ Phase 2
  notifications/  ⏸ Sprint 1.5
  import_export/  ⏸ Phase 2
  scheduled/      ⏸ Sprint 1.4 (Celery beat registry)
  common/         ✅ Base + UUIDPrimaryKey + Timestamped mixins
```

Each package: `models.py` + `schemas.py` + `repositories.py` + `services.py`
              + `tasks.py` (Celery) + `routers.py` + `events.py`

## Estimated Infrastructure Cost (DrinkX scale, 500 leads/day)

~$130–180 / month total · AI portion ~$50–70 / month
- DeepSeek V3: ~$0.0003/1K tokens (synthesis)
- Brave Search: $7.50/day raw → cache reduces to ~$3-5/day
- HH.ru: free
- Apify: $5-15/month
- Postgres/Redis (managed): $30-40
- Vercel/Railway (when migrated): $50

Currently zero cloud cost — running on user's bare-metal server.
