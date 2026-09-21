# DrinkX Smart AI CRM

B2B CRM with AI-driven research agent, daily plan generator, unified inbox, and
follow-up automation. Production rebuild of the Phase 0 clickable HTML prototype.

- **Prototype (live):** https://globalsasha.github.io/drinkx-crm-prototype/
- **PRD (single source of truth):** [`docs/PRD-v2.0.md`](docs/PRD-v2.0.md)
- **Roadmap (live):** [`docs/brain/04_NEXT_SPRINT.md`](docs/brain/04_NEXT_SPRINT.md)
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

Prereqs: Node 20+, pnpm 9+, Python 3.12+, Docker, [uv](https://docs.astral.sh/uv/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`).

Без uv и Docker тоже можно, просто руками:

```bash
# вместо uv sync
cd apps/api && python3.12 -m venv .venv && . .venv/bin/activate
pip install -e . && pip install --group dev   # dev-зависимости лежат в
                                              # [dependency-groups], а не в
                                              # extras: `pip install -e ".[dev]"`
                                              # тихо поставит пакет без pytest
# вместо make db.up — свои Postgres и Redis с параметрами из
# infra/docker/docker-compose.yml, дальше DATABASE_URL / REDIS_URL в окружении
```

Redis нужен только воркеру и beat: без него REST работает целиком (POST
создаёт job и возвращает 202), а Celery-воркер просто бесконечно пробует
переподключиться — «локального режима без брокера» у него нет.

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
Copy `apps/web/.env.local.example` → `apps/web/.env.local` and fill the rest.

Настройки API читаются из `apps/api/.env` — файла ровно с этим именем
(`pydantic-settings`, см. `app/config.py`). Положить их в `.env.local`, по
аналогии с фронтендом, не получится: файл молча не прочитается, API
поднимется на дефолтах и укажет не на ту базу, ничего не сказав.

Открыть защищённые экраны локально без реального проекта Supabase можно с
`NEXT_PUBLIC_DEV_AUTH_BYPASS=1` в `apps/web/.env.local` — см.
`apps/web/.env.local.example`.

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
docs/brain/    состояние кодовой базы и текущий спринт
CLAUDE.md      orientation for Claude sessions
```

## Contributing inside this repo

1. Read [`CLAUDE.md`](CLAUDE.md)
2. Find the next `- [ ]` item in [`docs/brain/04_NEXT_SPRINT.md`](docs/brain/04_NEXT_SPRINT.md)
3. Do that one item, tick the box, commit, push

## License

Internal DrinkX project. All rights reserved.
