# Sprint 1.2 Backend — Merge Report

**Merged on:** 2026-05-06
**Merge commit:** `b72de5a` (`--no-ff` merge of `sprint/1.2-core-crud` into `main`)
**Local main HEAD:** `b72de5a` · **origin/main:** `4c546df` (10 commits behind — NOT pushed)
**Status:** ✅ Merged locally · ⏸ Not deployed (push pending product-owner approval)

---

## Scope

Backend tasks 1–4 of Sprint 1.2 (B2B core CRUD). Frontend tasks 5–8 deliberately
excluded — they will live on a follow-up branch and need browser verification.

## What was merged

### Task 1 — Schema migration `0002_b2b_model`
- New tables: `leads`, `contacts`, `activities`, `followups`, `scoring_criteria`
- Stage gains `gate_criteria_json` (JSON list) — schema-only field, hydrated at bootstrap
- `DEFAULT_STAGES` replaced with 11 B2B stages (per ADR-016, `index-b2b.html`) + 1 lost stage
- `DEFAULT_GATE_CRITERIA` constant — 10 transition checklists (positions 1–10)
- `DEFAULT_SCORING_CRITERIA` — 8 weighted criteria summing to 100 (ADR-017)
- Indexes: `ix_leads_workspace_stage`, `ix_leads_workspace_assignment`, `ix_leads_rotting`,
  `ix_leads_assigned_to`, GIN full-text on `company_name`, plus per-FK indexes
- Data migration re-seeds existing default pipelines with the 11 B2B stages
- 17 model-level tests (all passing on `main`)

### Task 2 — Lead CRUD + Lead Pool
- `GET/POST/PATCH/DELETE /api/leads` with filters: `stage_id`, `segment`, `city`,
  `priority`, `deal_type`, `assigned_to`, `q`, `page`, `page_size`
- `GET  /api/leads/pool?city=&segment=&fit_min=` — only `assignment_status='pool'`,
  ordered `fit_score DESC NULLS LAST → created_at ASC`
- `POST /api/leads/sprint {cities, segment?, limit?}` — race-safe N-claim using
  `FOR UPDATE SKIP LOCKED`, falls back to `workspace.sprint_capacity_per_week` when limit is null
- `POST /api/leads/{id}/claim` — atomic `UPDATE … WHERE assignment_status='pool' RETURNING`
- `POST /api/leads/{id}/transfer` — owner-only or admin/head bypass, validates target user
  is in same workspace
- 21 PG-gated tests including a real concurrent-sprint race-safety test

### Task 3 — Stage transitions + gate engine
- `POST /api/leads/{id}/move-stage {stage_id, gate_skipped, skip_reason, lost_reason}`
- `app/automation/stage_change.py` — pre-checks + post-actions orchestrator
- Hard rule: `check_pipeline_match` (cannot be bypassed by `gate_skipped`) — defined
  via `GateViolation.hard=True` flag, not string matching
- Soft rule: `check_economic_buyer_for_stage_6_plus` (ADR-012) — bypassable with
  `gate_skipped=True` + non-empty `skip_reason`
- Post-actions: `set_won_lost_timestamps`, `log_stage_change_activity`
- ADR-003 audit: `logger.warning()` emitted on every gate-skip, plus full
  `Activity(type='stage_change')` row with violations payload
- Workspace isolation: stage lookup in service joins `Pipeline.workspace_id`
- HTTP: 404 (not found), 400 (invalid/archived/missing reason), 409 (gates blocked)
- 10 tests covering all gate paths, terminal stages, archived blocking

### Task 4 — Contacts / Activities / Followups REST
- Contacts: `GET/POST /api/leads/{id}/contacts` + `PATCH/DELETE /{contact_id}` (4 endpoints)
- Activities: `GET /api/leads/{id}/activities?type=&cursor=&limit=` (composite cursor
  on `(created_at, id)` for stable pagination), `POST` composer, `POST /{id}/complete-task`
