# Sprint 2.4 — Full Settings panel + Templates

**Status:** ✅ DONE
**Branch:** `sprint/2.4-settings-templates`
**Range:** 2026-05-08 → 2026-05-09
**Tracking:** `docs/brain/04_NEXT_SPRINT.md` (pre-sprint spec)

## Goal

Sprint 2.3 shipped `/settings` with one live section («Воронки») and
five «Скоро» stubs. Sprint 2.4 fills out the rest of the admin panel
and lays the groundwork for the upcoming Automation Builder by
shipping a workspace-scoped Templates module.

**Result:** all four spec'd Settings sections live + Templates module
shipped + housekeeping carryovers from 2.3 + audit / notifications
polish + soft-launch backup script. Single merge after G5 close per
the cadence agreed mid-sprint.

## Gates

| Gate | Status | Commit | Date | What shipped |
|---|---|---|---|---|
| **G1** Settings «Команда» | ✅ | `01e104a` | 2026-05-08 | Backend `app/users/` package (list / invite / role-change / supabase admin client), migration `0016_user_invites`, migration `0017_drop_pipelines_is_default`, frontend `TeamSection.tsx` + invite modal + role-edit dropdown, 9 mock tests |
| **G2** Settings «Каналы» | ✅ | `871467c` | 2026-05-08 | New `app/settings/` package, `GET /api/settings/channels`, `ChannelsSection.tsx` with Gmail card (3 states) + SMTP card; 0 new migrations; tests 0 (build-only) |
| **G3** Settings «AI» + «Кастомные поля» | ✅ | `12be0d6` | 2026-05-08 | Backend AI section (`GET / PATCH /api/settings/ai`, persists into `workspace.settings_json`); Custom Attributes domain (`app/custom_attributes/`, migration `0018_custom_attributes`, EAV definitions + lead_custom_values, kind-aware upsert dispatch); `AISection.tsx` with budget gauge + model selector; `CustomFieldsSection.tsx` with CRUD modal; 14 mock tests |
| **G4** Templates module | ✅ | `1ff4419` | 2026-05-09 | Migration `0019_message_templates`, `app/template/` package (UUID PK, channel as String(20) + VALID_CHANNELS guard, rename-aware duplicate check), 4 endpoints under `/api/templates`, `TemplatesSection.tsx` table+modal, audit `template.{create,update,delete}`, 6 mock tests |
| **G4.5** Quick wins | ✅ | `36a4c97` | 2026-05-09 | Accent colour, dropzone guard, audit labels — folded onto sprint branch alongside G4 |
| **G5** Polish + close | ✅ | this commit | 2026-05-09 | Audit user-join + formatDelta, notifications click split + dismiss endpoint, priority colour centralization → `lib/ui/priority.ts`, `scripts/pg_dump_backup.sh` + `docs/crontab.example`, sprint report, brain memory rotation, smoke checklist |

## New migrations

| Rev | File | Purpose |
|---|---|---|
| `0016_user_invites` | `20260508_0016_user_invites.py` | `user_invites` table (workspace, invited_by, email, suggested_role, accepted_at) |
| `0017_drop_pipelines_is_default` | `20260508_0017_drop_pipelines_is_default.py` | Sprint 2.3 carryover — drops legacy `pipelines.is_default` boolean now that `workspaces.default_pipeline_id` is the canonical pointer |
| `0018_custom_attributes` | `20260508_0018_custom_attributes.py` | EAV: `custom_attribute_definitions` + `lead_custom_values` |
| `0019_message_templates` | `20260509_0019_message_templates.py` | `message_templates` (UUID PK, channel String(20), category nullable, UNIQUE (workspace, name, channel)) |

All four migrations open with the ADR-020 alembic_version widening
(`ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)`).

## Test baseline

