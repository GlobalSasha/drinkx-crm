# Next Sprint: Phase 1 Sprint 1.5 — Polish + Launch

Status: **READY TO START**
Branch: `sprint/1.5-polish-launch`

## Goal

Finish what's needed to put the DrinkX team on this CRM full-time. Less new product surface, more polish. Notifications + audit + mobile + a handful of UX rough edges that piled up across Sprints 1.2–1.4. Soft launch at the end.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 1.4 left
- `docs/brain/03_DECISIONS.md` — ADR-007 (no auto-actions), ADR-018 (MiMo)
- `docs/brain/sprint_reports/SPRINT_1_4_DAILY_PLAN.md` — esp. "Known issues / risks" section
- `docs/PRD-v2.0.md` §6.10 (notifications) and §6.12 (audit)
- Production state at sprint start: 4 app containers running (api, web, worker, beat), 216 leads in pool, real Supabase auth on, MiMo+Brave+Anthropic keys live.

## Scope

### ALLOWED

#### 1. In-app notifications drawer

- New table `notifications` (alembic 0006_notifications):
  - `id` UUID PK, timestamps
  - `workspace_id`, `user_id` FK CASCADE, indexed
  - `kind` String(40) — `lead_transferred` | `enrichment_done` | `enrichment_failed` | `daily_plan_ready` | `followup_due` | `mention` | `system`
  - `title` String(200), `body` Text
  - `lead_id` UUID FK SET NULL — optional click-through target
  - `read_at` DateTime(tz) NULL
  - `created_at` DateTime(tz) server_default now()
  - Indexes `(user_id, created_at DESC)`, `(user_id, read_at)`
- Service `app/notifications/services.py` — `notify(user_id, kind, title, body, lead_id?)` writes a row + (Phase 2) optional Redis pub/sub for real-time. v1: just writes, frontend polls.
- Hooks at obvious emit points (no AI required):
  - `lead_transferred` → in `app/leads/services.transfer_lead`
  - `enrichment_done` / `enrichment_failed` → in orchestrator success/failure paths
  - `daily_plan_ready` → at the end of `generate_for_user`
  - `followup_due` → in `followup_reminder_dispatcher` per emitted reminder
- REST: `GET /api/notifications?unread=true&page=N`, `POST /api/notifications/{id}/read`, `POST /api/notifications/mark-all-read`
- Frontend: `NotificationsDrawer.tsx` opened from a bell icon in the AppShell sidebar; polls `/notifications?unread=true` every 30s; click row → mark read + navigate to lead

#### 2. Email digest (daily morning summary)

- Library: stdlib `email.message.EmailMessage` + `aiosmtplib` (it's tiny, MIT licensed; if we don't want a new dep, reuse `httpx` against a SMTP-via-API service like Postmark — defer that decision to the implementer with a recommendation toward `aiosmtplib`).
- New env vars in `infra/production/.env.example`:
  ```
  SMTP_HOST=
  SMTP_PORT=587
  SMTP_USER=
  SMTP_PASSWORD=
  SMTP_FROM=DrinkX CRM <noreply@crm.drinkx.tech>
  ```
- Stub mode: if `SMTP_HOST=""`, log the rendered email instead of sending (mirrors ADR-014 stub-mode pattern).
- New Celery task `daily_email_digest` — runs at the same hourly tick as `daily_plan_generator`, picks workspaces where local hour == 08:30 (after the plan generator finished), composes `top 5 leads to call today` + `overdue tasks` + `new enrichment Briefs` from yesterday, sends to each user.
- HTML template in `apps/api/app/notifications/templates/daily_digest.html` — minimalist taste-soft, plain inline CSS, no external assets.

#### 3. Audit log

- New table `audit_log` (alembic 0007_audit_log):
  - `id` UUID PK, timestamps
  - `workspace_id`, `user_id` (NULLABLE — system events have no user) FK
  - `action` String(60) — e.g. `lead.create`, `lead.transfer`, `lead.move_stage`, `enrichment.trigger`, `daily_plan.regenerate`
  - `entity_type` String(40), `entity_id` UUID NULL
  - `delta_json` JSON — minimal before/after fields
  - `created_at` DateTime(tz) server_default now()
  - Index `(workspace_id, created_at DESC)`, `(entity_type, entity_id)`
- Lightweight `audit.py` helper — `log(action, user_id, workspace_id, entity_type=, entity_id=, delta=)`. Called from service layer at obvious points.
- Don't audit reads (just writes). Don't audit cron's own per-tick writes (ScheduledJob already covers that).
- Admin-only REST `GET /api/audit?entity_type=&entity_id=&page=` — only `User.role == 'admin'` can hit it.
- Frontend stub admin view at `/audit` (sidebar item gated to admin role) — table of recent events with filter chips. Don't over-design — minimum viable.

#### 4. Mobile responsive pass

Three screens deserve a real mobile design pass — currently desktop-only:
- `/today` — already collapses better than the others; just verify card is readable at 375px wide
- `/leads/[id]` — biggest job; the 5 tabs + side rail collapse to single-column with a `<select>` tab switcher, rail moves under header
- `/pipeline` — Kanban is desktop-only by design (PRD §8.6); add a "Switch to list view" affordance for narrow viewports that renders leads as a flat list grouped by stage

Use Tailwind breakpoints already in `tailwind.config.ts` — `sm` (640) / `md` (768) / `lg` (1024). Touch drag-drop on `/pipeline` is OUT OF SCOPE — a list view is the mobile fallback.

#### 5. Lead Card header polish