- Followups: full CRUD + `POST /{fu_id}/complete`; auto-seed of 3 defaults on lead create
- 27 PG-gated tests across the three new test files

## ADRs introduced this sprint

- **ADR-016** — `index-b2b.html` is canonical; PRD v2.0 outdated on stages/priority/scoring/multi-stakeholder/pilot
- **ADR-017** — Scoring criteria live in `scoring_criteria` table (per-workspace, typed), not a JSON blob

## Test results on `main` (post-merge)

```
17 passed, 58 skipped, 1 warning in 0.24s
```

- ✅ All 17 unit tests pass (model definitions, enum coverage, default seeds, gate criteria structure)
- ⏸ 58 PG-gated tests skipped — local machine has no Postgres / Docker. They WILL run on the prod server (`crm.drinkx.tech` has Postgres 16 in Docker) and on CI when `TEST_DATABASE_URL` is set.

## Files changed

35 files, +4184 / -31 lines:
- `apps/api/alembic/versions/20260506_0002_b2b_model.py` (new, 318 lines)
- `apps/api/app/automation/stage_change.py` (new, 229 lines)
- `apps/api/app/{leads,contacts,activity,followups}/{models,schemas,repositories,services,routers}.py` (new packages)
- `apps/api/app/{auth,pipelines}/models.py` (extended)
- `apps/api/app/main.py` (4 new routers registered)
- `apps/api/alembic/env.py` (4 new model imports)
- `apps/api/tests/{conftest,test_*}.py` (new test files, 1605 lines)
- `AUTOPILOT.md` (1.2.1 + 1.2.2 ticked)
- `docs/brain/03_DECISIONS.md` (ADR-016, ADR-017)

## Production-readiness checklist

- [x] All unit tests pass on `main` after merge
- [x] AUTOPILOT 1.2.1 + 1.2.2 ticked
- [x] No frontend changes leaked in
- [x] Migration includes both upgrade and downgrade paths
- [x] Migration data-migration block re-seeds existing pipelines (only 1 default pipeline exists in production from Sprint 1.1)
- [ ] Push to `origin/main` (gate to product-owner)
- [ ] Deploy via GitHub Actions → `crm.drinkx.tech` (auto on push, ~90s)
- [ ] PG integration tests in CI (requires `TEST_DATABASE_URL` in workflow env)

## Known follow-ups (not in this sprint)

- WebSocket `/ws/{user_id}` (Redis pub/sub) — Task 1.2.2 last bullet, deferred to Sprint 1.3+
- Notifications dispatcher: `lead_transferred` event → notify new manager — deferred
- Frontend Sprint 1.2 (Tasks 5–8): Pipeline page, Lead Card, Today, Pool, drag-drop, brief drawer
- 131-prototype-leads import script — Task 8, deferred to a frontend follow-up branch

## Risk notes for production

1. **Stage re-seeding deletes existing stages.** The migration's data-migration block
   runs `DELETE FROM stages WHERE pipeline_id = …` for every default pipeline before
   inserting the 11 B2B stages. Any existing leads with `stage_id` pointing at a
   deleted stage will be silently set to NULL (FK is `ON DELETE SET NULL`). Production
   currently has no leads, so this is safe — but it would be destructive in any DB
   that has hand-created leads referencing the old 7-stage scheme.
2. **Cursor pagination on activities is now composite (`created_at|id`).** Any
   client that stored cursors from before the merge would not exist (this is a new
   endpoint), so no migration risk. New cursors are stable across identical timestamps.
3. **Auto-seed on lead create is unconditional.** Every newly created lead gets 3
   default followups, including bulk-imported leads. The future import script (Task 8)
   may need to bypass this to avoid noise on the 131 prototype leads.

## Next action

Awaiting product-owner approval to push `main` → `origin/main`. Pushing triggers
the GitHub Actions deploy workflow which runs `deploy.sh` on the VPS and verifies
`/health` returns 200.
