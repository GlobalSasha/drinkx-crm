# DrinkX Smart AI CRM

B2B CRM with AI-driven research agent, daily plan generator, unified inbox, and
follow-up automation. Production rebuild of the Phase 0 clickable HTML prototype.

- **Prototype (live):** https://globalsasha.github.io/drinkx-crm-prototype/
- **PRD (single source of truth):** [`docs/PRD-v2.0.md`](docs/PRD-v2.0.md)
- **Roadmap (live):** [`AUTOPILOT.md`](AUTOPILOT.md)
- **Claude session brief:** [`CLAUDE.md`](CLAUDE.md)

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js 15 (App Router) + React 19 + TypeScript + Tailwind + shadcn/ui + Zustand + TanStack Query |
| API | Python 3.12 + FastAPI + SQLAlchemy 2 (async) + Pydantic v2 + Alembic |
| Async | Celery + Upstash Redis |
| DB | PostgreSQL via Supabase |
| Auth | Supabase Auth (Google OAuth + magic link) |
| AI | DeepSeek V3 (primary) + OpenAI (vision) + Gemini (fallback) + Brave Search + HH.ru |
| Hosting | Vercel (web) + Railway (api / worker / beat) |
| Errors | Sentry |

## Quickstart (local dev)

Prereqs: Node 20+, pnpm 9+, Python 3.12+, Docker, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/GlobalSasha/drinkx-crm.git
cd drinkx-crm

# 1. Boot local infra (Postgres + Redis)
make db.up

# 2. Web
cd apps/web && pnpm install && pnpm dev   # http://localhost:3000

# 3. API (in another terminal)
cd apps/api && uv sync && uv run fastapi dev app/main.py   # http://localhost:8000
```

The web app expects `NEXT_PUBLIC_API_URL=http://localhost:8000`.
Copy `apps/web/.env.local.example` → `.env.local` and fill the rest.

## Repo layout

```
apps/
  web/         Next.js frontend
  api/         FastAPI backend (package-per-domain)
infra/
  docker/      docker-compose for local Postgres + Redis
  supabase/    SQL migrations (managed by Alembic-export tool)
docs/
  PRD-v2.0.md  consolidated product spec
AUTOPILOT.md   sequential roadmap with checkboxes
CLAUDE.md      orientation for Claude sessions
```

## Contributing inside this repo

1. Read [`CLAUDE.md`](CLAUDE.md)
2. Find the next `- [ ]` item in [`AUTOPILOT.md`](AUTOPILOT.md)
3. Do that one item, tick the box, commit, push

## License

Internal DrinkX project. All rights reserved.
