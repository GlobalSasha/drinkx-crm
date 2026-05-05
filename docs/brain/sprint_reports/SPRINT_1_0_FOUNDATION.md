# Sprint 1.0 — Foundation (REPORT)

**Status:** ✅ DONE
**Period:** 2026-05-05 (single session)
**Branch:** main (scaffold work, no feature branch)

## Goal
Empty but deployable monorepo with Next.js + FastAPI + Postgres + Redis + nginx
+ TLS + auto-deploy on `git push origin main`.

## What shipped

### Repo skeleton
- CLAUDE.md, AUTOPILOT.md, README.md, .gitignore, Makefile
- pnpm-workspace.yaml + root package.json
- `apps/web` (Next.js 15, App Router, Tailwind, shadcn/ui deps, Zustand, TanStack Query, @dnd-kit, Supabase SSR client)
  - `app/page.tsx` (home with links to /sign-in, /today, /pipeline)
  - `app/today/page.tsx` (placeholder)
  - `app/pipeline/page.tsx` (placeholder)
  - `app/sign-in/page.tsx` (taste-soft sign-in card, Google button disabled)
  - `lib/api-client.ts` (typed fetch wrapper)
  - `Dockerfile` (multi-stage standalone build)
  - `next.config.mjs` (output: standalone)
- `apps/api` (Python 3.12, uv, FastAPI, SQLAlchemy 2 async, Pydantic v2)
  - `app/main.py` (factory + /health + /version + Sentry hook)
  - `app/config.py` (Pydantic Settings — env-driven)
  - `app/db.py` (async engine + session factory)
  - `app/common/models.py` (Base + UUIDPrimaryKeyMixin + TimestampedMixin)
  - 17 domain packages scaffolded (auth, leads, pipelines, contacts, inbox,
    enrichment, automation, assignment, activity, followups, quote, template,
    forms, knowledge, notifications, import_export, scheduled)
  - `Dockerfile`

### Infra
- `infra/docker/docker-compose.yml` (local Postgres + Redis + Mailhog)
- `infra/production/docker-compose.yml` (production stack, all on 127.0.0.1)
- `infra/production/.env.example` (placeholders for all secrets)
- `infra/production/nginx/crm.drinkx.tech.conf` (HTTPS + reverse-proxy + WebSocket)
- `infra/production/deploy.sh` (pull + rebuild + health check)

### Production server (bare-metal)
- Provisioned 77.105.168.227 / crm.drinkx.tech (Ubuntu 22.04)
- Apt update, 2GB swap, UFW (22/80/443), fail2ban
- Docker 29.4 + Compose v5.1
- nginx 1.18 + certbot (Let's Encrypt cert auto-renew)
- `deploy` user (in `docker` group, SSH key for GitHub Actions)
- Cloned repo to `/opt/drinkx-crm`
- `.env` with autogen 32-char Postgres password
- All 4 services healthy (postgres, redis, api, web)

### CI/CD
- `.github/workflows/deploy.yml` — SSH deploy on push to main, verify /health
- Secrets in GitHub: DEPLOY_SSH_KEY, DEPLOY_HOST, DEPLOY_USER

### Live URLs
- https://crm.drinkx.tech/ — Next.js placeholder home
- https://crm.drinkx.tech/api/health — `{"status":"ok"}`
- https://crm.drinkx.tech/api/version — version + env

## Deviations from PRD

- PRD §8.5 specified Vercel + Railway hosting. **Switched to bare-metal Ubuntu**
  because user provided own server. Same architecture, just different target.
  See ADR-013.
- Skipped: Supabase project creation, real Sentry DSN, Vercel/Railway projects.
  These are deferred until user provides credentials.

## Tests

No unit tests in this sprint — scaffold only. `/health` endpoint verified
end-to-end (curl returns `{"status":"ok"}` over HTTPS through nginx).

## What is NOT done

- Branch protection on `main` (manual GitHub UI step)
- `.github/workflows/web.yml` PR lint+typecheck+build (deferred)
- `.github/workflows/api.yml` PR ruff+mypy+pytest (deferred)
- Sentry integration end-to-end (DSN needed)

## Hand-off
Sprint 1.1 (Auth + Onboarding partial) started immediately after this in same
session — see `SPRINT_1_1_AUTH.md`.
