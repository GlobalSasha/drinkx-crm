# Sprint 1.5 — Polish + Launch Report

**Status:** ✅ Branch ready for product-owner review · 8/8 groups closed
**Period:** 2026-05-07 (single-day sprint)
**Branch:** `sprint/1.5-polish-launch` (NOT yet merged to main)

---

## Goal

Finish what's needed to put the DrinkX team on this CRM full-time. Less new
product surface, more polish: in-app notifications, audit trail, daily email
digest, mobile responsive pass, Lead Card header polish, and two small copy /
layout fixes. No new vendor dependencies; no Phase 2 features bleed in.

---

## Groups delivered

| # | Name | Commit | Files | Tests |
|---|---|---|---|---|
| 1 | Notifications backend | `f3e0509` | 13 (api) | 7 (Postgres-backed) |
| ↳ | Verification fixes — `lead.assigned_to` recipient + mock-only tests | `ac04920` | 2 (api) | 10 (mock, no DB) |
| 2 | Notifications frontend (bell + drawer + 30s polling) | `c353367` | 4 (web) | — (build only) |
| 3 | Audit backend — table + helper + REST + 4 hooks | `bc44ccd` | 13 (api) | 7 (mock, no DB) |
| 4 | Audit frontend — admin-only `/audit` page | `2f118f5` | 7 (web) | — (build only) |
| 5 | Daily email digest — Celery task + stub mode | `6f2f0c0` | 12 (api) | 5 (mock, no DB / SMTP) |
| 6 | Mobile responsive pass | `265b7aa` | 6 (web) | — (build only) |
| 7 | Lead Card header polish — chips + Won/Lost banner + Transfer modal | `a11ce79` | 4 (web) | — (build only) |
| 8 | Small fixes (ICP copy, sticky header audit, sprint report) | this commit | 5 (web/docs) | — |

**Combined backend test suite:** 22 passed, 0 skipped, 0 errors, 0 DB. Mock
harness shared across notifications / audit / digest tests; one regression
caught in the verification pass (sqlalchemy stub `_Callable` was missing
rich-comparison operators — fixed across all three suites).

**Frontend:** `tsc --noEmit` clean and `next build` clean throughout. No new
npm dependencies. Sizes: `/today` 8.4 kB, `/pipeline` 28 kB, `/leads/[id]`
23.4 kB, `/audit` 3.5 kB.

---

## What shipped

### Group 1 — Notifications backend (`f3e0509` + `ac04920`)
- Migration `0006_notifications` — workspace_id (CASCADE) / user_id
  (CASCADE) / kind(40) / title(200) / body / lead_id (SET NULL) / read_at /
  created_at + (user_id, created_at DESC) and (user_id, read_at) indexes.
- `app/notifications`: `Notification` ORM, schemas, services
  (`notify` / `safe_notify` / `list_for_user` / `mark_read` /
  `mark_all_read`), router (`GET /notifications`,
  `POST /notifications/{id}/read`, `POST /notifications/mark-all-read`).
- Same-tx semantics — `notify()` only stages a row; caller commits, so the
  notification rolls back together with the parent action on failure.
- Cross-user mutation guard on `mark_read` (returns `None` for rows that
  belong to another user).
- Hooks at emit points:
  - `lead.transfer_lead` → `lead_transferred` for new owner
  - `enrichment.orchestrator` → `enrichment_done` / `enrichment_failed` for
    the **lead's current owner** (`lead.assigned_to`, fixed in `ac04920`
    after originally pointing at `run.user_id`).
  - `daily_plan.generate_for_user` → `daily_plan_ready`
  - `followups.dispatcher` → `followup_due` per emitted reminder
    (defensive try/except, never fails the cron tick)

### Group 2 — Notifications frontend (`c353367`)
- Lifted `relativeTime(iso)` into `lib/relative-time.ts` (shared with audit
  page in group 4).
- `useNotificationsBadge` (lightweight `page_size=1` poll for the count) +
  `useNotificationsList` (drawer body) + `useMarkRead` /
  `useMarkAllRead`. 30s `refetchInterval`,
  `refetchIntervalInBackground=false` so tabs don't burn API quota.
