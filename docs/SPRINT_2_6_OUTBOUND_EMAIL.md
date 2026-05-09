# Sprint 2.6 — Real outbound email + UX polish

**Status:** ✅ DONE (G2 multi-step chains skipped by product decision)
**Branch:** `sprint/2.6-outbound-email`
**Range:** 2026-05-09 → 2026-05-09
**Tracking:** `docs/brain/04_NEXT_SPRINT.md` (pre-sprint spec)

## Goal

Sprint 2.5 shipped the Automation Builder end-to-end with a stub
`send_template` action — Activity rows landed with
`outbound_pending=true` instead of actually delivering messages.
Sprint 2.6 flips the flag for the email channel + clears the Sprint
2.4 / 2.5 UX polish carryovers (LeadCard inline custom fields,
dnd-kit reorder, Pipeline header tweak, modal-on-Lost, settings
disclosure).

**Result:** four of five planned gates shipped; G2 (multi-step
automation chains) dropped mid-sprint by product decision — the
single-step automation surface is enough to validate the Builder,
multi-step lands when there's actual customer demand. Two rounds of
stability fixes landed mid-sprint after a code-review audit found
SMTP-during-DB-transaction + N+1 issues. tg / sms channels stay
stubbed until Sprint 2.7 picks providers.

## Gates

| Gate | Status | Commit | Date | What shipped |
|---|---|---|---|---|
| **G1** Real email dispatch | ✅ | `b740a76` | 2026-05-09 | New `app/email/sender.py` (tri-state True/False/EmailSendError contract); `_send_template_action` routes by `template.channel`; tg/sms keep `delivery_status='pending'`; 4 mock tests |
| **STB #1** SMTP outside transaction | ✅ | `cc8db53` | 2026-05-09 | New `app/automation_builder/dispatch.py` (contextvar-scoped queue + post-commit drainer); `_send_template_action` defers SMTP to drainer; `evaluate_trigger` wraps each action in `db.begin_nested()` SAVEPOINT; 3 trigger sites updated (inbox/forms/leads-router); whitespace-only email strip |
| **STB #2** Template 409 + bulk fetch | ✅ | `323aa85` | 2026-05-09 | `TemplateInUse` 409 guard on `delete_template` (refuses delete when active automation references the template via `action_config_json["template_id"]`); `followup_dispatcher` bulk-fetch leads via `WHERE id IN (...)` (was N+1 per due followup); 3 new tests |
| **G3** Pipeline + LeadCard polish | ✅ | `6f19d4d` | 2026-05-09 | +Лид → accent fill, Sprint button → outline; Settings sidebar «Скоро» disclosure (3 stub sections fold under `<details>`); LeadCard `LostModal` replaces `window.confirm` + `window.prompt`; mobile Pipeline polish (centralized priority chip + stage badge per card) |
| **G4** Custom fields inline + dnd-kit | ✅ | `df7bfc2` | 2026-05-09 | New `GET /api/leads/{id}/attributes` + `PATCH /api/leads/{id}/attributes` + `PATCH /api/custom-attributes/reorder`; new `CustomFieldsPanel.tsx` on LeadCard with inline editing per kind; `CustomFieldsSection.tsx` refactored to dnd-kit drag reorder; cross-workspace 403 defence; 4 mock tests |
| **G2** Multi-step automation chains | ⏭️ SKIPPED | — | — | Dropped by product decision. The single-step Automation Builder is enough to validate the Builder UX; multi-step (send → wait N days → action) lands when there's customer demand. Folded back to the long-tail backlog |
| **G5** Sprint close | ✅ | this commit | 2026-05-09 | Sprint report, brain rotation, smoke checklist additions |

## New migrations

**None.** Sprint 2.6 was a pure code sprint: SMTP integration on the
existing `automations` / `lead_custom_values` schema, plus polish.
The `position` column on `custom_attribute_definitions` (used by G4
reorder) has existed since migration 0018 (Sprint 2.4 G3) — no
schema delta needed.

## Test baseline

- **Pre-sprint:** 95 mock tests passing (Sprint 2.5 close).
- **After G1:** 95 → 99 (+4 email-sender + send_template routing).
- **After STB #1:** 99 → 100 (+1 whitespace-only email; existing tests adapted to deferred-dispatch contract).
- **After STB #2:** 100 → 108 (+3 template-in-use / bulk-fetch / lead-missing tests + 5 collateral test files newly collecting under the unified `__getitem__` stub fix).
- **After G3:** 108 unchanged (frontend-only).
- **After G4:** 108 → 112 (+4 string-typed upsert / cross-workspace 403 / reorder happy + partial-rejection).
- **After G5:** 112 unchanged (docs-only).

`pnpm typecheck` (tsc --noEmit) clean throughout — verified after
each gate. The 3 pre-existing test-ordering failures in
`test_pipelines_service` (when run after `test_notifications`,
sqlalchemy.exc not stubbed) remain inherited baseline noise; not
introduced or worsened by Sprint 2.6.

## Stability audit summary

A full bug-hunt was run mid-sprint (across all of `apps/api/app/`,
not just the changeset). Findings + status:

**CRITICAL** — all 3 fixed in `cc8db53`:
- ✅ SMTP-during-DB-transaction in `send_template` (deferred to post-commit drainer)
- ✅ Session poisoning on action handler exceptions (per-automation SAVEPOINT)
- ✅ Whitespace-only `lead.email` reaching SMTP header parser (strip + skip)

