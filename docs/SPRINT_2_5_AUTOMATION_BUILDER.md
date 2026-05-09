# Sprint 2.5 — Automation Builder

**Status:** ✅ DONE (G3 skipped by product decision)
**Branch:** `sprint/2.5-automation-builder`
**Range:** 2026-05-09 → 2026-05-09
**Tracking:** `docs/brain/04_NEXT_SPRINT.md` (pre-sprint spec)

## Goal

Sprint 2.4 G4 shipped the Templates data model + admin CRUD without a
consumer. Sprint 2.5 wires templates into actual outbound flows by
building the Automation Builder — a workspace-scoped configuration
of «when X happens, run Y» across three trigger sources
(`stage_change` / `form_submission` / `inbox_match`). Plus closes the
Sprint 2.4 carryovers around notification noise and the never-written
`accepted_at` column.

**Result:** four of five planned gates shipped; G3 (AmoCRM adapter)
dropped mid-sprint by product decision — the lead-import surface area
isn't blocking 2.5+ work and Bitrix24 already covers the «import
leads» story for ops. Real outbound dispatch for `send_template`
still stubs to an Activity row with `outbound_pending=True` — the
Automation Builder UX is the value, dispatch lands in 2.6.

## Gates

| Gate | Status | Commit | Date | What shipped |
|---|---|---|---|---|
| **G1** Automation Builder core | ✅ | `363b371` | 2026-05-09 | Migration `0020_automations` (automations + automation_runs); new `app/automation_builder/` package (models / schemas / repositories / services / routers / condition / render); 5 endpoints under `/api/automations`; trigger fan-out wired into `app/automation/stage_change.py`, `app/forms/lead_factory.py`, `app/inbox/processor.py`; 3 action handlers (send_template / create_task / move_stage); `/automations` page with builder modal + RunsDrawer; AppShell sidebar entry; 12 mock tests |
| **G2** Notification dedupe + day grouping | ✅ | `a3b48ad` | 2026-05-09 | `_has_recent_same_kind` helper + 1h dedup window in `notify()`; empty `daily_plan_ready` body suppression (regex on `^0\s+карточек`); `DEDUP_EXEMPT_KINDS` frozenset (`lead.urgent_signal`); NotificationsDrawer day grouping via Intl.DateTimeFormat ru-RU («Сегодня» / «Вчера» / «D MMM»); 5 mock tests |
| **G3** AmoCRM adapter | ⏭️ SKIPPED | — | — | Dropped by product decision — Bitrix24 covers the lead-import story; AmoCRM not blocking. Folded back into the long-tail backlog |
| **G4** Invite accept-flow | ✅ | `f32fe89` | 2026-05-09 | `_apply_pending_invite` helper in `app/auth/services.py`; both branches of `upsert_user_from_token` invoke it; `safe_notify(kind="invite_accepted")` to inviter (defensive on null `invited_by_user_id`); G2 dedupe applies automatically; 3 mock tests; no new migration (column from 0016 was the right shape) |
| **G5** Sprint close | ✅ | this commit | 2026-05-09 | Sprint report, brain memory rotation, smoke checklist additions, no code changes |

## New migrations

| Rev | File | Purpose |
|---|---|---|
| `0020_automations` | `20260509_0020_automations.py` | `automations` (workspace-scoped, trigger / condition / action shape) + `automation_runs` (append-only audit per fire). UUID PK; trigger / action_type as `String(40)` with service-layer guards (codebase pattern, no Postgres ENUM); UNIQUE-less; hot-path index `(workspace_id, trigger, is_active)` for the trigger fan-out reads |

ADR-020 alembic_version widening at the start. Migration 0021 was
spec'd for notification dedupe but G2 implemented dedup without a
schema change (existing `(user_id, created_at)` index was enough).

## Test baseline

- **Pre-sprint:** 281 mock tests passing (Sprint 2.4 close).
- **After G1:** 281 → 293 (+12 automation_builder service / condition / render / trigger fan-out).
- **After G2:** 293 → 298 (+5 dedup / day-group / exempt-set pin).
- **After G4:** 298 → 301 (+3 invite-accept / no-op / dedup-swallow).
- **After G5:** 301 unchanged (docs-only).

