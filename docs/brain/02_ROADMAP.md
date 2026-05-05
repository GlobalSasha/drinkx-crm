# DrinkX CRM — Roadmap

## ✅ DONE

### Phase 0 — UX/UI Design & Prototyping (in `crm-prototype` repo)
- HTML prototypes: index.html, index-soft-full.html, index-soft.html
- B2B full reference: index-b2b.html (11-stage pipeline, gate criteria,
  scoring 0-100, multi-stakeholder, deal type, A/B/C/D, dual-rotting,
  pilot contract, pipeline review)
- data.js: 131 real DrinkX clients
- PRD v2.0 + addition v2.1 (Lead Pool & Sprint System)
- Design system: taste-soft (Plus Jakarta Sans + double-bezel + squircle)

### Phase 1 — Foundation + Auth (in `drinkx-crm` repo)
**Sprint 1.0 — DONE**
- Monorepo (Next.js + FastAPI), bare-metal Docker stack on crm.drinkx.tech
- Postgres 16 + Redis 7 + nginx + Let's Encrypt TLS
- GitHub Actions auto-deploy (~90s on push to main)

**Sprint 1.1 — DONE (partially — Supabase deferred)**
- SQLAlchemy models: Workspace, User, Pipeline, Stage
- Alembic 0001 migration applied
- Stub-mode JWT verifier + `current_user` dependency
- `upsert_user_from_token` workspace bootstrap
- `GET /api/auth/me` + `PATCH /api/auth/me` live
- Sign-in UI scaffolded
- ⏸ Real Supabase project + Google OAuth pending user creds

## 🔜 NEXT

### Phase 1 — MVP continuation (~6-7 weeks remaining)

**Sprint 1.2 — Core CRUD with B2B model (2 weeks)** ← READY TO START
- Re-seed stages 7 → 11 (B2B pipeline) + add `gate_criteria_json` field
- Lead schema: `deal_type`, `priority` (A/B/C/D), `score` (0-100, manager-set),
  `fit_score` (0-10, AI-set, NULL until Sprint 1.3),
  `next_action_at`, `assignment_status` (pool/assigned/transferred), Lead Pool fields
- Contact schema with `role_type` enum (economic_buyer / champion /
  technical_buyer / operational_buyer)
- Activity polymorphic table (comment / task / reminder / file / email / tg / system)
- Followup table (auto-seeded sequences per stage)
- Pilot Contract embedded JSON in Lead (activates from Stage 9)
- REST: `/leads`, `/leads/pool`, `/leads/sprint`, `/leads/{id}/claim`,
  `/leads/{id}/transfer`, `/contacts`, `/activities`, `/followups`
- Stage transitions through `app/automation/stage_change.py` with gate validation
- Frontend: Today + Pipeline (drag-drop with @dnd-kit) + Lead Card with 4 tabs
  + Brief drawer + Lead Pool page + Sprint modal

**Sprint 1.3 — AI Enrichment (2 weeks)**
- Research Agent (BraveSearch + HH.ru + web_fetch)
- DeepSeek V3 provider via Protocol pattern
- `enrichment_runs` entity with cost tracking
- WebSocket progress
- Knowledge Base loader

**Sprint 1.4 — Daily Plan + Follow-ups (1 week)**
- Celery beat (cron 08:00 per timezone)
- AI prioritization + 1-line task hints
- Follow-up reminder dispatcher (every 15min)

**Sprint 1.5 — Polish + Launch (1 week)**
- Notifications (in-app + email digest)
- Audit log
- Empty/error states, mobile responsive
- Soft launch for DrinkX team

## 📅 LATER

### Phase 2 (~6 weeks)
Inbox (Email IMAP/SMTP + Telegram Business webhook), Quote/КП builder,
WebForms, Bulk Import/Export, Knowledge Base UI, Apify integration,
push notifications + Telegram bot, multi-pipeline switcher,
full Settings panel.

### Phase 3 (~4 weeks)
MCP server, AI Sales Coach full chat, Visit-card OCR parser,
Vector DB (pgvector) for similar-deals retrieval, Stalled-deal detector,
Pipeline column virtualization (>1000 cards), Apify lead-gen wizard.