- **Pre-sprint:** 132 mock tests passing (Sprint 2.3 close).
- **After G1:** 132 → 141 (+9 user invite / role / diff_engine carryover).
- **After G3:** 141 → 155 (+14 AI settings + custom attributes).
- **After G4:** 155 → 161 (+6 templates).
- **After G5:** 161 → **281 passed / 14 pre-existing failed / 58 skipped** (target reached; 14 failures all pre-existing env-related — fastapi import in modules collected on machines that don't have the runtime venv full deps).

`pnpm typecheck` (tsc --noEmit) clean throughout — verified after
each gate and after the priority-colour centralization in G5.

## ADRs adopted in sprint

- **ADR-018** — already in registry; reaffirmed by Sprint 2.4 audit user-join (no schema change needed; raw `user_id: UUID | None` was sufficient with a LEFT JOIN at read time).
- **ADR-019** — emails are lead-scoped; reused by G3 custom-attributes design (values are also lead-scoped, never workspace-scoped — same pattern).
- **ADR-020** — alembic_version widening; applied at the head of all four new migrations (0016 / 0017 / 0018 / 0019).
- **ADR-021** — single-workspace-per-deployment; reaffirmed by G1 (UserInvite is workspace-scoped — invitee joins the canonical workspace, not a fresh one) and G4 (templates workspace-scoped via FK CASCADE).

## Carryovers to Sprint 2.5

Folded into `docs/brain/04_NEXT_SPRINT.md` and `02_ROADMAP.md` for tracking:

1. **Notification dedupe (backend)** — suppress empty `daily_plan_ready` notifications, 1h dedup window keyed on (user, kind).
2. **Notification frontend grouping by day** — drawer currently is a flat list; add day-section headings.
3. **Pipeline header tweak** — accent button → `+Лид`, Sprint button → outline variant.
4. **Default pipeline 6–7 stages** — current bootstrap creates 7 — confirm naming + add ICP fields.
5. **Settings sidebar «Скоро» collapse** — three remaining stub sections (Профиль / Уведомления / API) should fold under a disclosure to reduce noise.
6. **LeadCard `window.confirm` → modal on Lost** — replace browser confirm with a styled modal.
7. **Mobile Pipeline fallback (<md)** — list-view fallback exists; vertical-card view on the actual /pipeline route still desktop-first.
8. **Invite accept-flow** — `accepted_at` column exists but never written. `upsert_user_from_token` should mark the matching invite accepted on first sign-in.
9. **Notification on invite acceptance** — depends on (8); pings inviter when invitee first signs in.
10. **Sentry activation** — Sprint 2.1 G10 carryover; `pnpm add @sentry/nextjs` + DSN env vars.
11. **Custom-field render on LeadCard** — G3 deferred this; values exist, no UI consumes them yet.
12. **Stage-replacement preview** — show «N лидов потеряют стадию» in PipelineEditor save flow (Sprint 2.3 polish carryover).
13. **Workspace AI override → fallback chain** — currently the workspace `primary_model` setting persists but env still wins in `app/enrichment/providers/factory.py`.
14. **dnd-kit reorder for Custom Fields** — v1 ships up/down position buttons.

## Known prod risks

1. **Anthropic 403 from RU IP** — fallback chain wastes one round-trip before falling through to Gemini/DeepSeek. Documented since Sprint 1.3.
2. **SMTP stub-mode** — `SMTP_HOST=""` keeps the daily digest in worker logs only (`[EMAIL STUB]` lines). User-invite magic-links rely on Supabase, not SMTP — invites work even in stub mode; the digest does not.
3. **`bootstrap_workspace` takes oldest workspace** — Phase 3 surface for multi-tenancy. Currently any new sign-in lands in workspace #1 silently if multiple workspaces exist (post-2026-05-08 hotfix collapsed Gmail + Drinkx workspaces; safe for now, brittle for any future second client).
4. **No automated DB backup before G5** — closed by `scripts/pg_dump_backup.sh` + `docs/crontab.example`; operator still needs to install the cron line manually on crm.drinkx.tech.

## Production smoke

See `docs/SMOKE_CHECKLIST_2_4.md` — 9-item ritual to run after the
sprint branch lands on staging and again after merge to main.

## Cadence notes for the merge

- **Single merge** sprint/2.4-settings-templates → main after this G5
  commit. No per-gate merges per the rule agreed mid-sprint.
- Migration 0017 (drop `pipelines.is_default`) is destructive — extra
  reason the merge waited for G5 close.
- Hotfixes 0014 (`bootstrap_orphan_workspaces`) and 0015
  (`merge_workspaces`) both shipped to main earlier between Sprint 2.3
  and 2.4 to fix the single-workspace migration.