The Lead Card top header (`apps/web/components/lead-card/LeadCard.tsx`) hasn't been polished. Currently shows company name + back link + tabs. Should also show:
- Stage chip (color from stage), priority badge (A/B/C/D), deal type pill, score (0-100) + fit_score (0-10) badge
- Right side action row: `Transfer` (opens TransferModal — wire up the existing modal scaffold), `Won`, `Lost`, `Move stage` dropdown (opens GateModal — already exists)
- "Move stage" dropdown shows 11 B2B stages + lost; selecting one with `gate_criteria_json` opens the gate modal

#### 6. AI Brief empty-state copy fix

`apps/web/components/lead-card/AIBriefTab.tsx` empty state says:
> "AI соберёт данные из Brave, HH.ru и сайта компании, оценит совпадение с **ICP** и подготовит план следующих шагов."

Replace `ICP` → `портретом идеального клиента`. The synthesis prompt already forbids LLM jargon (Sprint 1.3); UI copy missed this rev.

#### 7. Pipeline sticky header

`apps/web/components/pipeline/PipelineHeader.tsx` is currently inside the page's `flex flex-col h-screen overflow-hidden` container, so it's *technically* sticky already (above the scrollable Kanban board). The grid clamp fix (`712bd85` + `cd25a9d`) handles the case of horizontal page-scroll.

But: when the user scrolls the BOARD horizontally (within `overflow-x-auto`), the header doesn't move with the columns — we want this. Verify the header stays put across realistic 14-column horizontal scrolls. If it doesn't, add `position: sticky; top: 0; z-index: 10;` explicitly.

This is a 5-minute audit + tiny CSS tweak, not a real task.

#### 8. Soft launch checklist

Before announcing to the DrinkX team:
- [ ] Production .env complete (Sentry DSNs, all AI keys)
- [ ] First daily plan generation runs successfully on a real timezone (verify in `scheduled_jobs` table)
- [ ] One end-to-end test: sign in → enrich a lead → see the brief → drag the lead to a new stage through the gate modal → mark a follow-up complete
- [ ] Backups: `pg_dump` cron on the VPS (or Postgres-native `pg_basebackup` if we want point-in-time) — currently no backup story
- [ ] Onboarding doc for first-time users (1-pager: how to sign in, where the key buttons are, what to expect from AI)
- [ ] Review log volume (api + worker + beat) — make sure stdout isn't drowning

### FORBIDDEN (defer to Phase 2 / Sprint 1.6)

- Inbox (email IMAP/SMTP for incoming, Telegram Business webhook) — Phase 2
- Quote/КП builder — Phase 2
- Knowledge Base CRUD UI — Phase 2 (the markdown library from Sprint 1.3 stays file-based for now)
- Multi-pipeline switcher — Phase 2
- Mobile push notifications — Phase 3
- Vector DB / pgvector — Phase 3
- Anything that needs new external accounts (Postmark / Twilio / Resend) — discuss before adding a vendor

## Tests required

- pytest: `notifications.services.notify` writes the right row shape; admin-only audit endpoint denies non-admins; daily digest renders without sending in stub mode
- pytest: cross-user mutation guard on `/notifications/{id}/read`
- pytest: audit row written on `lead.transfer_lead` and `enrichment.trigger`
- web: Playwright (or skipped if env unavailable): bell icon → drawer renders → mark all read flow
- Manual: 375px viewport screenshot of /leads/[id] showing the responsive layout

## Deliverables

- Migrations 0006 + 0007 applied on production
- Notifications drawer in production AppShell
- Email digest cron firing (verify a stub log entry on next 08:30 local tick)
- Audit log table populating
- Mobile-readable Lead Card + /today + /pipeline list-fallback
- `docs/brain/sprint_reports/SPRINT_1_5_POLISH_LAUNCH.md` written
- Update `docs/brain/00_CURRENT_STATE.md`
- Update `docs/brain/02_ROADMAP.md` — Sprint 1.5 → DONE, Phase 2 → NEXT
- Update `docs/brain/04_NEXT_SPRINT.md` → Phase 2 first sprint scope

## Stop conditions

- All tests pass → report written → committed → push only with explicit product-owner approval
- No scope creep into Phase 2 items
- No vendor lock-in without discussion (especially email provider)

---

## Recommended task breakdown (one PR per group, ~1 subagent each)

1. **Notifications backend** — table, service, hooks, REST
2. **Notifications frontend** — bell icon + drawer + 30s polling + mark-read
3. **Audit backend** — table, helper, hooks, admin-only REST endpoint
4. **Audit frontend** — minimal `/audit` admin view
5. **Email digest** — Celery task + HTML template + stub-mode-aware sender
6. **Mobile responsive** — Lead Card + /pipeline list fallback + /today verification
7. **Lead Card header polish** — stage/priority/deal_type/score chips + Transfer/Won/Lost/Move-stage actions
8. **Small fixes** — AI Brief copy + Pipeline sticky header verification

After all merged: walk the soft-launch checklist with the DrinkX team.

---

## Followups parked from earlier sprints

These can opportunistically bundle into Sprint 1.5 if anyone runs short on work:

- **Phase G (Sprint 1.3 follow-on)** — move enrichment orchestrator off FastAPI BackgroundTasks onto Celery (now that Celery exists). Add WebSocket `/ws/{user_id}` for real-time enrichment progress; replace the 2s polling.
- **DST-aware daily plan cron** — handle hour-skip and hour-duplicate edge cases for `daily_plan_generator`.
- **Stuck `DailyPlan` row from Sprint 1.4 loop bug** — write a one-shot SQL to flip any lingering `status='generating'` rows to `failed` so users aren't seeing the spinner forever (UI handles `failed` correctly; users can re-trigger).

Both are nice-to-haves — skip if Sprint 1.5 runs long.