- `NotificationsDrawer` — right-side slide-in, Esc-close, backdrop, segmented
  filter (Непрочитанные / Все), per-row unread dot + kind chip + relative
  time. Click-row → mark read + navigate when `lead_id` is set.
- AppShell bell button between nav and Phase-2 disabled items, badge with
  count (capped "99+").

### Group 3 — Audit backend (`bc44ccd`)
- Migration `0007_audit_log` — workspace_id (CASCADE) / user_id (SET NULL,
  NULL = system) / action(60) / entity_type(40) / entity_id / delta_json /
  created_at, with (workspace_id, created_at DESC) and (entity_type,
  entity_id) indexes.
- `app/audit`: `AuditLog` ORM (no TimestampedMixin — explicit `created_at`),
  `audit.log()` defensive helper, repository, schemas, admin-only router
  scoped to caller's workspace via `require_admin` dependency.
- Reads NOT audited; cron's own `ScheduledJob` writes NOT re-audited (already
  covered by that table).
- Four emit hooks:
  - `leads.create_lead` → `lead.create` `{company_name, stage_id}`
  - `leads.transfer_lead` → `lead.transfer` `{from, to}`
  - `leads.move_lead_stage` → `lead.move_stage` (only on success;
    `StageTransitionBlocked/Invalid` raises before audit fires)
  - `enrichment.trigger_enrichment` → `enrichment.trigger` `{run_id}`
- `daily_plan.regenerate` audit deferred — Celery task user-context handling
  is a Phase 2 concern.

### Group 4 — Audit frontend (`2f118f5`)
- New `useMe()` hook against `/auth/me` — backend role / workspace info that
  Supabase JWT alone doesn't carry. Generous staleTime; no
  refetchOnWindowFocus.
- `useAuditLog({entity_type?, entity_id?, page})` — staleTime 30s, no
  polling.
- `/audit` page — header + 5 filter chips (All / lead.create /
  lead.transfer / lead.move_stage / enrichment.trigger) + table (Время /
  Действие / Сущность / Пользователь / Изменения) + pagination. Loading
  skeleton, error retry, empty state. Admin-only route guard via
  `useMe()` (waits for `me` to resolve before deciding — prevents admin
  from briefly bouncing to `/today`).
- AppShell adds an admin-only "Журнал" item with `History` icon (no new
  icon dep).

### Group 5 — Daily email digest (`6f2f0c0`)
- 5 SMTP env vars + `Settings` fields. Stub mode is on while
  `SMTP_HOST=""` (mirrors ADR-014). aiosmtplib added as runtime dep.
- `email_sender.send_email(to, subject, html)` → `bool`, never raises.
  Lazy aiosmtplib import so stub-mode envs don't need the package.
- `templates/daily_digest.html` — inline-CSS, no images, str.format
  placeholders only (no Jinja).
- `digest.build_digest_for_user(...)` — top-5 daily plan items + top-5
  overdue follow-ups + top-5 yesterday's succeeded enrichments. All three
  empty → skip (return False).
- `digest_runner.run_daily_digest_for_all_users` iterates active users
  (last_login within 30d), filters local-hour=8.
- New Celery task `daily_email_digest` + beat entry `crontab(minute=30)`.
  Combined: digest fires at 08:30 local time, 30 min after the plan
  generator at 08:00.

### Group 6 — Mobile responsive pass (`265b7aa`)
- AppShell: `block md:grid` toggle so the 220px column only applies at
  md+; on narrow viewports, sidebar slides in as overlay via
  hamburger ☰. Auto-closes on route change.
- `/today`: flex-wrap header, `px-4 sm:px-6` gutters, 44px tap-target
  pagination buttons on <sm, "Пересобрать план" → "Пересобрать" on <sm.
- `/leads/[id]`: body container stacks (`flex-col md:flex-row`) — rail
  ABOVE tab body on mobile. Tab bar swaps to `<select>` on <sm via one
  controlled `activeTab` state. Action group `flex-wrap` so
  Передать/Won/Lost/Стадия wrap instead of pushing the company name
  off-screen. `px-4 sm:px-6` gutters.
