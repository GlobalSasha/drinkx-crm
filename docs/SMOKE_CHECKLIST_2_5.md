# Sprint 2.5 — Post-deploy smoke checklist

Supplement to `SMOKE_CHECKLIST_2_4.md`, NOT a replacement. Run the
9 checks from 2.4 first; then the 7 new 2.5 checks below. Both lists
should run on staging immediately after the sprint branch lands, and
again on prod after merge to main.

The same rule applies: every row needs an actual visit in a logged-in
browser tab — DevTools Network tab open, "Preserve log" enabled, zero
non-2xx tolerated.

## Setup

- Workspace seeded with at least 1 user, 1 pipeline, 1 lead, 1
  message template (Sprint 2.4 G4 module).
- Two browser sessions handy: one as the inviter (admin/head), one to
  accept a magic-link invite as a fresh user (test #5).

## New 2.5 checks

| # | Page / Flow | Verify |
|---|---|---|
| 1 | `/automations` (admin/head) | Page loads. `/api/automations` 200. Existing automations render in the table; trigger / action labels in Russian; status chip («Активна» / «Выключена»). Manager-role users get redirected or see read-only (action buttons hidden). |
| 2 | `/automations` → «Новая автоматизация» | Builder modal opens. Trigger dropdown lists 3 options. Condition row exposes 8 ops («=», «≠», «≥», «≤», «>», «<», «пусто», «не пусто»). Action picker switches the per-action config block (template dropdown / title+due_in_hours / target_stage_id). is_active checkbox defaults to checked. |
| 3 | Create automation end-to-end | Trigger=`stage_change`, condition empty, action=`create_task` with title «Связаться с ЛПР» — Save → 201 → row appears in table. Click the name in the table → RunsDrawer opens with empty list («Запусков пока не было»). |
| 4 | Trigger fires + run history | Move a lead to a stage that should match the rule (or just any stage if the rule has no `to_stage_id` filter). Reload `/automations` → click into the rule's runs drawer. New row appears with status «Успешно» + executed_at. The lead's Activity Feed shows the new task-type Activity. (If the action is `send_template` instead, the Activity row carries `outbound_pending=true` in the payload — no real send in v1.) |
| 5 | Invite accept-flow + inviter ping | Inviter session: `/settings → Команда → Пригласить` with a fresh email (use a personal mailbox you can read). Magic-link arrives via Supabase (or worker log line in stub mode). Open the link in a fresh browser → sign in. Switch back to the inviter session → bell shows badge increment. Open drawer → top item is «X принял приглашение в workspace» with kind chip «Система» (or `invite_accepted` if the frontend label hasn't been polished yet — non-blocking). Reload `/settings → Команда → Приглашения` → row's `accepted_at` filled in. |
| 6 | Notification dedupe | Trigger the SAME kind of notification twice within 1 minute (e.g. transfer two leads to the same user back-to-back). Inviter / target manager sees ONE bell badge increment, not two. Worker log shows `notifications.skip_dedup_window` for the second emit. (If the second one DID create a row, dedup is broken.) |
| 7 | Drawer day grouping | After a few days of activity, open the bell drawer. Sticky day headers «Сегодня» / «Вчера» / «D MMM» (e.g. «5 мая») visible above the corresponding item groups. Newest-first ordering preserved within each group. |

## If anything fails

- **Don't merge** (or roll back the merge if already on prod).
- Capture failing request payload + response in the sprint report's «Production-readiness» section before opening a hotfix branch.
- Standard hotfix pattern: `hotfix/{slug}` branch off main, fix +
  test, merge back via PR. Same shape as `hotfix/single-workspace`,
  `hotfix/celery-mapper-registry` etc.

## Operator notes

- `send_template` stub. Until Sprint 2.6 G1 wires real dispatch, any
  automation with `action_type=send_template` only stages an Activity
  row with `outbound_pending=true`. This is by design; ops will see
  the row in the lead's Activity Feed but the customer will NOT
  receive the email/tg/sms. Surface this proactively to admins
  during the post-merge announcement.
- Migration 0020 is additive. Down-migration drops `automation_runs`
  + `automations` cleanly; no data on those tables in production yet
  at smoke time, so rollback risk is low.
- The fan-out hooks live INSIDE the parent transactions
  (`stage_change` post-action, `forms.lead_factory` after-create-lead,
  `inbox.processor` before-commit). Wrapped in `safe_evaluate_trigger`
  so a bad automation cannot roll back lead moves / form submissions
  / email attachments. Worker logs surface the failure as
  `automation.evaluate_trigger.swallowed`.
- G2 dedupe applies workspace-wide. If an admin invites 5 teammates
  in the same hour and all accept within that window, the inviter
  gets ONE bell ping for the first; the rest land in the audit log.
  This is the Sprint 2.5 cadence; documented in `04_NEXT_SPRINT.md`
  G2 spec.
