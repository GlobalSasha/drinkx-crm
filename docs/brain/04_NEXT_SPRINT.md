# Next Sprint: Phase 2 Sprint 2.3 — Multi-pipeline switcher

Status: **READY TO START** (after Sprint 2.2 merge / deploy / smoke check)
Branch: `sprint/2.3-multi-pipeline` (create from main once 2.2 lands)

## Goal

Phase 1 + Sprints 2.0 / 2.1 / 2.2 took DrinkX CRM from a working
single-pipeline system to a system of record for the conversation,
plus a wide pipe in/out of the data model, plus an inbound lead-capture
surface. The next ergonomic gap is **multi-pipeline support**.

Today every workspace has exactly one auto-bootstrapped pipeline (the
11-stage B2B template from Sprint 1.1). Real customers want at least
two:

- **Продажи (sales)** — the existing 11-stage B2B funnel
- **Партнёры (partners)** — much shorter funnel for distributor /
  reseller deals, different stage names, different gate criteria
- **Возвраты / гарантии (refunds)** — issue-tracker shape, mostly
  for после-продажного сопровождения
- **Лиды апсейла (upsell)** — separate from net-new sales, owned by
  account managers not BDRs

Sprint 2.3 closes the gap: a workspace can have N pipelines; the
manager switches between them via a dropdown in the `/pipeline`
header; «+ Новая воронка» lives in Settings; `/today` and
`/leads-pool` continue to show leads across ALL of the user's
pipelines (no switcher there — too distracting).

No new domains, no new vendors, no new AI capability. Estimated 3–4
days.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 2.2 left
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope
- `docs/brain/sprint_reports/SPRINT_2_2_WEBFORMS.md` — known issues
  (notification debounce, honeypot, sentry@nextjs activation, cross-
  workspace stage validation — 2.3 should fold the stage-validation
  carryover in)
- `docs/PRD-v2.0.md` §4 (Pipeline) — original spec contemplated
  multi-pipeline from day one (`pipelines.workspace_id` FK is already
  in the schema since Sprint 1.1)
- `docs/brain/03_DECISIONS.md` — ADR-007 still applies (no auto-actions
  on pipeline switch); look for any ADR mentioning «default pipeline»
  before committing to the FK shape
- Production state at sprint start: 4 app containers + 4 cron entries
  running, manager workflows for Pipeline / Inbox / Import / Export /
  Forms all live, Sprints 2.1 + 2.2 merged

## Scope

### ALLOWED

#### 1. Schema + backend (Group 1, ~1 day)

Migration `0013_default_pipeline`:

- `workspaces.default_pipeline_id` — `UUID NULL`, FK to
  `pipelines.id ON DELETE SET NULL`. Backfill: for each workspace,
  set `default_pipeline_id = (SELECT id FROM pipelines WHERE
  workspace_id = workspaces.id ORDER BY created_at LIMIT 1)`. The FK
  is nullable forever — `SET NULL` rather than `NO ACTION` so deleting
  the last pipeline (an admin-only destructive op we don't expose in
  v1) doesn't cascade-fail.
- No change to `pipelines` itself — `pipelines.workspace_id` FK is
  already there since Sprint 1.1.
- No change to `leads.pipeline_id` — already required since Sprint 1.2.

ORM:
- `Workspace.default_pipeline_id: Mapped[uuid.UUID | None]` +
  `default_pipeline: Mapped["Pipeline" | None]` relationship.

Services:
- `app.pipelines.services.list_for_workspace(session, workspace_id)`
  — paginated.
- `app.pipelines.services.create_pipeline(session, workspace_id, *,
  name, stages: list[StageIn])` — admin/head only at the router; auto-
  bootstraps stages from the explicit `stages` list (NOT the 11-stage
  B2B template — caller passes whatever they want). Workspace must own
  the call (auth dependency).
