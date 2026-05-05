# Sprint 1.1 — Auth + Onboarding (REPORT, partial)

**Status:** ⚠️ PARTIAL — backend done, real Supabase OAuth deferred until credentials
**Period:** 2026-05-05 (continuation of same session as Sprint 1.0)
**Branch:** main (scaffold continuation; feature-branch policy starts Sprint 1.2)

## Goal
A real human can sign in (with Supabase Google OAuth when wired), get a
workspace bootstrapped, complete 4-step onboarding, and land on `/today`.

## What shipped

### Backend
- `apps/api/app/auth/models.py` — `Workspace`, `User` (with sprint_capacity_per_week,
  supabase_user_id, working_hours_json, specialization, max_active_deals,
  onboarding_completed, last_login_at)
- `apps/api/app/pipelines/models.py` — `Pipeline`, `Stage` with **DEFAULT_STAGES**
  seed of 7 stages (Новые лиды → Квалификация → КП → Переговоры →
  Согласование → Закрыто won/lost)
  ⚠️ **Sprint 1.2 will replace this with 11 B2B stages** + gate_criteria
- `alembic.ini` + `alembic/env.py` (async-aware) + `0001_initial` migration
- `apps/api/app/auth/jwt.py` — `TokenClaims` + `verify_token` (HS256 Supabase JWT,
  falls back to stub when SUPABASE_JWT_SECRET empty)
- `apps/api/app/auth/services.py` — `upsert_user_from_token` bootstraps Workspace
  + Pipeline + 7 stages on first sign-in, creates User as admin
- `apps/api/app/auth/dependencies.py` — `current_user`, `require_admin`
- `apps/api/app/auth/schemas.py` — UserOut, WorkspaceOut, UserUpdateIn
- `apps/api/app/auth/routers.py` — `GET /auth/me`, `PATCH /auth/me`
- `app/main.py` wires auth router
- Dockerfile entrypoint: `alembic upgrade head` runs before uvicorn

### Frontend
- `apps/web/app/sign-in/page.tsx` — taste-soft sign-in card
  (Google button disabled until Supabase env vars set)
- `apps/web/app/page.tsx` updated to link to `/sign-in`

### Production verification
- Migration auto-ran on deploy: 5 tables in Postgres
  (alembic_version, workspaces, users, pipelines, stages)
- `GET /api/auth/me` returns Dev User stub identity
- First call bootstraps Workspace "Drinkx" + Pipeline "Новые клиенты" + 7 stages
- `PATCH /api/auth/me` updates name/role/spec/working_hours/onboarding_completed
- Verified end-to-end via curl

## Deviations from plan

- **Real Supabase Auth deferred** — keys not provided yet. Stub mode
  (`SUPABASE_JWT_SECRET=""`) returns fixed `dev@drinkx.tech` identity.
  Switching to real OAuth = single env var change, no code change.
  See ADR-014.
- **Onboarding 4-step UI not built** — page placeholders only.
  Will revisit when real Auth is live.
- **No tests yet** — pytest fixtures deferred to Sprint 1.2 (where they'll be
  needed for lead CRUD coverage).

## Bug found and fixed in-session
- Pydantic `EmailStr` rejected `dev@drinkx.local` (`.local` is reserved TLD)
  → changed stub email to `dev@drinkx.tech`. Cleared stale row in DB,
  bootstrap re-ran successfully. No data migration needed for production.

## Hand-off

Sprint 1.2 (Core CRUD with B2B model) is the next sprint.
**Important inputs from Phase 0:**
- `crm-prototype/index-b2b.html` — 11-stage pipeline + gate criteria visual
- `docs/brain/00_CURRENT_STATE.md` — full B2B model spec
- `docs/PRD-v2.0.md` §6.2, §6.3, §8.3
- ADR-002 through ADR-015 in `docs/brain/03_DECISIONS.md`

Stages will need to be re-seeded from 7 → 11 in Sprint 1.2's first migration
(`0002_b2b_model`).
