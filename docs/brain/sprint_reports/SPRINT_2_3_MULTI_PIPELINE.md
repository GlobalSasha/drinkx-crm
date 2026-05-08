# Sprint 2.3 — Multi-pipeline switcher

**Status:** ✅ Branch ready for product-owner review · 4/4 groups closed
**Period:** 2026-05-08 (single-day sprint)
**Branch:** `sprint/2.3-multi-pipeline` (NOT yet merged to main)
**Commit range:** `4294988..HEAD` (G1–G3) + this G4 close

---

## Goal

Phase 2 had three thirds done — Inbox (2.0) gave a real conversation
record, Bulk I/O (2.1) gave a wide pipe in/out of the data model,
WebForms (2.2) gave inbound lead capture. The next ergonomic gap was
**multi-pipeline support**: every workspace had exactly one
auto-bootstrapped pipeline (the 11-stage B2B template) since Sprint
1.1, even though `pipelines.workspace_id` always anticipated more.
Real customers wanted at least Продажи + Партнёры; some wanted
Возвраты and Апсейл too.

Sprint 2.3 closes the gap:

- a workspace can host N pipelines, each with its own stage list,
- the manager switches between them via a dropdown in `/pipeline`
  header (per-workspace localStorage memory),
- `/today` and `/leads-pool` keep aggregating across all of the
  user's pipelines (no switcher there — too distracting),
- `+ Новая воронка` lives on the new `/settings` page with a full
  drag-drop stage editor,
- the «which one is default» signal moves from the boolean
  `Pipeline.is_default` flag onto a canonical
  `Workspace.default_pipeline_id` FK.

No new domains, no new vendors, no new AI capability, no new npm
or Python deps. Smallest sprint in Phase 2 next to 2.2.

---

## Groups delivered

| # | Name | Commit | Files | Tests |
|---|---|---|---|---|
| 1 | Schema (migration 0013) + admin CRUD + forms cross-workspace validation carryover | `4294988` | 11 | 10 |
| 2 | Switcher dropdown + per-workspace localStorage + /pipeline reflow | `ae59f78` | 10 | — (build only) |
| 3 | /settings page + PipelineEditor (dnd-kit stages) + 3-branch delete flow | `eafdc8e` | 7 | — (build only) |
| 4 | Audit deltas + admin/head notify fan-out + sprint close (this) | (this) | 5 | 2 |

**Combined backend test suite (Sprint 2.3 deliverables):** 12
mock-only tests in `tests/test_pipelines_service.py`, 0 DB / 0 Redis
/ 0 network. Combined with Sprint 1.5 / 2.0 / 2.1 / 2.2 / 2.3
baseline: **129 mock tests passing**.

**Frontend:** `pnpm typecheck` + `pnpm build` clean throughout. **13
routes prerender** (was 12; `/settings` is the new one at 7.61 kB).
Zero new npm dependencies (the Sprint 2.0+ streak survives a fourth
sprint). Zero new Python deps.

---

## Architecture decisions

### `workspaces.default_pipeline_id` FK, not a separate join table

The «which pipeline is default» signal had two reasonable shapes:
keep `Pipeline.is_default` (boolean per row) or move to a single
canonical FK on the workspace. We picked the FK:

- Single source of truth. Two pipelines can't accidentally both
  carry `is_default=True` — no need for app-level invariants on
  every flip.