- `/pipeline`: new `PipelineList` component (read-only flat list grouped
  by stage); `<div className="md:hidden">` swaps Kanban for list on
  narrow viewports. PipelineHeader gets `flex-wrap` + shorter
  "План на неделю" label on <sm. Touch drag-drop is intentionally OUT
  (PRD §8.6).

### Group 7 — Lead Card header polish (`a11ce79`)
- `lib/i18n.ts`: `DEAL_TYPE_LABELS` / `dealTypeLabel()` (extracted from
  LeadCard's local map), `PRIORITY_LABELS` / `priorityLabel()` ("Приоритет
  A/B/C/D").
- `useTransferLead()` hook — `POST /leads/{id}/transfer` `{to_user_id,
  comment}`, invalidates `["lead"]` + `["leads"]`.
- `TransferModal` (new) — UUID input for the recipient (no `/api/users`
  endpoint exists yet — pasting UUID is the agreed stop-gap), optional
  comment, client-side UUID validation, surfaces backend 400/403/404
  inline.
- LeadCard chips per spec: Stage / Priority "Приоритет X" / Deal type /
  Score "{score}/100" with band colors / fit_score "AI {fit}/10" with
  band colors. Removed the now-redundant separate tier pill.
- Won/Lost banner below chips (green ✓ / rose ✗) with `won_at` / `lost_at`
  date, plus `lost_reason` when present. Won/Lost buttons disabled when
  the lead is already in that terminal stage. Lost flow now confirms via
  `window.confirm` before prompting for a reason.
- "Стадия" → "Сменить стадию" label.

### Group 8 — Small fixes (this commit)
- `AIBriefTab.tsx` empty-state copy: "ICP" → "портретом идеального
  клиента". One string replacement.
- Pipeline sticky header — confirmed as already correctly anchored. The
  page is `<div className="flex flex-col h-screen bg-canvas
  overflow-hidden">`; PipelineHeader is the first flex item and
  PipelineBoard owns its own `overflow-x-auto`. Horizontal scrolling
  happens INSIDE the board container; the header (outside it) cannot
  move with the columns. No `sticky top-0 z-10` needed — flex-column
  structural pinning is the equivalent.
- Sprint report + brain memory updates (this file + 00_CURRENT_STATE +
  02_ROADMAP + 04_NEXT_SPRINT).

---

## Decisions made during the sprint

- **`notify()` stages on the caller's session, never commits its own
  transaction.** Notifications and the action that caused them roll back
  together. `safe_notify()` swallows exceptions for cron / orchestrator
  paths.
- **Notification recipient for enrichment events is `lead.assigned_to`,
  not `run.user_id`.** Caught during the verification pass — the user
  who *triggered* an enrichment isn't necessarily the person who'd act
  on the resulting AI Brief by the time it lands. Documented in
  `ac04920` and the verification report.
- **Mock-only tests for new domains** (notifications / audit / digest).
  Same sqlalchemy-stub harness pattern used by Sprint 1.3 / 1.4 routes
  tests. Three test files share the harness; rich-comparison operators
  (`__lt__` / `__le__` / `__gt__` / `__ge__`) added so the digest's
  `Followup.due_at < now` query survives.
- **Audit reads / cron's own ScheduledJob writes are NOT audited.** Reads
  have no security value at this scale; ScheduledJob is the existing
  cron audit and re-recording would just duplicate.
- **`/api/audit` always scopes to `current_user.workspace_id`.**
  `workspace_id` is never accepted as a query param — prevents an admin
  in workspace A from poking at workspace B's audit via crafted URL.
- **Email digest in stub mode by default.** `SMTP_HOST=""` → `[EMAIL
  STUB]` log line instead of real send. Production env stays in stub
  mode until a real SMTP relay is provisioned; the Celery task and
  beat tick already work end-to-end (logs prove it).
- **TransferModal takes UUID input, not a user picker.** No `/api/users`
  listing endpoint yet; adding one was out of scope for group 7. Spec
  acknowledged "minimum viable". Future replacement is straightforward.
- **Mobile is overlay sidebar via hamburger, not push-content.** Push
  pattern at <md would steal too much horizontal space (220 / 375 = 59%);
  overlay gives the user the full viewport when the drawer is closed.
- **Pipeline list view is the mobile fallback for the Kanban.** PRD
  §8.6 already declared touch drag-drop out of scope; a flat read-only
  grouped list is the agreed substitute.
- **`useMe()` hook** instead of plumbing role through Zustand. Single
  TanStack Query keyed `["me"]`, mounted once in AppShell, reused by
  the audit page. Generous staleTime since role changes rarely.

---

## Known issues / risks

1. **Tab content overflow on mobile, not exhaustively audited.** Group 6
   added `min-w-0` and stacking; individual tab components
   (DealTab / ScoringTab / AIBriefTab / ContactsTab / ActivityTab /
   PilotTab) were not reviewed for hard-coded grids or wide tables.
   If a tab horizontally scrolls at 375px, point-fix with
   `overflow-x-auto` after on-device verification.

2. **TransferModal UUID input.** Receiver-side UX is rough until a
   `/api/users` listing exists — the manager must paste a UUID. The
   backend already validates the user is in the same workspace, and the
   modal surfaces the 400 inline.

3. **Email digest stub mode not yet verified in production.** Container
   restart after deploy will register the new beat entry. First firing
   is at the first `crontab(minute=30)` UTC tick where any user has
   `local_hour == 8`. With one MSK user, that's 05:30 UTC daily. Verify
   the next morning that `[EMAIL STUB]` lines appear in `drinkx-worker-1`
   logs and a `daily_email_digest` audit row lands in `scheduled_jobs`.

4. **`lead.assigned_to` may be NULL on system-imported leads.**
   Notifications hooks already skip when `assigned_to is None`; audit
   `lead.create` records `user_id=current_user_id` regardless, so admin
   imports show the operator's id correctly.

5. **Cron retry on per-user failure** — still no retry queue (Sprint 1.4
   carryover). One LLM time-out → that user gets no plan / no digest
   that day. Acceptable for soft launch; revisit when we have data on
   how often it actually happens.

6. **Pre-existing pre-Sprint 1.5 carryover risks (still open):**
   - Anthropic 403 from RU IP wastes one fallback round-trip per AI call.
   - DST edge cases on the daily plan / digest cron (hour skipped or
     duplicated).
   - `fit_score` last-writer-wins between orchestrator and the manual
     scoring tab.

---

## Production readiness — Soft Launch Checklist

From `04_NEXT_SPRINT.md` §8 "Soft launch checklist". Status as of sprint close:

| Item | Status | Notes |
|---|---|---|
| Production .env complete (Sentry DSNs, all AI keys) | ⏸ | Sentry DSNs still empty; AI keys live (MiMo / Anthropic / Brave). SMTP empty by design (stub mode). |
| First daily plan generation runs successfully on a real timezone | ✅ | Verified during the in-sprint debugging session — `regenerate_for_user` fires, `generate_for_user` ran 24 items in 27s. `scheduled_jobs` shows `daily_plan_generator` succeeded at 13:00 UTC. |
| End-to-end smoke (sign in → enrich → see brief → drag stage → mark followup) | ⏸ | Not yet performed against this branch. Each step works individually; cross-step verification pending merge to main + deploy. |
| Backups: pg_dump cron on the VPS | ⏸ | NOT addressed in 1.5. Defer to Phase 2 or a dedicated infra sprint. |
| Onboarding doc for first-time users | ⏸ | NOT written in 1.5. |
| Review log volume across api / worker / beat | ⏸ | Manual review after deploy. Current logs are reasonable in non-load conditions; verify under real traffic. |

✅ = done in this sprint · ⏸ = open / deferred

---

## Files changed (cumulative — all 8 groups)

### Backend (apps/api)

```
alembic/versions/
  20260507_0006_notifications.py            (group 1)
  20260507_0007_audit_log.py                (group 3)
alembic/env.py                              (group 1, 3 — model registrations)

app/audit/                                   (group 3 — new domain)
  __init__.py
  audit.py                                  (defensive log() helper)
  models.py
  repositories.py
  routers.py
  schemas.py

app/notifications/                           (group 1 — new domain content)
  digest.py                                 (group 5)
  email_sender.py                           (group 5)
  models.py                                 (group 1)
  routers.py                                (group 1)
  schemas.py                                (group 1)
  services.py                               (group 1)
  templates/daily_digest.html               (group 5)

app/scheduled/
  celery_app.py                             (groups 1, 3, 5 — side-effect imports + beat entry)
  digest_runner.py                          (group 5)
  jobs.py                                   (group 5 — daily_email_digest task)

app/leads/services.py                        (groups 1, 3 — notify + audit hooks; old_assigned_to capture)
app/enrichment/orchestrator.py               (groups 1, verif — notify hooks; lead.assigned_to recipient)
app/enrichment/services.py                   (group 3 — audit hook)
app/daily_plan/services.py                   (group 1 — daily_plan_ready notify)
app/followups/dispatcher.py                  (group 1 — followup_due notify, defensive)
app/main.py                                  (groups 1, 3 — router registrations)
app/config.py                                (group 5 — SMTP_* fields)
pyproject.toml                               (group 5 — aiosmtplib runtime dep)

tests/
  test_notifications.py                     (groups 1, verif — 10 mock-only)
  test_audit.py                              (group 3 — 7 mock-only)
  test_email_digest.py                       (group 5 — 5 mock-only)
```

### Frontend (apps/web)

```
app/(app)/audit/page.tsx                     (group 4)
app/(app)/today/page.tsx                     (group 6)
app/(app)/pipeline/page.tsx                  (group 6 — list/board swap)

components/lead-card/
  AIBriefTab.tsx                            (group 8 — ICP copy fix)
  LeadCard.tsx                              (groups 6, 7 — mobile + chips + Won/Lost banner)
  TransferModal.tsx                         (group 7 — new)

components/notifications/
  NotificationsDrawer.tsx                   (group 2)

components/pipeline/
  PipelineHeader.tsx                        (group 6 — flex-wrap)
  PipelineList.tsx                          (group 6 — new mobile list)

components/layout/AppShell.tsx               (groups 2, 4, 6 — bell + admin Журнал + hamburger)

lib/hooks/
  use-audit.ts                              (group 4)
  use-leads.ts                              (group 7 — useTransferLead)
  use-me.ts                                 (group 4)
  use-notifications.ts                      (group 2)

lib/
  i18n.ts                                   (group 7 — DEAL_TYPE / PRIORITY labels)
  relative-time.ts                          (group 2)
  types.ts                                  (groups 2, 4 — Notification + Me + Audit)
```

### Infra / Docs

```
infra/production/.env.example                (group 5 — SMTP_* example)

docs/brain/sprint_reports/SPRINT_1_5_POLISH_LAUNCH.md   (this file)
docs/brain/00_CURRENT_STATE.md                          (group 8)
docs/brain/02_ROADMAP.md                                (group 8)
docs/brain/04_NEXT_SPRINT.md                            (group 8 — Phase 2 sprint)
```

---

## Tests on the branch

```
$ pytest apps/api/tests/test_notifications.py
  10 passed in 0.07s

$ pytest apps/api/tests/test_audit.py
  7 passed in 0.21s

$ pytest apps/api/tests/test_email_digest.py
  5 passed in 0.14s

$ pytest tests/test_notifications.py tests/test_audit.py tests/test_email_digest.py
  22 passed in 0.31s

$ tsc --noEmit
  (clean)

$ next build
  ✓ 10 routes generated, no new warnings
```

---

## Next sprint

See `docs/brain/04_NEXT_SPRINT.md` — **Phase 2 Sprint 2.0 — Inbox + Quote +
Forms** (entering Phase 2 after the Sprint 1.5 merge / deploy / soft launch).