- `app.pipelines.services.delete_pipeline(session, workspace_id, *,
  pipeline_id)` — defensive: refuse with 409 if any leads are on it
  (return count); refuse with 409 if it's the workspace's
  `default_pipeline_id` (force the admin to set a new default first).
  Soft-delete via an `is_active` column on pipelines? Probably not —
  pipelines are workspace-internal, not embedded into landing pages
  the way forms are; a hard delete with the «move leads first» guard
  rail is enough.
- `app.pipelines.services.set_default(session, workspace_id, *,
  pipeline_id)` — flips `workspaces.default_pipeline_id`. Admin/head
  only. Validates the pipeline belongs to this workspace.

Routers:
- `GET /api/pipelines` — list workspace's pipelines + their stages.
  All roles.
- `POST /api/pipelines` — create. Admin/head.
- `PATCH /api/pipelines/{id}` — rename / reorder stages. Admin/head.
- `DELETE /api/pipelines/{id}` — defensive delete. Admin/head.
- `POST /api/pipelines/{id}/set-default` — set workspace default.
  Admin/head.

Tests (mock-only target ~10):
- create + auto-bootstrap stage list
- delete refuses when leads exist (409, returns count)
- delete refuses when target is default (409, forces re-default first)
- set_default rejects cross-workspace pipeline (404 from get-or-404)
- list returns only workspace-scoped pipelines
- create rejects non-admin (403 — auth dependency)

**Bundle the Sprint 2.2 carryover here:** add a service-layer check
in `forms.services.create_form` / `update_form` that
`target_pipeline_id` and `target_stage_id` belong to the form's
workspace. Cheap to fold in, single-test addition.

#### 2. Switcher dropdown UI (Group 2, ~1 day)

Frontend:

- `usePipelines()` hook against `/api/pipelines` with TanStack Query;
  staleTime 5 min (pipelines change once a quarter, not once a request).
- `useSetDefaultPipeline()` mutation — invalidates `['pipelines']` +
  `['me']` on success (the `me` payload should carry
  `default_pipeline_id` so the dropdown initial state is correct
  cold-load).
- `usePipelineStore` (zustand) — current `selectedPipelineId`. Persists
  to `localStorage` so a refresh stays on the same pipeline. Falls
  back to `me.default_pipeline_id` when nothing is in localStorage.

`/pipeline` page:

- Header dropdown to the LEFT of the existing «+ Импорт» / «Экспорт»
  buttons. shadcn/ui `Select` or a custom `<details>` widget — match
  whatever the rest of the app uses.
- Items: each pipeline's `name`, with the workspace default tagged
  «(по умолчанию)» in muted text.
- Selecting a pipeline updates the store + refetches lead lists with
  the new `pipeline_id` filter param.
- The drag-drop board re-renders against the selected pipeline's
  stages.

`/leads-pool`, `/today`:

- NO switcher — these surfaces aggregate across all the user's
  pipelines on purpose. Keep current behaviour.

Lead REST:

- `GET /api/leads` already accepts `pipeline_id` filter (Sprint 1.2);
  verify it's wired through. Backend ALREADY enforces workspace scope.
- `GET /api/leads/pool` already aggregates across the workspace; no
  change.

Tests: `pnpm typecheck` + `pnpm build` clean. No frontend unit tests
this sprint (consistent with Sprint 2.0 / 2.1 / 2.2 — backend mock
tests, frontend structural verification only).

#### 3. Settings panel — pipeline management (Group 3, ~1 day)

`/settings` page (NEW — currently doesn't exist as a real page in the
app, only stub navigation). Sections:

- **Воронки** — list of workspace pipelines + «+ Новая воронка» CTA.
  Each row: name, stage count, lead count, set-default button (or
  «по умолчанию» chip if it is), delete trash icon.
- `PipelineEditor` modal (similar shape to `FormEditor` from Sprint
  2.2 G3): name, drag-reorderable stage list with name + color +
  is_won/is_lost flags. Reuse `dnd-kit` from Pipeline drag-drop.
- Confirm-delete modal explaining the «can't delete with leads on it»
  rule.

Other settings sections (out-of-scope for this sprint, stub headings
only — full Settings panel is a Phase 3 surface): «Профиль»,
«Уведомления», «Интеграции», «API».

