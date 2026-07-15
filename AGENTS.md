# AGENTS.md — DrinkX Smart AI CRM

Context for any AI agent (Codex, and other AGENTS.md-aware tools) working in this
repo. Read this first before doing anything. This file mirrors `CLAUDE.md`; if the
two ever disagree, `docs/PRD-v2.0.md` (product) and `docs/brain/` (execution) win.

## Working language

- The product owner is **not a programmer** and works in **Russian**.
- Reply in **Russian**, in plain language, without jargon. Explain what you did and
  why in terms a non-technical founder can follow.
- Surface tradeoffs and ask before doing anything irreversible (force-push, deleting
  data, changing production env, merging to `main`).

## What this is

Production build of **Smart AI CRM for DrinkX** — a B2B CRM that sells smart coffee
stations to retail / HoReCa / QSR / gas stations. It takes over from a clickable HTML
prototype (deployed at https://globalsasha.github.io/drinkx-crm-prototype/).

- **Product source of truth:** `docs/PRD-v2.0.md` (consolidated PRD — IA, all screens,
  AI architecture, data model, phases).
- **Execution source of truth:** `docs/brain/` — start with `00_CURRENT_STATE.md`
  (where the codebase is now), then `04_NEXT_SPRINT.md` (what to do next).

## How to operate in this repo

1. Read `docs/brain/00_CURRENT_STATE.md`, then `docs/brain/04_NEXT_SPRINT.md`.
2. Find the first `- [ ]` item under the current sprint.
3. Do that **one** item. Keep changes surgical — touch only what the task needs.
4. Tick the checkbox in `docs/brain/04_NEXT_SPRINT.md` when done.
5. Commit with a clear one-line message — one logical change per commit.
6. If you uncover scope creep, add a **new** item to `04_NEXT_SPRINT.md` instead of
   expanding the current one.
7. If you're blocked (missing env var, account, decision), write a `> [BLOCKED]` note
   under the item describing what you need from the human.

## Codebase shape

```
apps/
  web/         # Next.js 15 (App Router) — frontend
  api/         # FastAPI — backend, package-per-domain (NOT layered)
infra/
  docker/      # docker-compose for local dev (Postgres + Redis)
  supabase/    # SQL migrations
  production/  # bare-metal deploy scripts + prod env layout
docs/
  PRD-v2.0.md              # consolidated product spec
  brain/00_CURRENT_STATE.md  # snapshot of where the codebase is
  brain/04_NEXT_SPRINT.md    # current sprint spec + checkboxes
AGENTS.md      # this file (Codex entry point)
CLAUDE.md      # same context, for Claude Code
```

## Backend conventions (apps/api)

- Python 3.12+, async-first.
- **Package-per-domain** — every domain has `models.py`, `schemas.py`,
  `repositories.py`, `services.py`, `tasks.py` (Celery), `routers.py`, `events.py`.
- Domains: `auth, leads, pipelines, contacts, inbox, enrichment, automation,
  assignment, activity, followups, quote, template, forms, knowledge, notifications,
  import_export, scheduled, common` (plus newer domains like `lead_sources`,
  `presence` — check the tree).
- Long AI tasks **never** block REST. POST creates a job entity, returns 202, a Celery
  worker fills it; the client subscribes via WebSocket.
- Pydantic schemas for AI outputs use `Optional` + defaults — never raise on missing
  fields (PRD §7.2 has the canonical `ResearchOutput` example).
- Stage transitions go through `app/automation/stage_change.py` (pre/post hooks).
- DB migrations: Alembic. Check `docs/brain/04_NEXT_SPRINT.md` for the current head and
  next free index before adding a migration.

## Frontend conventions (apps/web)

- Next.js 15, App Router, TypeScript strict.
- shadcn/ui + Tailwind, Zustand for client state, TanStack Query for server state.
- Mobile-first responsive — desktop-only is not acceptable.
- Routes mirror the IA: `/today`, `/pipeline`, `/leads/[id]`, `/inbox`, `/team`,
  `/knowledge`, `/segments`, `/settings`, `/onboarding`.
- Spacing scale: **4-8-12-16-24-32px only**, no arbitrary values.
- Fonts: **no Inter, Roboto, or Arial.** Apple system fonts for service-grade screens;
  the taste-soft variant uses Plus Jakarta Sans + JetBrains Mono.
- The interface-design baseline lives at `.interface-design/system.md` — follow it.

## Anti-patterns — do NOT introduce

1. Sync REST for long AI tasks.
2. LLM with raw SQL access (only whitelisted views).
3. Multi-agent for the sake of it.
4. AI auto-actions without human-in-the-loop.
5. Metadata-driven DSL for everything (only fields/forms/navigation).
6. Monolithic `cron/` scripts (use Celery beat with an explicit registry).
7. Output schemas without fallback defaults.

## External services and accounts

| Service | Used for | Creds |
|---|---|---|
| Supabase | Postgres + Auth + Storage | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWT_SECRET` |
| Upstash | Redis (Celery broker) | `REDIS_URL` |
| DeepSeek | Primary LLM | `DEEPSEEK_API_KEY` |
| OpenAI | Vision + high-value carts | `OPENAI_API_KEY` |
| Brave Search | Web research | `BRAVE_API_KEY` |
| HH.ru | Vacancies signal | public, no key |
| Apify | (Phase 1.5+) scrapers | `APIFY_TOKEN` |
| Google OAuth | Sign-in | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Sentry | Errors | `SENTRY_DSN` |

Local dev uses `.env.local` files. Production env vars live on the bare-metal server at
`/opt/drinkx-crm/.env` and in GitHub Actions secrets. **NEVER commit real keys.**

## Deployment

Production runs on a **bare-metal server** (`crm.drinkx.tech` / `77.105.168.227`), NOT
Vercel/Railway.

- **Trigger:** every push to `main` fires `.github/workflows/deploy.yml`. It SSHes into
  the server and runs `infra/production/deploy.sh` — `git pull`, `docker compose build`
  of `web`, `api`, `worker`, `beat`, then health-checks `/sign-in`.
- **Frontend** (`apps/web`): Next.js 15 in the `web` container.
- **Backend** (`apps/api`): FastAPI in `api`; Celery worker in `worker`; Celery beat in
  `beat` — all three share one image.
- **DB:** Supabase (managed Postgres). **Redis:** Upstash.
- If a deploy fails: `gh run list --workflow "Deploy to crm.drinkx.tech"`, then
  `gh run view <id> --log-failed`. Note: the prod server occasionally can't reach
  github.com and the deploy hangs on `git fetch` — that's infra flakiness, retry.

## Pre-PR / pre-push checklist

`tsc --noEmit` is **not enough** for `apps/web` — Next.js 15 build-time checks (typed
routes, Suspense around `useSearchParams`, RSC import constraints) only fire during
`next build`. Before pushing a frontend change:

1. `npm run typecheck`
2. `npm run lint`
3. `pnpm build` from `apps/web` — **mandatory** when the change adds/edits a
   `<Link href={...}>` with a non-literal href, uses `useSearchParams` / `useRouter`,
   or otherwise touches App-Router routing.

For backend changes: `python -m py_compile` on touched modules + `pytest` (at minimum
`pytest --collect-only`). Many DB-backed tests skip locally (no Postgres) and run in CI.

## When you finish a unit of work

1. Tick the checkbox in `docs/brain/04_NEXT_SPRINT.md`.
2. Commit with a one-line summary that mentions the sprint gate (e.g. `G1`, `G2`).
3. Push only when the user asks. Pushing to `main` auto-deploys to production — treat it
   as a release, not a save.

## Useful links

- Repo: https://github.com/GlobalSasha/drinkx-crm
- Live prototype: https://globalsasha.github.io/drinkx-crm-prototype/
- Production app: https://crm.drinkx.tech
- PRD: `docs/PRD-v2.0.md`