- `SET NULL` on the FK means deleting the last pipeline (an admin-
  only destructive op we don't expose in v1) doesn't cascade-fail.
- Joining workspace → default pipeline is now a one-hop FK lookup,
  no boolean filter.

`pipelines.is_default` is **kept as a redundant signal** for now —
diff_engine + the alembic backfill itself read it. Dropping the
column is a 2.4+ housekeeping pass; the new repo helper
`get_default_pipeline_id` reads the FK first and falls back to the
boolean so a workspace mid-migration is never «no default».

### Per-workspace localStorage namespace

The switcher state was a real footgun: a manager belonging to two
workspaces would otherwise see their `selectedPipelineId` from
workspace A leak into workspace B on the next page load. We
deliberately key the store as **`drinkx:pipeline:{workspaceId}`** —
risk #2 from `04_NEXT_SPRINT.md` — and the hydration walks
persisted → workspace default → first pipeline so a deleted
pipeline silently degrades to the workspace default rather than
blank.

### Single-pipeline workspaces show a chip, not a dropdown

Most production workspaces today still have exactly one pipeline.
Showing a chevroned dropdown that only contains that one item
implies «click here to switch» — false signal, bad UX. We render
the name in a non-interactive chip when `pipelines.length === 1`.
The «Управление воронками →» entry is also hidden in that branch
(admin can still reach `/settings` via the sidebar).

### Optimistic DELETE → 409 structured response, no pre-flight check

The G3 spec mentioned a «pre-flight check» endpoint to predict
whether DELETE would succeed. We did NOT add one — the actual DELETE
is the cheapest probe the backend can do, and the structured 409
detail (`code: pipeline_has_leads | pipeline_is_default`,
`lead_count`, `message`) carries everything the UI needs. Saves one
round-trip on the happy path and one endpoint definition in the API.

### `as any` cast convention for typedRoutes same-build new routes

Next.js `typedRoutes` regenerates the route map AFTER the same
`tsc` invocation that needs the type — so a brand-new route
(`/settings` lands in G3) can't be type-checked against itself
within one build. The codebase already standardised on
`// eslint-disable-next-line @typescript-eslint/no-explicit-any` +
`as any` for `<Link>` and `router.push()` to parameterized routes
(`/leads/${id}`, `/inbox`, etc.). G3's new `/settings` link follows
the same pattern. Documented; not a code smell.

### `form_submission` G4 carryover bundled, not split into a 2.4 ticket

G1 also folded in the Sprint 2.2 carryover for cross-workspace
target validation in `forms.services` (`target_pipeline_id` /
`target_stage_id` must belong to the form's workspace, and the
stage must be a child of the pipeline). The work is multi-pipeline-
adjacent and lives in 3 lines of plumbing — keeping it in 2.3
closes the loop while the schema is fresh in everyone's head.

---

## Known issues / risks

1. **Browser E2E smoke deferred to staging.** `/pipeline`,
   `/settings`, the switcher, the editor, the delete-conflict modals
   all need an authenticated Supabase session against a live API to
   render. `pnpm typecheck` + `pnpm build` cleanliness is the
   strongest local signal; an honest «verify in browser» needs a
   staging deploy with migration 0013 applied. Same precedent as
   Sprints 2.1 / 2.2.

2. **`as any` cast carryover in `PipelineSwitcher` + `AppShell`.**
   Documented as the typedRoutes limitation above. Removing them
   entirely fails compilation. They're cosmetic — every other Link
   in the app does the same thing — but worth flagging if Next.js
   ever ships a fix.

3. **Sentry `@sentry/nextjs` package still not installed.**
   Carryover from Sprint 2.1 G10. The browser-side init guard is
   wired (DSN check + lazy require) but the package isn't in the
   lockfile. One `pnpm add @sentry/nextjs` away from active.

4. **Per-stage gate-criteria editor not exposed.** The gate engine
   already supports `stages.gate_criteria_json` since Sprint 1.2 —
   the new PipelineEditor does NOT yet surface a UI for editing
   them. Phase 3 work; the seeded B2B template ships with sensible
   defaults.

5. **Pipeline cloning / templates not exposed.** A workspace
   creates each new pipeline from scratch in v1. Cloning «Продажи →
   Партнёры minus 5 stages» is a 2.4+ ergonomic, deferred per spec.

6. **Stage replacement on PATCH is full, not row-level merge.**
   The Settings editor sends the whole stage list back on every
   save. `leads.stage_id` is FK SET NULL so dropped stages don't
   cascade-delete leads, but a stale lead lands at `stage_id=null`
   until the manager reassigns. The UI currently doesn't surface
   this loudly; a proper «N лидов потеряют стадию» preview is a
   nice 2.4 polish item.

7. **No multi-pipeline reporting.** Cross-pipeline funnel comparison
   (e.g. «conversion in Партнёры vs Продажи») is Phase 3.

8. **Notification fan-out has no debounce.** A flurry of
   set-default flips would page every admin once per flip.
   Acceptable for a config event that fires roughly never; revisit
   if we see real abuse. Same shape as the Sprint 2.2 form-submit
   notification fan-out (also un-debounced).

---

## Production readiness checklist

- [ ] **Migration `0013_default_pipeline` applies cleanly.** Auto-
      applies via the api Dockerfile entrypoint
      (`uv run alembic upgrade head && uv run uvicorn`). After first
      deploy verify `alembic_version` shows `0013_default_pipeline`
      and `SELECT id, default_pipeline_id FROM workspaces` is
      non-null on all rows (the two-pass backfill should land it).

- [ ] **Smoke (staging then prod):**
      1. Sign in as admin → open `/settings` → click «+ Новая
         воронка».
      2. Name it «Партнёры», drag-reorder a couple of stages,
         change a color, save.
      3. Go to `/pipeline` → confirm the dropdown now lists both
         «Новые клиенты» (default chip) and «Партнёры».
      4. Click «Партнёры» → board reflows, columns match the new
         stage list.
      5. Reload — same selection persists (localStorage).
      6. Back to `/settings` → click «Сделать основной» on
         «Партнёры». Reload — `me.workspace.default_pipeline_id`
         and the «по умолчанию» chip have moved.
      7. Bell drawer (admin) shows a new «Основная воронка
         изменена» notification.
      8. Try to delete «Партнёры» → 409 friendly modal explains
         it's the default. Set «Новые клиенты» as default again,
         try delete → 409 friendly modal explains there are leads.
         Move the leads (or accept), delete succeeds.

- [ ] **Audit log verified.** Each step above should land an
      `AuditLog` row with `action ∈ {pipeline.create,
      pipeline.delete, pipeline.set_default}` visible at `/audit`.

- [ ] **Cross-workspace isolation.** Two-workspace test account
      (if available): switching workspaces shouldn't leak
      `selectedPipelineId` because the localStorage key is
      namespaced by workspace_id.

---

## Files changed (cumulative across G1–G4)

```
apps/api/
  alembic/versions/20260508_0013_default_pipeline.py    # G1
  app/auth/models.py                                     # G1 default_pipeline_id FK + foreign_keys disambiguation
  app/auth/schemas.py                                    # G2 WorkspaceOut.default_pipeline_id
  app/auth/services.py                                   # G1 bootstrap sets default_pipeline_id
  app/forms/routers.py                                   # G1 maps WebFormInvalidTarget → 400
  app/forms/services.py                                  # G1 _validate_target carryover
  app/leads/repositories.py                              # G2 pipeline_id filter on list_leads
  app/leads/routers.py                                   # G2 pipeline_id query param
  app/pipelines/models.py                                # G1 Pipeline.workspace foreign_keys
  app/pipelines/repositories.py                          # G1 get_by_id / count_leads / get_default_pipeline_id / create / rename / replace_stages / hard_delete / set_default / stage_belongs_to_pipeline
  app/pipelines/routers.py                               # G1+G4 5-endpoint admin CRUD with audit emits
  app/pipelines/schemas.py                               # G1 StageIn / PipelineCreateIn / PipelineUpdateIn
  app/pipelines/services.py                              # G1+G4 PipelineNotFound / PipelineHasLeads / PipelineIsDefault + admin/head notify fan-out
  tests/test_pipelines_service.py                        # G1+G4 12 mock-only tests

apps/web/
  app/(app)/pipeline/page.tsx                            # G2 reads selectedPipelineId, falls back to me.workspace.default_pipeline_id
  app/(app)/settings/page.tsx                            # G3 left-sidebar layout + section stubs
  components/layout/AppShell.tsx                         # G3 «Настройки» nav item
  components/pipeline/PipelineHeader.tsx                 # G2 mounts PipelineSwitcher
  components/pipeline/PipelineSwitcher.tsx               # G2 chevroned dropdown / single-pipeline chip / outside-click close
  components/settings/PipelineEditor.tsx                 # G3 dnd-kit stage editor with color + rot_days
  components/settings/PipelinesSection.tsx               # G3 table + 3-branch delete flow
  lib/hooks/use-leads.ts                                 # G2 LeadFilters.pipeline_id
  lib/hooks/use-pipelines.ts                             # G2+G3 real /api/pipelines + useSet/Create/Update/DeletePipeline
  lib/store/pipeline-store.ts                            # G2 selectedPipelineId + workspace-namespaced localStorage
  lib/types.ts                                           # G2+G3 WorkspaceOut.default_pipeline_id, StageIn, PipelineCreateIn, PipelineUpdateIn, PipelineDeleteConflict

docs/brain/
  00_CURRENT_STATE.md                                    # G4 Sprint 2.3 marked DONE
  02_ROADMAP.md                                          # G4 Sprint 2.3 → DONE, 2.4 promoted
  04_NEXT_SPRINT.md                                      # G4 rewritten for Sprint 2.4
  sprint_reports/SPRINT_2_3_MULTI_PIPELINE.md            # this report
```

25 files touched (G1–G3) + 5 in G4 = 30 files cumulative,
~2750 net lines added.

---

## Next sprint pointer

**Phase 2 Sprint 2.4 — Full Settings panel + Templates.** See
`docs/brain/04_NEXT_SPRINT.md`. Settings gains «Команда» / «Каналы»
/ «AI» / «Кастомные поля» sections and a new Templates module
(message templates for the Automation Builder coming in 2.5).

Outstanding deferred work to fold into 2.4+ housekeeping or 2.5:

- AmoCRM adapter (Sprint 2.1 G5 deferred)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder (Sprint 2.0 deferred)
- Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 carryover)
- Notification debounce on form-submission fan-out (Sprint 2.2 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- `pnpm add @sentry/nextjs` activation (Sprint 2.1 G10 carryover)
- pg_dump cron + Sentry DSNs (Sprint 1.5 soft-launch carryover)
- Per-stage gate-criteria editor (Phase 3)
- Pipeline cloning / templates (Sprint 2.4+)
- Cross-pipeline reporting (Phase 3)
- Stage-replacement preview «N лидов потеряют стадию» (2.4 polish)
- Drop legacy `pipelines.is_default` boolean (2.4 housekeeping)
- DST-aware cron edge handling
