# Sprint 2.7 — Post-deploy smoke checklist

Supplement to `SMOKE_CHECKLIST_2_4.md` + `SMOKE_CHECKLIST_2_5.md` +
`SMOKE_CHECKLIST_2_6.md`, NOT a replacement. Run prior checklists
first; then the new 2.7 checks below. Both lists should run on
production after merge to main + auto-deploy.

Same rule as before: every row needs an actual visit in a logged-in
browser tab — DevTools Network tab open, "Preserve log" enabled,
zero non-2xx tolerated.

## Setup

- All Sprint 2.6 setup carries over (workspace seeded with user,
  pipeline, lead with valid email, message template channel='email',
  active automation pointing at the template, custom-attribute
  definitions).
- `SENTRY_DSN` may still be empty — telemetry-off is the production
  default and the smoke checks below are designed to pass either
  way. The Sentry-arrival items below are noted as **operator
  follow-on**, not blockers.

## New 2.7 checks

| # | Page / Flow | Verify |
|---|---|---|
| 1 | `/automations` — create single-action automation | Create an automation with trigger=stage_change, action=create_task. The «Цепочка после первого шага» fieldset shows «Без шагов — автоматизация однократная». Save → row appears in the table; refresh → still there. Trigger the automation by moving any lead into the matching stage; one Activity row of type=task appears on the lead. RunsDrawer shows the run with status=success and is NOT expandable (no chevron). |
| 2 | `/automations` — create multi-step chain | Same trigger as #1. Click «+ Пауза» → a step row appears with hours=24. Click «+ Задача» → second extra step. Save. Trigger the automation. RunsDrawer shows the run row WITH a chevron. Click chevron → per-step grid expands: step 1 shows status=success + executed timestamp; step 3 shows status=Ожидает + scheduled timestamp ~24h in the future. (Step 2 — the delay — does NOT appear in the grid; it's a gate, not a queued step.) |
| 3 | `/automations` — multi-step builder reorder | Add 3 extra steps. Use the ↑/↓ buttons to reorder. Save → reload page → reorder persists. The «Шаг N» numbering updates correctly (step 2 = first extra, etc.). |
| 4 | `/automations` — multi-step validation | Add «+ Пауза» step, set hours=0 → save → toast/error «Пауза должна быть от 1 до 720 часов». Add «+ Шаблон» step but don't pick a template → save → error «выберите шаблон». Backend `_validate_steps` returns 400 with `code: invalid_steps` if frontend validation is bypassed. |
| 5 | Beat scheduler — pending step fires | After check #2, manually wait OR shortcut via a 1-hour delay step instead of 24h. After 5+ min (next scheduler tick), the pending step row in RunsDrawer flips from «Ожидает» to «Успешно», `executed_at` populates. The lead's Activity Feed shows the step's side-effect (new task / Activity row). Worker logs show `automation.step_run` entries. |
| 6 | LeadCard render error — sentry-aware boundary | If `NEXT_PUBLIC_SENTRY_DSN` is set: deliberately trigger a render error on `/leads/{id}` (e.g. via DevTools console: `throw new Error("smoke-test")` inside a React event). The `(app)/error.tsx` boundary renders the «Что-то пошло не так» fallback with «Попробовать снова» button. Sentry receives the issue with `route` tag = the lead path + `boundary` tag = `(app)/error`. **If DSN is empty**, just verify the boundary renders the fallback — no Sentry traffic expected. |
| 7 | Cron swallow → Sentry capture (operator follow-on) | If `SENTRY_DSN` is set on backend: kill the daily-plan task mid-run (e.g. inject `raise RuntimeError("smoke")` in `daily_plan_runner.py` for one user via a debug branch). Sentry receives an issue fingerprinted `["daily-plan-cron", "user-failed"]` + tags `cron=daily_plan_generator`, `user_id=<id>` in extras. structlog WARNING line still emits. **If DSN is empty**, verify only the structlog line — no Sentry traffic. |
| 8 | Enrichment failure flips row to 'failed' | Trigger an enrichment run on a lead, then SIGKILL the api container mid-run (or roll back DB by stopping postgres briefly). Restart everything. Check the latest `enrichment_runs` row for that lead — `status='failed'`, `error` has truncated `RuntimeError: ...` or similar. If `SENTRY_DSN` set: Sentry issue fingerprinted `["enrichment-bg-run", "stranded"]` + run_id in extras. Pre-G1 this row would have stranded at `status='running'` forever. |
| 9 | Backwards-compat — legacy automations still fire | Verify pre-2.7 automations (single-action) still fire correctly after the migration. Trigger a stage_change for a lead matching a legacy automation → run row appears with status=success; per-step grid (if expanded — single-step automations still get a step 0 audit row) shows one row at step_index=0, status=success. The `automation_step_scheduler` cron tick logs zero scanned rows on its first run after deploy (no chains exist yet). |

## If anything fails

- **Don't merge** (or roll back the merge if already on prod).
- Capture the failing request payload + response in
  `SPRINT_2_7_SENTRY_MULTISTEP.md`'s production-readiness section.
- Hotfix pattern: `hotfix/{slug}` branch off main, fix + test, PR
  back. See `hotfix/single-workspace`,
  `hotfix/celery-mapper-registry` for the established shape.

## Operator notes

### Sentry stays optional

Both `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` (frontend)
default to empty. The G1 init path is gated:

- Backend: `app/observability.py:init_sentry_if_dsn(settings)` returns
  False when DSN is empty. `sentry_sdk.capture_exception` becomes a
  no-op when init never ran (Sentry SDK contract).
- Frontend: `apps/web/lib/sentry.ts:initSentry()` returns silently
  when `NEXT_PUBLIC_SENTRY_DSN` is empty. The lazy require of
  `@sentry/nextjs` doesn't fire — bundle size impact stays at zero
  until the operator opts in.

The smoke checklist passes either way. Sentry-specific items (#6
Sentry-arrival, #7 cron-arrival, #8 enrichment-arrival) downgrade
from «verify Sentry receives X» to «verify the structlog line
emits + behaviour is correct» when DSN is empty.

### Frontend `@sentry/nextjs` not yet installed

`lib/sentry.ts` has carried a lazy-require warn-once guard since
Sprint 2.1 G10. Until the operator runs `pnpm add @sentry/nextjs`,
even setting `NEXT_PUBLIC_SENTRY_DSN` won't activate Sentry — you'll
just see a one-shot console warning. Frontend telemetry is a
separate operator step from the merge.

### Multi-step automation step queue growth

`automation_step_runs` is append-only and grows over time. With a
delay-cap of 720h (30 days) and the partial index on
`(scheduled_at) WHERE executed_at IS NULL`, the hot-path query
stays fast even with millions of rows. Long-term, a cleanup job
could archive rows older than N months — Sprint 2.8+ if size
becomes an operator concern.

### Step 0 audit rows for legacy single-action automations

`evaluate_trigger` now writes an `automation_step_runs` row at
step_index=0 even for legacy single-action automations. This adds
one extra row per fire to the new table — negligible, and the
RunsDrawer per-step grid renders consistently for both shapes.
Existing audit reports that read `automation_runs` are unaffected
(parent table is unchanged in shape).

### Beat scheduler concurrency

`automation_step_scheduler` runs every 5 min. With Celery worker
concurrency=2 and the scheduler grabbing up to 200 due rows per
tick (`limit=200` in `list_due_step_runs`), the worst-case scenario
is ~24k steps/hour processable. Far above any realistic load.
