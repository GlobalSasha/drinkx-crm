# DrinkX CRM — Roadmap

## ✅ DONE

### Phase 0 — UX/UI Design & Prototyping (in `crm-prototype` repo)
- HTML prototypes: index.html, index-soft-full.html, index-soft.html
- B2B reference: index-b2b.html (11-stage pipeline, gates, scoring 0-100, multi-stakeholder, deal type, A/B/C/D, dual-rotting, pilot contract)
- data.js: 131 real DrinkX clients
- v0.6 foodmarkets-audit: +85 candidates
- PRD v2.0 + addition v2.1 (Lead Pool & Sprint System)
- Design system: taste-soft (Plus Jakarta Sans + double-bezel + squircle)

### Phase 1 — Foundation + Auth + AI (in `drinkx-crm` repo)

**Sprint 1.0 — DONE** · `SPRINT_1_0_FOUNDATION.md`
- Monorepo, bare-metal Docker stack on crm.drinkx.tech, GitHub Actions auto-deploy

**Sprint 1.1 — DONE** · `SPRINT_1_1_AUTH.md` + Sprint 1.1.3 follow-on
- Workspace/User/Pipeline/Stage models; alembic 0001
- JWT verifier supports HS256 + ES256/RS256 via JWKS
- Real Supabase + Google OAuth + magic link via `@supabase/ssr`

**Sprint 1.2 — DONE** · `SPRINT_1_2_BACKEND_MERGE.md` + frontend follow-on
- Migration 0002: 5 new tables (leads, contacts, activities, followups, scoring_criteria), 11 B2B stages
- Lead REST + Pool + Sprint claim + transfer; stage transitions with gate engine
- AppShell + /today + /pipeline (drag-drop) + /leads-pool + /leads/[id] (5 tabs)
- 216 leads imported from prototype data

**Sprint 1.3 — DONE** · `SPRINT_1_3_AI_ENRICHMENT.md`
- LLM Provider abstraction: MiMo (primary) + Anthropic + Gemini + DeepSeek with fallback chain
- Sources: Brave + HH.ru + web_fetch with 24h Redis cache
- Migration 0003: `enrichment_runs`; Research Agent orchestrator
- AI Brief tab with hero band, fit_score, score_rationale, signals, decision-makers, next-steps
- DrinkX `profile.yaml` + KB markdown library (segment-tagged playbooks + always-on objections / competitors / icp_definition)
- Cost guards: per-lead rate limit, workspace concurrency cap, daily budget cap

**Sprint 1.4 — DONE** · `SPRINT_1_4_DAILY_PLAN.md`
- **First Celery service in the system** — worker + beat live in production
- Migration 0004: daily_plans, daily_plan_items, scheduled_jobs (UNIQUE on (user_id, plan_date) for upsert)
- Migration 0005: followups.dispatched_at for idempotency
- `priority_scorer.score_lead()` pure function with tunable weights
- `DailyPlanService.generate_for_user()` — score → pack into work_hours → MiMo Flash hints → time-block spread
- Cron beat: `daily_plan_generator` hourly with timezone-local 08:00 filter; `followup_reminder_dispatcher` every 15 min, idempotent
- REST: `/me/today`, regenerate, complete-item; manual UI trigger via Celery `regenerate_for_user`
- Frontend `/today` rewritten with real plan rendering — compact cards (~72px), URL-driven pagination 10/page, time-block sections, hot-lead left rail
- Infra hotfixes (4): Node 22 bump, pnpm pin, Celery mapper-registry, per-task NullPool engine