Auth:
- `/settings` accessible to all roles, but admin/head-only sections
  (Воронки, Интеграции) gated by `useMe().role`.

Tests: `pnpm typecheck` + `pnpm build` clean.

#### 4. Polish + sprint close (Group 4)

- Audit log emit hooks for pipeline.create / pipeline.delete /
  pipeline.set_default (we already log lead.create / lead.transfer /
  lead.move_stage / enrichment.trigger from Sprint 1.5).
- Notifications — when an admin sets a new default pipeline, fire a
  `system`-kind notification to all workspace members so their next
  `/pipeline` cold-load is the new default («Воронка по умолчанию
  изменилась на …»).
- AppShell: `/settings` nav item activates (currently disabled).
- Sprint report `SPRINT_2_3_MULTI_PIPELINE.md`.
- Brain memory rotation: 00 + 02 + 04 updates as usual.

### NOT ALLOWED (out of scope)

- **Pipeline templates / cloning.** A workspace creates a new pipeline
  from scratch in v1. Cloning «Продажи → Партнёры minus 5 stages» is
  a 2.4+ ergonomic.
- **Per-pipeline gate criteria configuration UI.** The gate engine
  already supports it via `stages.gate_criteria_json`, but we don't
  expose a UI for editing gate criteria in v1 — the bootstrap stage
  list covers the common case, and the seeded B2B template's gates
  are good defaults.
- **Multi-pipeline reporting (cross-pipeline funnel comparison).**
  Reporting / analytics is Phase 3.
- **Pipeline-level permissions.** «User X can only see Pipeline Y»
  is a 3.x permission model; v1 trusts workspace membership.

## Risks

1. **Migration 0013 backfill on a workspace with 0 pipelines** is a
   no-op (pipelines.workspace_id FK forces ≥0). Verify the bootstrap
   path on a fresh sign-in (`auth.bootstrap_workspace`) still seeds
   the default pipeline AND sets `default_pipeline_id` to its id.
2. **Pipeline switcher state leak between workspaces.** The
   `localStorage` key MUST be namespaced by `workspace_id`, otherwise
   a user who belongs to two workspaces sees stale selection on the
   wrong workspace. Use `drinkx:pipeline:{workspace_id}` as the key.
3. **Lead-list query performance** with the new `pipeline_id` filter
   — the existing `idx_leads_workspace_stage` index covers it, but
   verify `EXPLAIN ANALYZE` on a workspace with >5k leads.
4. **`SPRINT_2_2_WEBFORMS.md` carryover bundling.** Don't blow up
   2.3 scope by trying to also fix notification debounce + honeypot
   + Sentry@nextjs in this sprint. Stage-validation in form services
   is the only piece that fits naturally into the multi-pipeline
   work; the rest stays carryover.

## Done definition

- Migration 0013 applies cleanly via `alembic upgrade head` on staging.
- Backfilled `default_pipeline_id` non-null on all existing
  workspaces.
- `/pipeline` page renders a switcher dropdown; selecting a different
  pipeline reflows the board.
- `/settings` page exists with at least the «Воронки» section live.
- 10+ new mock tests (`test_pipelines_service.py` or similar).
  Combined baseline ≥127 mock tests passing.
- `pnpm typecheck` + `pnpm build` clean.
- Sprint report written, brain memory rotated.
- 0 new npm deps target (matches Sprints 2.0 / 2.1 / 2.2).

---

**Out-of-scope but parked here for awareness — fold into 2.4+:**

- AmoCRM adapter (Sprint 2.1 G5 deferred)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder, Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 carryover)
- Notification debounce on form-submission fan-out (Sprint 2.2 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- `pnpm add @sentry/nextjs` activation (Sprint 2.1 G10 carryover)
- pg_dump cron + Sentry DSNs (Sprint 1.5 soft-launch carryover)
- Phase G (Sprint 1.3) — move enrichment off FastAPI BackgroundTasks
  onto Celery; WebSocket `/ws/{user_id}` for real-time progress
- DST-aware cron edge handling
