# Next Sprint: Phase 1 Sprint 1.2 — Core CRUD with B2B model

Status: **READY TO START**
Branch: `sprint/1.2-core-crud`

## Goal

Real pipeline with real leads, real drag-drop, real lead card.
Implements B2B model from `index-b2b.html` reference (11 stages,
gate criteria, two scorings, multi-stakeholder, deal type, priority A/B/C/D,
dual rotting, pilot contract, lead pool).

No AI yet. No external integrations. Pure CRUD + workflow.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what `index-b2b.html` implements
- `docs/brain/01_ARCHITECTURE.md` — backend structure
- `docs/brain/03_DECISIONS.md` — ADR-002 through ADR-015
- `docs/PRD-v2.0.md` §6.2, §6.3, §8.3
- Prototype `crm-prototype/index-b2b.html` (visual reference)
- Prototype `crm-prototype/docs/PRD-addition-v2.1-lead-pool.md`

## Scope

### ALLOWED

**Schema migration** (`alembic 0002_b2b_model`):
- Drop existing 7 stages from default pipelines, re-seed with **11 B2B stages**:
  ```
  1 Новый контакт   (prob=5,  rot=3,  is_won=F, is_lost=F)
  2 Квалификация    (prob=15, rot=5)
  3 Discovery       (prob=25, rot=7)
  4 Solution Fit    (prob=40, rot=7)
  5 Business Case   (prob=50, rot=5)
  6 Multi-stakeholder (prob=60, rot=7)
  7 Договор / пилот (prob=75, rot=5)
  8 Производство    (prob=85, rot=10)
  9 Пилот           (prob=90, rot=14)
  10 Scale          (prob=95, rot=14)
  11 Закрыто (won)  (prob=100, is_won=T)
  + Закрыто (lost)  (prob=0, is_lost=T) — separate, not in main flow
  ```
- Add `gate_criteria_json` to Stage (list of strings, configurable per workspace)
- Update `DEFAULT_STAGES` and `DEFAULT_GATE_CRITERIA` constants in
  `app/pipelines/models.py`

**New tables:**
- `leads` (PRD §8.3 + B2B fields):
  - basic: company_name, segment, email, phone, website, inn, source, tags_json
  - **B2B-specific:** deal_type (enum 6 values), priority (A/B/C/D),
    score (0-100, manager-set), fit_score (0-10, AI-set, NULL for now)
  - **Lead Pool:** assignment_status (pool/assigned/transferred), assigned_to,
    assigned_at, transferred_from, transferred_at
  - **Rotting:** next_action_at, is_rotting_stage (bool), is_rotting_next_step (bool),
    last_activity_at
  - **Pilot:** pilot_contract_json (embedded; populated when stage>=9)
  - lifecycle: created_at, updated_at, archived_at, won_at, lost_at, lost_reason

- `contacts`:
  - lead_id, name, title, role_type (enum: economic_buyer / champion /
    technical_buyer / operational_buyer), email, phone, telegram_url,
    linkedin_url, source, confidence (high/medium/low),
    verified_status (verified / to_verify), notes

- `activities` (polymorphic per type):
  - lead_id, user_id (author), type (comment / task / reminder / file / email /
    tg / system / stage_change / score_update)
  - payload_json (type-specific fields)
  - common: task_due_at, task_done, task_completed_at, reminder_trigger_at,
    file_url, file_kind, channel, direction, subject, body

- `followups`:
  - lead_id, name, due_at, status (pending/active/done/overdue),
    reminder_kind (manager / auto_email / ai_hint),
    notes, position, completed_at

- `workspaces.scoring_config_json` — 8 criteria with weights (default per ADR-004),
  per-workspace tunable

**Backend endpoints:**
- `GET/POST/PATCH/DELETE /api/leads`
- `GET /api/leads?stage=&segment=&city=&priority=&deal_type=&q=&page=` (filters)
- `GET /api/leads/pool?city=&segment=&fit_min=` (only `assignment_status=pool`)
- `POST /api/leads/sprint` body `{cities[], segment?, limit?}` — race-safe claim N
- `POST /api/leads/{id}/claim` (manual single-card take)
- `POST /api/leads/{id}/transfer` body `{to_user_id, comment?}`
- `POST /api/leads/{id}/move-stage` body `{stage_id, gate_skipped: bool, reason?}`
  → validates Economic Buyer presence for stage>=7
