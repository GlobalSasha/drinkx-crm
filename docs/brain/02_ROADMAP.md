# DrinkX CRM — Roadmap

## ✅ DONE

### Phase 0 — UX/UI Design & Prototyping (in `crm-prototype` repo)
- HTML prototypes: index.html, index-soft-full.html, index-soft.html
- B2B full reference: index-b2b.html (11-stage pipeline, gate criteria,
  scoring 0-100, multi-stakeholder, deal type, A/B/C/D, dual-rotting,
  pilot contract, pipeline review)
- data.js: 131 real DrinkX clients
- drinkx-client-map-v0.6-foodmarkets-audit: +85 candidates
- PRD v2.0 + addition v2.1 (Lead Pool & Sprint System)
- Design system: taste-soft (Plus Jakarta Sans + double-bezel + squircle)

### Phase 1 — Foundation + Auth (in `drinkx-crm` repo)

**Sprint 1.0 — DONE** · `SPRINT_1_0_FOUNDATION.md`
- Monorepo (Next.js + FastAPI), bare-metal Docker stack on crm.drinkx.tech
- Postgres 16 + Redis 7 + nginx + Let's Encrypt TLS
- GitHub Actions auto-deploy (~90s on push to main)

**Sprint 1.1 — DONE** · `SPRINT_1_1_AUTH.md` + Sprint 1.1.3 follow-on
- SQLAlchemy models: Workspace, User, Pipeline, Stage
- Alembic 0001 migration applied
- Stub-mode JWT verifier + JWKS-based ES256/RS256 verification (modern Supabase)
- `upsert_user_from_token` workspace bootstrap
- `GET /api/auth/me` + `PATCH /api/auth/me` live
- Real Supabase + Google OAuth + magic link wired via `@supabase/ssr`
- `middleware.ts` protects authed routes; `/auth/callback` route handler

**Sprint 1.2 — DONE** · `SPRINT_1_2_BACKEND_MERGE.md` + frontend follow-on
- Migration 0002: 5 new tables (leads, contacts, activities, followups, scoring_criteria), 11 B2B stages with gate_criteria_json
- All Lead REST endpoints (CRUD, pool, sprint, claim, transfer)
- Stage transitions through `app/automation/stage_change.py` with gate engine
- 4 contact role types, polymorphic activities, auto-seeded followups
- AppShell + Today + Pipeline (drag-drop) + Lead Pool + Lead Card (5 tabs)
- 216 leads imported from prototype data (131 v0.5 + 85 v0.6 foodmarkets)

**Sprint 1.3 — DONE** · `SPRINT_1_3_AI_ENRICHMENT.md`
- LLMProvider abstraction: MiMo (primary, OpenAI-compatible) + Anthropic + Gemini + DeepSeek with fallback chain
- Sources: Brave + HH.ru + web_fetch with 24h Redis cache
- Migration 0003: `enrichment_runs` table; orchestrator writes `lead.ai_data` + run row
- AI Brief tab (Lead Card) with hero band, coffee-signals panel, growth/risk balance sheet, decision-maker cards, next-steps checklist
- DrinkX profile YAML injected into synthesis prompts; business-tone Russian, no jargon
- Cost guards: per-lead 1-running rate limit, workspace concurrency cap, daily budget cap
- ⏸ Phase F (Knowledge Base markdown library) deferred
- ⏸ Phase G (Celery + WebSocket) deferred — currently FastAPI BackgroundTasks + 2s polling

## 🔜 NEXT

### Phase 1 — MVP continuation (~3-4 weeks remaining)

**Sprint 1.4 — Daily Plan + Follow-ups (1-2 weeks)** ← READY TO START
See `docs/brain/04_NEXT_SPRINT.md` for full scope.
- Celery beat (cron 08:00 in workspace timezone)
- Daily plan generator: priority scoring × stage probability × AI urgency, packs into work hours
- 1-line task hint per item via MiMo Flash
- `daily_plans` table; rendered as real `/today` content (replaces empty state grouping)
- Follow-up reminder dispatcher (every 15 minutes); creates `activities` rows
- Auto-email reminders are drafts requiring manager click-to-send (ADR-007)

**Sprint 1.3-followons (parallel)** — when Sprint 1.4 needs Celery anyway
- Phase F: Knowledge Base markdown library + tag-based grounding
- Phase G: WebSocket progress for enrichment (replaces polling)

**Sprint 1.5 — Polish + Launch (1 week)**
- Notifications (in-app drawer + email digest)
- Audit log table + admin UI
- Empty/error states, mobile responsive Today/Lead Card
- Pipeline column virtualization (>200 cards)
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