`pnpm typecheck` (tsc --noEmit) clean throughout — verified after
each gate. The 3 pre-existing test-ordering failures in
`test_pipelines_service` (when run after `test_notifications` because
the latter's sqlalchemy stub omits `sqlalchemy.exc`) are baseline
noise inherited from before Sprint 2.5; A/B-confirmed via git-stash
during G2 review.

## ADRs adopted in sprint

None new. Migration 0020 is data-model work, not architecture.

The trigger fan-out pattern (existing hot path → `safe_evaluate_trigger` →
swallow exceptions, log via structlog) reuses the Sprint 1.5
`safe_notify` shape — same «parent transaction must not roll back
because of a side-effect handler» principle, applied to the Automation
Builder layer.

## Carryovers to Sprint 2.6

Folded into `docs/brain/04_NEXT_SPRINT.md` and `02_ROADMAP.md`:

1. **Real outbound dispatch for `send_template`.** Currently stages
   an Activity row with `outbound_pending=True` instead of actually
   sending. Sprint 2.6 G1 wires the channel-aware sender (email via
   existing `app/notifications/email_sender.py`; tg + sms remain stub
   until proper providers land in 2.7+).
2. **Multi-step automation chains** («send email → wait 3 days →
   create task»). v1 is one trigger → one action; chains need a
   per-step queue and a wait-state.
3. **Pipeline header tweak** (accent button → `+Лид`; Sprint button → outline).
4. **Default pipeline 6–7 stages confirm + ICP fields** (light-touch DB seed change).
5. **Settings sidebar «Скоро» collapse** into a disclosure (3 stub sections currently visible).
6. **LeadCard `window.confirm` → modal on Lost.**
7. **Mobile Pipeline fallback (<md)** — vertical card layout on the actual `/pipeline` route.
8. **Custom-field render on LeadCard** (Sprint 2.4 G3 carryover; values exist, no UI consumes them).
9. **Stage-replacement preview** in PipelineEditor («N лидов потеряют стадию»; Sprint 2.3 carryover).
10. **Multi-clause condition UI** in the Automation Builder modal (backend supports n-clause AND/OR; frontend ships a single row in v1).
11. **dnd-kit reorder for Custom Fields position** (Sprint 2.4 G3 carryover).
12. **AmoCRM adapter** — back in the long-tail backlog after the G3 skip.

## Known prod risks

Same list as Sprint 2.4 close — 2.5 didn't add new ones:

1. **Anthropic 403 from RU IP** → wastes one round-trip in the
   fallback chain. Documented since Sprint 1.3.
2. **Sentry DSNs empty** → errors live in file logs + journalctl +
   ScheduledJob audit table.
3. **SMTP in stub-mode** (`SMTP_HOST=""`) — daily digest writes to
   worker logs only. Invite magic-links go via Supabase, not SMTP —
   those still work (verified G4 path doesn't need SMTP).
4. **`bootstrap_workspace` takes oldest workspace** — second client
   would silently land in workspace #1 (Phase 3 surface).
5. **pg_dump cron not installed on host** — script shipped in 2.4 G5,
   operator step still open.

## Production smoke

Sprint 2.5 additions live in `docs/SMOKE_CHECKLIST_2_5.md`
(supplement to the 2.4 checklist, not a replacement). Run the 2.4
checklist + the 7 new 2.5 checks after merge to main.

## Cadence notes

- Single merge `sprint/2.5-automation-builder` → main after G5,
  matching the Sprint 2.4 cadence.
- No destructive migrations in 2.5 (0020 is additive — drops two new
  tables on downgrade, leaves existing data alone).
- `send_template` ships intentionally as a stub — production users
  who configure a `send_template` automation will see the rendered
  body land as an Activity row with `outbound_pending=True`. This is
  visible in the lead's Activity Feed and in the run history; v1
  audit trail without dispatch wiring.