- `GET /api/pipelines/{id}/stages` with gate_criteria
- Nested `GET/POST/PATCH/DELETE /api/leads/{id}/contacts`
- `GET /api/leads/{id}/activities?type=&cursor=&limit=`
- `POST /api/leads/{id}/activities` (composer endpoint — type+payload)
- `GET/POST/PATCH/DELETE /api/leads/{id}/followups`
- `POST /api/leads/{id}/followups/{fu_id}/complete`
- WebSocket `/ws/{user_id}` (Redis pub/sub) — for activity stream + drag-drop sync

**Frontend (Next.js):**
- `app/today/page.tsx` — real Today screen (reads from /leads with assigned_to=me + sorting)
  Empty state when no leads.
- `app/pipeline/page.tsx` — Kanban with @dnd-kit, segment+city filter chips,
  "Сформировать план на неделю" button, AI Brief drawer on click
- `app/leads-pool/page.tsx` — Lead Pool table with filters + "Взять в работу"
- `app/leads/[id]/page.tsx` — Lead Card with 4 tabs:
  - Сделка: deal_type, priority, score with sliders, blocker, next step
  - Контакты: 4 role types, add/edit/delete
  - Scoring: 8 criteria sliders, auto Tier badge
  - Активность: composer (comment/task/reminder/file) + filtered feed
  - Pilot Contract (conditional, stage>=9)
- Brief drawer (port from prototype)
- TransferModal in lead card menu

**Migration script:**
- `apps/api/scripts/import_prototype_data.py` — one-shot loader
  Reads prototype's `data.js`, parses into Postgres
  Lead.assignment_status = 'pool' for all imported (managers will claim)

### FORBIDDEN

- AI features (Sprint 1.3)
- Inbox / email / Telegram (Phase 2)
- Quote/КП builder (Phase 2)
- Touching `apps/api/app/auth/` beyond adding `User` foreign-key references
- Real Supabase keys (continue stub mode)
- Modifying `crm-prototype` repo (it's reference only now)

## Tests required

- pytest: lead CRUD, including segment/city/priority filter
- pytest: `POST /leads/sprint` race-safe (concurrent calls, only one wins per card)
- pytest: stage transition rejected when Economic Buyer missing for stage>=7,
  unless `gate_skipped=true`
- pytest: contact CRUD with role_type enum
- pytest: activity polymorphic write+read for all 8 types
- pytest: followup auto-seed on lead create per default pipeline
- web: Playwright e2e "sign in (stub) → create lead → drag to next stage →
  add comment → mark task done"

## Deliverables

- All tables migrated on production server (auto via deploy)
- All endpoints documented in OpenAPI (FastAPI auto-generates)
- Frontend pages live at https://crm.drinkx.tech/today, /pipeline, /leads-pool, /leads/{id}
- `docs/brain/sprint_reports/SPRINT_1_2_CORE_CRUD.md` written
- Update `docs/brain/00_CURRENT_STATE.md`
- Update `docs/brain/02_ROADMAP.md`
- Update `docs/brain/04_NEXT_SPRINT.md` → next is Sprint 1.3 AI Enrichment

## Stop conditions

All tests pass → report written → committed → STOP
No push to main without product owner approval.
No scope creep into Sprint 1.3+ items.

---

## Recommended task breakdown (one PR per group)

1. **Schema** — migration 0002, models, tests of model creation/relations
2. **Lead CRUD + Pool** — endpoints, tests, OpenAPI
3. **Stage transitions + gates** — automation/stage_change.py with rule engine
4. **Contacts + Activities + Followups** — three sub-domains, REST + tests
5. **Frontend Pipeline + Brief drawer** — drag-drop, filter chips, sprint modal
6. **Frontend Lead Card** — 4 tabs with B2B fields, scoring sliders, pilot conditional
7. **Frontend Today + Pool page** — real data instead of placeholders
8. **Migration script + smoke** — import 131 prototype leads, verify in UI
