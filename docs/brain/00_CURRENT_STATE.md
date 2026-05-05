# DrinkX CRM — Current State

Last updated: 2026-05-06

## Phase 0 — COMPLETED ✅ (lives in `crm-prototype` repo)

Clickable HTML prototypes deployed at https://globalsasha.github.io/drinkx-crm-prototype/

| File | Description |
|---|---|
| `index.html` | Service-grade prototype, 11+ screens, 7+ modals, 3 drawers — full functionality |
| `index-soft-full.html` | taste-soft hi-fi version (Plus Jakarta Sans + double-bezel) |
| `index-soft.html` | Landing / preview page |
| `index-b2b.html` | **B2B enterprise design reference** (see below) |
| `data.js` | 131 real DrinkX clients with full enrichment |
| `docs/PRD-v2.0.md` | 988-line product requirements |
| `build_data.py` | Parses drinkx-client-map → data.js |

### What `index-b2b.html` introduces (target spec for Phase 1 Sprint 1.2)

Built as gap-analysis between PRD v2.0 and original prototype. Covers 8 gaps:

**1. 11-stage B2B Sales Pipeline** (replaces 6-stage simple model):

```
Stage 1 Новый контакт      prob=5  rot=3
Stage 2 Квалификация       prob=15 rot=5
Stage 3 Discovery          prob=25 rot=7
Stage 4 Solution Fit       prob=40 rot=7
Stage 5 Business Case / КП prob=50 rot=5
Stage 6 Multi-stakeholder  prob=60 rot=7
Stage 7 Договор / пилот    prob=75 rot=5
Stage 8 Производство       prob=85 rot=10
Stage 9 Пилот              prob=90 rot=14
Stage 10 Scale / серия     prob=95 rot=14
```

**2. Gate criteria modal** — checklist of conditions per transition. Force-move
allowed with warning. 10 unique criteria sets (one per transition).

**3. Two scoring systems (DO NOT CONFLATE)**:
- `fit_score` (0–10) — AI auto, ICP match, computed by Research Agent
- `Score` (0–100) — manager manual, 8 weighted criteria:
  - Scale potential (20)
  - Pilot probability 90d (15)
  - Economic buyer (15)
  - Reference value (15)
  - Standard product (10)
  - Data readiness (10)
  - Partner potential (10)
  - Budget confirmed (5)

Tier derived from Score:
- 80–100 → Tier 1, личное управление
- 60–79 → Tier 2, активная работа
- 40–59 → Tier 3, nurture
- <40 → Tier 4, архив

**4. Multi-stakeholder roles** — 4 contact types per lead:
- 💰 Economic Buyer (required from Stage 6+)
- ⭐ Champion
- 🔧 Technical Buyer
- 🏢 Operational Buyer

**5. Deal Type — required field** (replaces simple "source"):
- Прямой enterprise-клиент
- QSR / high-volume foodservice
- Дистрибьютор / партнёр
- Сырьевой / стратегический партнёр
- Частный / малый клиент
- Сервис / повторная продажа

**6. Priority A/B/C/D** (replaces tier 1/2/3):
- A = Стратегический · B = Перспективный · C = Низкий · D = Архив
- Assigned at Stage 2 as gate condition

**7. Rotting — dual logic**:
- Stage-rot: time in stage > stage.rot_days
- Next-step-rot: next_action_at empty → 3d yellow → 7d red
- Both run independently

**8. Pilot Success Contract** — separate tab, visible from Stage 9+
Fields: pilot goal, period, locations, 6 success metrics
(cups/day, uptime, avg check, service time, incidents/month, baseline),
responsible parties, review date, decision (scale/extend/reject/refine)

Plus: Pipeline Review screen (45-min agenda), Team View with AI alerts,
Settings with 11-stage constructor.

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

### ✅ Sprint 1.1 — Auth + Onboarding partial (DONE)

Backend:
- SQLAlchemy 2 async models: `Workspace`, `User`, `Pipeline`, `Stage`
- Alembic `0001_initial` migration applied to production
- `app/auth/jwt.py` — Supabase JWT verifier (HS256) with stub-mode fallback
  when `SUPABASE_JWT_SECRET=""`
- `upsert_user_from_token` — auto-bootstraps Workspace + Pipeline + 7 default
  Stages on first sign-in
- Endpoints live: `GET /api/auth/me`, `PATCH /api/auth/me`
- Migration auto-runs on container start (`alembic upgrade head` in Dockerfile)

Frontend:
- `apps/web/app/sign-in/page.tsx` — taste-soft sign-in card (Google button
  disabled until SUPABASE_* env wired)
- Home links to `/sign-in`

⚠️ Stages currently seeded with **7 default stages** (old model from prototype).
Sprint 1.2 will re-seed with **11 B2B stages** + `gate_criteria_json` field.

### ⏸ NOT YET BUILT

- Lead schema (Lead, Contact, Activity, Followup tables)
- Real Supabase project + Google OAuth (env keys not yet provided)
- AI Research Agent (Brave / HH.ru / DeepSeek) — Sprint 1.3
- Daily Plan generator — Sprint 1.4
- Inbox (email / Telegram) — Phase 2
- Quote/КП builder — Phase 2
- Knowledge Base UI — Phase 2

---

## Open dependencies

User will provide later:
- Supabase project URL + anon_key + service_key + jwt_secret
- Google OAuth client ID + secret
- DeepSeek + Brave API keys
- Sentry DSNs

Current `.env` on server has autogen Postgres password; AI keys empty (stub mode).

---

## Next
**Sprint 1.2 — Core CRUD with B2B model.** See `docs/brain/04_NEXT_SPRINT.md`.
