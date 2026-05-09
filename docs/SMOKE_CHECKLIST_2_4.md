# Sprint 2.4 — Post-deploy smoke checklist

Run this ritual on staging immediately after `sprint/2.4-settings-templates`
lands, and again on prod after the merge to `main`. Every row needs an
actual visit in a logged-in browser tab — Network → Fetch/XHR open,
zero non-2xx responses tolerated.

The checklist exists because of the 2026-05-08 incident where
`/leads-pool` was silently broken for >24h after a frontend page-size
bump (frontend `480d0a9` → backend hotfix `8349516`). The lesson:
typecheck and unit tests don't catch contract drift between deployed
frontend and deployed backend; manual visit does.

## Setup

- Workspace seeded with at least 1 user, 1 pipeline, 1 lead.
- Network DevTools tab open, "Preserve log" enabled.
- Reset filter every check — don't reuse a stale filter from the previous step.

## Checks

| # | Page | Verify |
|---|---|---|
| 1 | `/login` | Auth flow works. Magic link OR Google OAuth completes. After sign-in, redirect lands on `/pipeline`. No 4xx in network. |
| 2 | `/pipeline` | Kanban board loads. `/api/pipelines` 200. `/api/leads?pipeline_id=...` 200. Drag-and-drop a card to a different stage; reload — the move persisted. PipelineSwitcher dropdown opens (multi-pipeline workspaces) or shows the chip (single-pipeline). |
| 3 | `/leads/{id}` | LeadCard opens. Trigger «Запросить AI Brief» — `enrichment_run_id` returned, AI Brief tab eventually renders synthesis. Activity Feed shows email rows if Gmail is connected. Priority chip uses the centralized colour palette (A=accent, B=success, C=warning, D=muted). |
| 4 | `/settings` → **Команда** | Team table loads. Admin sees «Пригласить» button. Clicking it sends a magic-link via Supabase admin API (worker logs show `users.invite_supabase_returned`). New invite row appears in the «Приглашения» list. Demoting the last admin returns a structured 409 modal («Это последний администратор…»). |
| 5 | `/settings` → **AI** | Admin-only. Budget gauge renders with current spend / cap. Model selector lists deepseek / anthropic / gemini / mimo. Editing the budget cap + model + Save → `PATCH /api/settings/ai` 200. Reload — values persist via `workspace.settings_json["ai"]`. |
| 6 | `/settings` → **Кастомные поля** | List loads. «Новое поле» modal opens. Create one of each kind (text, number, date, select). Select kind requires options. Duplicate key → structured 409. Delete with values defined → CASCADE removes them too (verify on a lead detail page). |
| 7 | `/settings` → **Шаблоны** | Table loads. «Новый шаблон» opens modal. Channel dropdown shows email / Telegram / SMS. Creating a template with a duplicate (name, channel) → structured 409 inline error. Edit + Delete work; deleting requires confirm. Manager role hides action buttons. |
| 8 | Notifications bell | Badge shows the unread count. Drawer opens on click. **G5 click split:** rows with `lead_id` (e.g. `lead_transferred`) navigate to the lead on click. Rows without `lead_id` (`system`, `daily_plan_ready`) do NOT navigate; instead a Check button marks-read and an X (visible on hover) dismisses permanently. Both update the bell badge correctly. |
| 9 | `/audit` (admin only) | Table loads. **G5 user column:** rows with a known user show «Имя · email@domain» (full_name and email server-joined from users table). Rows where the user was deleted or `user_id` is NULL show the first 8 chars of the UUID with «system» in the title tooltip. **G5 formatDelta:** `lead.move_stage` rows render «from → to», `lead.transfer` rows render «from_user → to_user», `template.create / template.update` rows render the template name. Other actions fall back to truncated JSON. |

## If anything fails

- **Don't merge.** Fix on the sprint branch, re-deploy staging, re-run the checklist.
- Capture the failing request payload + response in the sprint report's «Production-readiness» section before opening a hotfix branch.
- Hotfixes between sprints get a top-level `hotfix/{slug}` branch (see `hotfix/single-workspace`, `hotfix/celery-mapper-registry` etc. for the pattern).

## Operator notes

- **pg_dump cron** — `scripts/pg_dump_backup.sh` is shipped but NOT
  installed on the host crontab. Operator copies the relevant line
  from `docs/crontab.example` into `crontab -e` after verifying paths
  and the deploy-user permissions on `/var/backups/drinkx`.
- **SMTP stub** — invite magic-links go via Supabase, not SMTP, so
  the team-invite flow works even with `SMTP_HOST=""`. The daily
  digest does not.
- **Sentry** — still empty DSN; activation is a Sprint 2.1 carryover
  parked in 2.5+ (requires `pnpm add @sentry/nextjs`, deferred for
  the «0 new deps» constraint of Sprint 2.4).