**HIGH** — 2 fixed in `323aa85`, 4 still open:
- ✅ Template delete silently breaks active automations (TemplateInUse 409 guard)
- ✅ N+1 in `followup_dispatcher` (bulk-fetch via `WHERE id IN (...)`)
- ⏸ Daily-plan / digest cron failures swallowed without Sentry (depends on Sentry activation, Sprint 2.7 G1)
- ⏸ Enrichment via FastAPI BackgroundTasks strands rows in `running` state on failure (Phase G carryover, Sprint 2.7 G4)

**MEDIUM** — 1 still open:
- ⏸ `inbox/processor.py` Celery dispatch failure leaves `inbox_item.status='pending'` permanently if Redis was down at write time

**LOW** — 4 noted, accepted:
- `audit.log()` swallows insert failures (defense-in-depth gap; needs Sentry first)
- `Activity` / `Contact` / inbox `Lead` reads not workspace-scoped at repository layer (routers gate today)
- `pipelines/services.py:232` swallow on default-flip notification fan-out (intentional)
- `forms/public_routers.py:74` swallow (intentional «public flow must not 5xx»)

**Net:** 0 CRITICAL remain. 2 of 4 HIGH fixed. The 2 unfixed HIGH
items both depend on Sentry activation (Sprint 2.7 G1) — surfacing
silent failures requires the surfacing surface to exist first.

## ADRs adopted in sprint

None new. Sprint 2.6 was implementation-shaped, not architecture-shaped.

The deferred-dispatch contextvar pattern in `dispatch.py` is a
codebase-local idiom rather than an ADR — it solves the specific
SMTP-after-commit problem without committing the project to «every
post-commit side-effect uses contextvars». Future side-effect dispatchers
(tg / sms in 2.7) can follow the same shape OR choose Celery-task-
based deferral; both are legitimate.

## Carryovers to Sprint 2.7

Folded into `docs/brain/04_NEXT_SPRINT.md` and `02_ROADMAP.md`:

1. **Sentry activation** (main infra driver) — frontend `pnpm add
   @sentry/nextjs`, backend DSN env vars, error boundaries on the
   high-traffic routes. Carryover since Sprint 2.1 G10. Required
   prerequisite for surfacing the cron-swallow + audit-log-swallow
   tech-debt.
2. **Multi-step automation chains** (Sprint 2.6 G2 skip) — send →
   wait N days → action. Migration `0021_automation_steps`,
   per-step run rows, Celery beat scheduler.
3. **Real tg / sms outbound dispatch** — Telegram bot library +
   SMS provider evaluation. Currently `delivery_status='pending'`
   forever for those channels.
4. **Enrichment → Celery** (Phase G carryover) — move off FastAPI
   BackgroundTasks, add WebSocket `/ws/{user_id}` for status
   updates. Closes the Sprint 2.6 audit's «strands rows in running»
   finding.
5. **inbox/processor Celery dispatch retry** — `inbox_item` stays
   pending if Redis is briefly down at write time.
6. **pg_dump cron install on host** — script lives at
   `scripts/pg_dump_backup.sh` since Sprint 2.4 G5; the operator
   step (copy into `crontab -e` on `crm.drinkx.tech`) is still open.
7. **Custom-field render on LeadCard polish carryovers** — boolean
   kind not yet supported (model has 4 kinds: text/number/date/select);
   inline-edit «autosave on blur» retry on transient errors;
   keyboard navigation between rows.

## Known prod risks

Same list as Sprint 2.5 close — Sprint 2.6 didn't add new ones, and
the 3 CRITICAL stability findings were fixed mid-sprint:

1. **Anthropic 403 from RU IP** → wastes one round-trip in the
   fallback chain. Documented since Sprint 1.3.
2. **Sentry DSNs empty** → errors live in file logs + journalctl +
   ScheduledJob audit table only. Sprint 2.7 G1 closes this.
3. **SMTP in stub-mode** in some envs (`SMTP_HOST=""`) — daily
   digest writes to worker logs only. Sprint 2.6 G1 added the same
   stub guard for `send_template` so the Activity Feed surfaces
   `delivery_status='stub'` instead of a misleading «sent».
4. **`bootstrap_workspace` takes oldest workspace** — second client
   would silently land in workspace #1 (Phase 3 surface).
5. **pg_dump cron not installed on host** — script shipped in 2.4
   G5; operator step still open.

## Production smoke

Sprint 2.6 additions live in `docs/SMOKE_CHECKLIST_2_6.md`
(supplement to the 2.4 + 2.5 checklists, not a replacement). 8 new
checks covering custom-fields inline editing, dnd-kit reorder,
template delete 409, accent +Лид button, mobile pipeline.

## Cadence notes

- Single merge `sprint/2.6-outbound-email` → main after this commit.
- 2 mid-sprint stability commits (`cc8db53`, `323aa85`) landed on
  the sprint branch in addition to the planned gates — full bug-hunt
  audit was the user's own decision after G1, valid course-correction.
  Documented per-finding in the commit messages.
- 0 destructive migrations in 2.6 (no migrations at all).
- `send_template` for tg / sms intentionally stays stubbed —
  flipping that requires picking real providers (Sprint 2.7+ G3
  scope).