**Sprint 1.5 — DONE** · `SPRINT_1_5_POLISH_LAUNCH.md` · branch `sprint/1.5-polish-launch` (range `f3e0509..HEAD`, 8 groups)
- Migration 0006: `notifications` (workspace/user FK, kind/title/body, optional lead_id, read_at)
- Migration 0007: `audit_log` (workspace/user FK, action/entity_type/entity_id/delta_json) + admin-only `GET /audit`
- `app/notifications` domain — `notify` / `safe_notify` / mark-read / mark-all-read; bell badge + drawer with 30s polling
- `app/audit` domain — `audit.log()` defensive helper + 4 emit hooks (lead.create, lead.transfer, lead.move_stage, enrichment.trigger); admin-only `/audit` page
- `app/notifications/email_sender.py` + `digest.py` + `templates/daily_digest.html` — daily morning email digest (top-5 plan items / top-5 overdue / top-5 yesterday's briefs); SMTP via aiosmtplib with stub mode while SMTP_HOST=""
- Beat: new entry `daily-email-digest` `crontab(minute=30)` (combined with local-hour=8 filter → fires at 08:30 local time)
- Frontend mobile pass — AppShell hamburger overlay, /today flex-wrap + 44px tap-targets, /leads/[id] stacked rail + select tab switcher, /pipeline list-view fallback below md
- LeadCard header polish — Stage / Priority / Deal type / Score "X/100" / "AI X/10" chips with band colors; Won/Lost banner; functional TransferModal (UUID input)
- AIBriefTab empty-state: "ICP" → "портретом идеального клиента"
- 22 mock-only backend tests, 0 DB / 0 SMTP / 0 network; tsc + next build clean throughout
- 0 new npm dependencies; 1 new Python dep (aiosmtplib)

**Sprint 2.0 — DONE + DEPLOYED** · `SPRINT_2_0_GMAIL_INBOX.md` · merged `2938810` (range `8745394..2938810`, 7 groups)
- **Gmail Inbox sync — read-only Phase 2 first slice**
- Migrations 0008 (`channel_connections`) + 0009 (`inbox_items` + activities email columns + subject 300→500)
- New `app/inbox/` package: gmail_client, oauth, email_parser, matcher, processor, sync, services, routers, schemas, models
- Beat: 4th cron `gmail-incremental-sync */5`
- New Celery tasks: `gmail_history_sync(user_id)` (6mo backfill, 2000-msg cap), `gmail_incremental_sync` (every-5-min via History API), `generate_inbox_suggestion(item_id)` (MiMo Flash, fail-soft)
- AI Brief synthesis injects last 10 emails as `### Переписка с клиентом` (cap 2000 chars)
- New `/inbox` page (empty-state OAuth CTA, AI-suggestion chips, confirm/dismiss flows), `Входящие` sidebar with red-dot badge
- Lead Card Activity Feed renders email rows with direction icon + bold subject + 200-char preview + Показать полностью toggle
- 18 mock-only tests (matcher 9, email-context 3, services 6); pnpm typecheck + build clean
- ADR-019: emails are lead-scoped, `Activity.user_id` is audit trail not visibility filter
- 0 new npm deps; 3 new Python deps (`google-auth`, `google-auth-oauthlib`, `google-api-python-client`)

**Sprint 2.1 — DONE (pending merge)** · `SPRINT_2_1_BULK_IMPORT_EXPORT.md` · branch `sprint/2.1-bulk-import-export` (range `46cc6a2..HEAD`, 9 groups + G10 close, G5 AmoCRM deferred)
- **Bulk Import / Export + AI Bulk-Update — Phase 2 second slice**
- Migrations 0010 (`import_jobs` + `import_errors`) + 0011 (`export_jobs`)
- New `app/import_export/` package: parsers (XLSX/CSV/JSON/YAML), mapper (fuzzy column match + conflict resolution), validators, exporters (5 formats), snapshot, diff_engine (3-batch resolve + apply), services, routers, adapters/{bitrix24, bulk_update}
- New Celery tasks: `bulk_import_run`, `run_export`, `run_bulk_update` (per-row commit, real-time UI poll)
- Redis blob storage for export results (TTL 1h, separate `decode_responses=False` client)
- `/import` 4-step wizard on `/pipeline`, «Экспорт» popover on `/pipeline` + `/leads-pool`, «AI Обновление» modal on `/leads-pool`, BulkUpdatePreview component for diff step
- Auth-aware download via `lib/download.ts` (works on prod cross-origin, retro-fixes G7 latent bug)
- Credentials at rest: Fernet encryption with `fernet:` prefix (Sprint 2.0 carryover closed in 2.1 G1)
- Browser Sentry init guard (G10) — DSN check + lazy require, ready for `pnpm add @sentry/nextjs`
- 64 mock-only tests (12 G1 + 16 G2 + 9 G4 + 10 G6 + 6 G8 + 11 G9 + 0 frontend)
- 0 new npm deps; 2 new Python deps (`cryptography>=43.0.3`, `openpyxl>=3.1.5`)
- ADR-007 satisfied at the diff-preview level for stage moves (documented in `diff_engine.apply_diff_item`)

**Sprint 2.2 — DONE (pending merge)** · `SPRINT_2_2_WEBFORMS.md` · branch `sprint/2.2-webforms` (range `32b5d79..HEAD`, 4 groups)
- **WebForms — Phase 2 third slice (public lead-capture)**
- Migration 0012 (`web_forms` + `form_submissions` + indexes)
- New `app/forms/` package: models, schemas, repositories, services (auto-slug + IntegrityError retry × 3, soft_delete returns 410), slug.py (stdlib-only RU translit + 6-char base36 suffix), routers (admin REST), public_routers (`/api/public/forms/{slug}/{submit,embed.js}`), rate_limit (Redis INCR + conditional EXPIRE, fail-open), embed.py (self-contained ~90-line JS, once-loaded guard), lead_factory (RU+EN field dict, ADR-007 — never assigns / never advances)
- Scoped `PublicFormsCORSMiddleware` for `/api/public/*` only; global CORS stays restrictive
- `form_submission` joins the `ActivityType` enum; carries `{form_name, form_slug, source_domain, utm}`
- New `/forms` admin page (admin/head gated) + `FormEditor` modal with «Настройки» + «Встроить» tabs; AppShell «Формы» nav item; Activity Feed `form_submission` render with ClipboardList icon + «Заявки» filter chip; Lead Card header `source` chip
- 18 mock-only tests (test_webforms.py 9 + test_public_submit.py 9). Combined baseline: **117 mock tests passing**
- 0 new npm deps; 0 new Python deps; `pnpm build` 12 routes (was 11)
- ADR-007 satisfied: forms capture leads, never auto-assign / never advance stage / never trigger AI

**Sprint 2.5 — DONE (pending merge)** · `docs/SPRINT_2_5_AUTOMATION_BUILDER.md` · branch `sprint/2.5-automation-builder` (range `363b371..HEAD`, 4 of 5 gates shipped — G3 AmoCRM skipped by product decision)
- **Automation Builder + notification dedup + invite accept-flow — Phase 2 sixth slice**
- Migration 0020 (`automations` + `automation_runs`)
- New `app/automation_builder/` package — workspace-scoped «when X happens, run Y» rules with 3 trigger sources (stage_change / form_submission / inbox_match), condition tree evaluator (allowlisted Lead fields), `{{lead.field}}` render substitution (allowlisted RENDER_FIELDS, `[unknown:foo]` marker for non-allowlisted), 3 action handlers (send_template / create_task / move_stage)
- Trigger fan-out wired into existing hot paths: `app/automation/stage_change.py` POST_ACTIONS, `app/forms/lead_factory.py` after-create-lead, `app/inbox/processor.py` before-commit (atomic with email Activity). All wrapped in `safe_evaluate_trigger` so a misconfigured rule cannot roll back the parent transaction
- 5 endpoints under `/api/automations` (admin/head writes; any-role reads); audit emits on `automation.{create,update,delete}`
- Notification dedupe: 1h window in `notify()` + empty `daily_plan_ready` body suppression (regex on `^0\s+карточек`); `DEDUP_EXEMPT_KINDS = {"lead.urgent_signal"}`
- NotificationsDrawer day grouping (`Сегодня` / `Вчера` / `D MMM`) via Intl.DateTimeFormat ru-RU
- Invite accept-flow: `_apply_pending_invite` in `app/auth/services.py` flips `accepted_at` (column existed since 0016 but never written) + `safe_notify(invite_accepted)` to inviter inside the same transaction
- Frontend: new `/automations` page with builder modal + RunsDrawer; AppShell sidebar entry «Автоматизации» (admin/head)
- 20 new mock tests (12 G1 + 5 G2 + 3 G4); baseline 281 → 301
- 0 new npm deps; 0 new Python deps; `send_template` dispatch is a stub (Activity row with `outbound_pending=true`) — real outbound wiring is Sprint 2.6 G1

**Sprint 2.4 — DONE** · `docs/SPRINT_2_4_SETTINGS_TEMPLATES.md` · branch `sprint/2.4-settings-templates` (range `01e104a..HEAD`, 5 gates + G4.5 quick wins) · merged to main `9587d47`
- **Full Settings panel + Templates module — Phase 2 fifth slice**
- Migrations 0016 (`user_invites`) + 0017 (drop `pipelines.is_default`) + 0018 (`custom_attribute_definitions` + `lead_custom_values` EAV) + 0019 (`message_templates`)
- New `app/users/` package (invite via Supabase admin REST, role-change with last-admin guard, idempotent re-invite)
- New `app/settings/` package — channels read-view (Gmail per-user OAuth state + SMTP env config) + AI section (workspace.settings_json overrides for daily budget cap + primary model)
- New `app/custom_attributes/` package — EAV definitions + per-lead values, kind-aware upsert dispatch (text/number/date/select), select kind validates against options_json
- New `app/template/` package (singular per CLAUDE.md domain registry; route prefix `/api/templates`) — UUID PK, channel as String(20) + VALID_CHANNELS guard, rename-aware duplicate check, audit on create/update/delete
- Frontend: 5 new sections under `/settings` — TeamSection / ChannelsSection / AISection / CustomFieldsSection / TemplatesSection
- G5 polish: audit page server-joins users for «Имя · email» rendering with shortId fallback; formatDelta switches per action (`lead.move_stage` → from→to, `template.create` → name, etc.); NotificationsDrawer click split (system/daily_plan rows non-navigable, persistent Check + hover X with backend DELETE endpoint); priority colour palette centralized in `lib/ui/priority.ts`; `scripts/pg_dump_backup.sh` + `docs/crontab.example` close the Sprint 1.5 backup carryover
- 281 mock tests passing / 14 pre-existing failed (fastapi env) / 58 skipped — was 132 at sprint start
- 0 new npm deps; 0 new Python deps
- ADRs reaffirmed: ADR-018, ADR-019, ADR-020, ADR-021

**Sprint 2.3 — DONE (pending merge)** · `SPRINT_2_3_MULTI_PIPELINE.md` · branch `sprint/2.3-multi-pipeline` (range `4294988..HEAD`, 4 groups)
- **Multi-pipeline switcher — Phase 2 fourth slice**
- Migration 0013 (`workspaces.default_pipeline_id` UUID NULL FK SET NULL + two-pass backfill)
- New `app/pipelines/services.py` + `app/pipelines/repositories.py` extended with workspace-scoped CRUD + 409 guards (`PipelineHasLeads` carries lead_count, `PipelineIsDefault` blocks deletion of the active default)
- 5 new endpoints under `/api/pipelines` (admin/head gated for writes); `pipeline_id` filter added to `GET /leads`
- `WorkspaceOut.default_pipeline_id` exposed so the frontend hydrates cold-load without an extra round-trip
- `app/forms/services.py` — Sprint 2.2 G4 carryover closed: `_validate_target` rejects cross-workspace `target_pipeline_id` / `target_stage_id` references at create + update time (HTTP 400)
- New `/settings` page with «Воронки» live and 5 «Скоро» stubs; `PipelinesSection` + `PipelineEditor` (`@dnd-kit` sortable stages, color picker, rot_days); 3-branch friendly delete modal consuming the structured 409 detail
- `PipelineSwitcher` in `/pipeline` header — workspace-namespaced localStorage selection (`drinkx:pipeline:{workspaceId}`); single-pipeline workspaces see a non-interactive chip
- Audit log emits on `pipeline.create / pipeline.delete / pipeline.set_default` with informative deltas (`{name, stage_count}` / `{name}` / `{name, from_id, to_id}`)
- `set_default` fans out a system-kind notification to every admin/head in the workspace («Основная воронка изменена») — wrapped in try/except, never blocks the flip
- 12 mock-only tests in `test_pipelines_service.py` (10 G1 + 2 G4 fan-out). Combined baseline: **129 mock tests passing**
- 0 new npm deps; 0 new Python deps; `pnpm build` 13 routes (was 12; `/settings` at 7.61 kB)
- `pipelines.is_default` boolean kept as redundant signal for diff_engine + back-compat — drop is a 2.4+ housekeeping pass

## 🔜 NEXT

### Phase 2 — Sprint 2.6 — Real outbound dispatch + UX polish (~5 gates)
See `docs/brain/04_NEXT_SPRINT.md` for full scope.

**Main driver:** flip Sprint 2.5's `send_template` from a stubbed
Activity row (`outbound_pending=true`) to actual dispatch via the
existing email_sender (Sprint 1.5) and stub channels for tg + sms
until proper providers land in 2.7+.

Tentative gate breakdown:
- **G1 — Real outbound dispatch** for `send_template`: render template body, route by `template.channel` (email via `email_sender.py`; tg + sms remain stub-mode with structured worker log), flip `outbound_pending` flag, surface delivery status in the Activity Feed.
- **G2 — Multi-step automation chains** («send email → wait 3 days → create task»). Likely needs migration `0021_automation_steps` + a Celery beat scheduler watching `wait_until` timestamps.
- **G3 — Pipeline + LeadCard polish bundle** (carryovers): pipeline header tweak (accent → +Лид; Sprint → outline), LeadCard `window.confirm` → modal on Lost, mobile Pipeline fallback (<md) vertical card layout.
- **G4 — Custom-field render on LeadCard + dnd-kit reorder** (Sprint 2.4 G3 carryovers). Values exist in `lead_custom_values` since 0018; G4 finally exposes them in the LeadCard right-rail.
- **G5 — Sprint close** — sprint report, brain rotation, smoke checklist.

Carryovers from 2.5 to fold into 2.6 (full list also in
`SPRINT_2_5_AUTOMATION_BUILDER.md`):
- Real `send_template` dispatch (G1 driver)
- Multi-step automation chains (G2 driver)
- Pipeline header tweak (accent → +Лид; Sprint → outline)
- Default pipeline 6–7 stages confirm + ICP fields
- Settings sidebar «Скоро» collapse into disclosure
- LeadCard `window.confirm` → modal on Lost
- Mobile Pipeline fallback (<md)
- Custom-field render on LeadCard
- Stage-replacement preview in PipelineEditor
- Multi-clause condition UI in Automation Builder modal
- dnd-kit reorder for Custom Fields position
- AmoCRM adapter (skipped in 2.5 G3, back in long-tail)

Other outstanding deferred work for 2.6+:
- **Telegram Business inbox** + **email send (gmail.send scope)** — deferred since Sprint 2.0
- **Quote / КП builder**, **Knowledge Base CRUD UI** — deferred from 2.0 envelope
- **`_GENERIC_DOMAINS` per-workspace setting** (Sprint 2.0 carryover)
- **Gmail history-sync resumable / paginated job** (Sprint 2.0 2000-msg cap)
- **Notification debounce** on form-submission fan-out (Sprint 2.2 carryover)
- **Honeypot / timing trap on `embed.js`** (Sprint 2.2 carryover)
- **Pipeline cloning / templates** (Sprint 2.3 deferred; «start from template» CTA in PipelineEditor)
- **Workspace AI override → fallback chain wiring** (Sprint 2.4 G3 carryover; UI persists, env still wins)
- **`pnpm add @sentry/nextjs`** + DSN env vars (Sprint 2.1 G10 carryover)
- **Phase G (Sprint 1.3 follow-on)** — move enrichment off FastAPI BackgroundTasks onto Celery; WebSocket `/ws/{user_id}` for real-time progress
- DST-aware cron edge handling
- Sentry DSNs activation (Sprint 1.5 soft-launch carryover; pg_dump cron closed by Sprint 2.4 G5)

## 📅 LATER

### Phase 2 — Sprint 2.5+ (~4 weeks)
Automation Builder (consumes Templates from 2.4), Apify integration
(foodmarkets / horeca scrapers), push notifications + Telegram bot for
managers, AmoCRM adapter, Quote / КП builder, Knowledge Base CRUD UI.

### Phase 3 (~4 weeks)
- **Multi-tenancy** — invite-flow + per-tenant routing (or per-
  tenant DB) for selling the codebase to a second client. ADR-021
  baked the «one canonical workspace per deployment» assumption
  into `bootstrap_workspace`; the second client would today land
  in workspace #1 silently. Surface area: explicit invite table,
  domain allow-list / signup gating, optional tenant-scoped subdomains
  (e.g. `crm.acme.com` vs `crm.drinkx.tech`). Carries over the
  `WORKSPACE_NAME` env-var pattern but adds a tenant resolver in
  the auth dependency chain.
- MCP server, AI Sales Coach full chat, Visit-card OCR parser,
- Vector DB (pgvector) for similar-deals retrieval, Stalled-deal detector,
- Pipeline column virtualization (>1000 cards), Apify lead-gen wizard.
