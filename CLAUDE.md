# CLAUDE.md — DrinkX Smart AI CRM

Context for any Claude session in this repo. Read first before doing anything.

## What this is

Production build of **Smart AI CRM for DrinkX** — B2B CRM that sells smart coffee stations
to retail / HoReCa / QSR / gas stations. Takes over from a clickable HTML prototype that
lives separately at `~/Desktop/crm-prototype/` and is deployed to
https://globalsasha.github.io/drinkx-crm-prototype/.

Single source of truth for product decisions: **`docs/PRD-v2.0.md`** (consolidated PRD,
988 lines, covers IA, all screens, AI architecture, data model, phases).

Single source of truth for execution: **`AUTOPILOT.md`** at the repo root. Sequential
roadmap with checkboxes. Always read this first, then continue from the first
unchecked item.

## How to operate in this repo

1. Read `AUTOPILOT.md` at repo root before any work
2. Find the first `- [ ]` item under the current sprint
3. Do that one item. Keep changes surgical
4. Tick the checkbox in `AUTOPILOT.md` when done
5. Commit with a clear message — one logical change per commit
6. If you uncover scope creep, write a new item into AUTOPILOT.md instead of expanding
   the current one

## Codebase shape

```
apps/
  web/         # Next.js 15 (App Router) — frontend
  api/         # FastAPI — backend, package-per-domain (NOT layered)
infra/
  docker/      # docker-compose for local dev (Postgres + Redis)
  supabase/    # SQL migrations
docs/
  PRD-v2.0.md  # consolidated product spec
AUTOPILOT.md   # sequential roadmap with checkboxes
CLAUDE.md      # this file
```

## Backend conventions (apps/api)

- Python 3.12+, async-first
- Package-per-domain — every domain gets `models.py`, `schemas.py`, `repositories.py`,
  `services.py`, `tasks.py` (Celery), `routers.py`, `events.py`
- Domains: `auth, leads, pipelines, contacts, inbox, enrichment, automation,
  assignment, activity, followups, quote, template, forms, knowledge, notifications,
  import_export, scheduled, common`
- Long AI tasks NEVER block REST. POST creates a job entity, returns 202, Celery
  worker fills it; client subscribes via WebSocket
- Pydantic schemas for AI outputs use `Optional` + defaults — never raise on missing
  fields. See PRD §7.2 for the canonical `ResearchOutput` example
- Stage transitions go through `app/automation/stage_change.py` (pre/post hooks)

## Frontend conventions (apps/web)

- Next.js 15, App Router, TypeScript strict
- shadcn/ui + Tailwind, Zustand for client state, TanStack Query for server state
- Apple system fonts for service-grade screens; **taste-soft variant** uses
  Plus Jakarta Sans + JetBrains Mono with double-bezel cards (see prototype
  `index-soft-full.html` for the pattern)
- Mobile-first responsive — desktop-only is not acceptable
- Routes mirror the IA: `/today`, `/pipeline`, `/leads/[id]`, `/inbox`, `/team`,
  `/knowledge`, `/segments`, `/settings`, `/onboarding`

## Anti-patterns — do NOT introduce

1. Sync REST for long AI tasks
2. LLM with raw SQL access (only whitelisted views)
3. Multi-agent for the sake of it
4. AI auto-actions without human-in-the-loop
5. Metadata-driven DSL for everything (only fields/forms/navigation)
6. Monolithic `cron/` scripts (use Celery beat with explicit registry)
7. Output schemas without fallback defaults

## External services and accounts

| Service | Used for | How to get creds |
|---|---|---|
| Supabase | Postgres + Auth + Storage | env: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWT_SECRET` |
| Upstash | Redis (Celery broker) | env: `REDIS_URL` |
| DeepSeek | Primary LLM | env: `DEEPSEEK_API_KEY` |
| OpenAI | Vision + high-value carts | env: `OPENAI_API_KEY` |
| Brave Search | Web research | env: `BRAVE_API_KEY` |
| HH.ru | Vacancies signal | public, no key |
| Apify | (Phase 1.5+) scrapers | env: `APIFY_TOKEN` |
| Google OAuth | Sign-in | env: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Sentry | Errors | env: `SENTRY_DSN` |

Local dev uses `.env.local` files. Production uses Railway / Vercel env vars.
NEVER commit real keys.

## Deployment

- Frontend: Vercel (auto-deploy from `main`)
- Backend: Railway (one service for FastAPI, one for Celery worker, one for Celery
  beat)
- DB: Supabase (managed)
- Redis: Upstash

## When you finish a unit of work

1. Tick the AUTOPILOT.md checkbox
2. Commit with a one-line summary that mentions the AUTOPILOT item id
3. If tests pass, push
4. If you blocked on something (env var, account, decision), write a `> [BLOCKED]`
   note under the item describing what you need from the human

## Useful URLs

- Prototype (live): https://globalsasha.github.io/drinkx-crm-prototype/
- Prototype repo: https://github.com/GlobalSasha/drinkx-crm-prototype
- Production repo: TBD (created in AUTOPILOT step 1.0.4)
- PRD: `docs/PRD-v2.0.md`
- Source data: `~/Downloads/drinkx-client-map-v0.5-linkedin-industry-enriched/`
