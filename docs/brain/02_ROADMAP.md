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

**Sprint 2.6 — DONE (pending merge)** · `docs/SPRINT_2_6_OUTBOUND_EMAIL.md` · branch `sprint/2.6-outbound-email` (range `b740a76..HEAD`, 4 planned gates shipped + 2 mid-sprint stability commits — G2 multi-step chains skipped by product decision)
- **Real outbound email + UX polish — Phase 2 seventh slice**
- 0 new migrations — pure code on the existing schema
- New `app/email/sender.py` — tri-state SMTP wrapper (True / False / EmailSendError) for the Automation Builder
- New `app/automation_builder/dispatch.py` — post-commit email dispatch queue (contextvar-scoped); SMTP runs in a fresh session AFTER the parent transaction commits, so a slow / failing relay can't hold the lead-attach / form-submission / move-stage transaction
- `_send_template_action` for `email` channel: stages Activity with `delivery_status='pending'`, queues a `PendingDispatch`, returns. `tg` / `sms` keep `delivery_status='pending'` until 2.7+ providers
- Per-automation `db.begin_nested()` SAVEPOINT in `evaluate_trigger` — exception in one action no longer poisons the parent session
- Whitespace-strip on `lead.email` before SMTP — Sprint 2.6 G1 stability fix #3
- `TemplateInUse` 409 guard on `delete_template` — refuses delete when an active automation references the template via `action_config_json["template_id"]` JSON-key (not a real FK)
- N+1 → bulk-fetch in `followups/dispatcher.py` — single `WHERE id IN (...)` SELECT before the loop replaces per-followup lead lookup
- Pipeline header polish: +Лид → accent fill, Sprint button → outline
- Settings sidebar «Скоро» disclosure — 3 stub sections fold under `<details>`
- `LostModal.tsx` replaces `window.confirm` + `window.prompt` on the «Перевести в Проигран» action
- Mobile Pipeline polish — centralized priority chip + stage badge per card
- `CustomFieldsPanel.tsx` on LeadCard — inline editing per kind (text / number / date / select); empty values render «не заполнено»; backend echoes the updated row so cache splices without GET
- dnd-kit reorder in Settings → Кастомные поля; `PATCH /api/custom-attributes/reorder` writes `position = index` atomically
- New endpoints: `GET / PATCH /api/leads/{id}/attributes`, `PATCH /api/custom-attributes/reorder`
- Cross-workspace defence on attribute upsert — `DefinitionNotFound` → 403 (workspace = security boundary)
- 17 new mock tests across the sprint (95 → 112 baseline). 0 CRITICAL remain after stability audit; 2 of 4 HIGH fixed (the rest depend on Sentry activation, Sprint 2.7 G1)
- 0 new npm deps; 0 new Python deps
- ADRs: none new — Sprint 2.6 was implementation-shaped, not architecture-shaped

**Sprint 2.5 — DONE** · `docs/SPRINT_2_5_AUTOMATION_BUILDER.md` · branch `sprint/2.5-automation-builder` (range `363b371..HEAD`, 4 of 5 gates shipped — G3 AmoCRM skipped by product decision) · merged to main `3aa78f3`
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

**Sprint 2.7 — DONE (pending merge → main)** · `docs/SPRINT_2_7_SENTRY_MULTISTEP.md` · branch `sprint/2.7-sentry-multistep` · PR [drinkx-crm#12](https://github.com/GlobalSasha/crm/pull/12) · 3 commits (`65c5bef..03bf762`)
- **Sentry activation + multi-step automation chains — Phase 2 final slice**
- 3 of 5 planned gates shipped; G3 + G4 deferred to long-tail by product decision (see DEFERRED section below)
- **G1 — Sentry activation** (`1c4283d`): new `app/common/sentry_capture.py` (single chokepoint, lazy import, soft no-op when SDK missing) + new `app/observability.py` (init_sentry_if_dsn extracted from main.py:lifespan for testability); 4 cron-class swallow sites wrap `capture()` alongside structlog (audit.log, automation_builder.safe_evaluate_trigger, daily_plan_runner, digest_runner); enrichment `_bg_run` failure path catches + flips `EnrichmentRun.status='failed'` via new `_mark_run_failed` + reports — closes the Sprint 2.6 audit finding «BackgroundTasks strands rows in 'running' on failure». Frontend: new `lib/sentry-capture.ts` runtime helper; `app/global-error.tsx` + `app/(app)/error.tsx` boundaries; `window.onerror` + `unhandledrejection` listeners in providers.tsx. 8 mock tests.
- **G2 — Multi-step automation chains** (`03bf762`): Migration 0021 — `automations.steps_json JSONB NULL` (additive — null = legacy single-action) + new `automation_step_runs` table with partial index `(scheduled_at) WHERE executed_at IS NULL`; `_dispatch_action` collapsed into `_dispatch_step(step)`; handlers refactored to `(lead, config, automation_id_str)` so the same code path serves synchronous step 0 and async step N. New `execute_due_step_runs` driven by `automation_step_scheduler` Celery beat task every 5 min. New `GET /api/automations/runs/{run_id}/steps` for the RunsDrawer per-step grid. Frontend: «Цепочка после первого шага» fieldset in the editor with +Пауза/+Шаблон/+Задача/+Стадия + ↑/↓/✕ controls; expandable per-step grid in RunsDrawer. 13 mock tests.
- **G3 — tg outbound dispatch** ⏭️ DEFERRED to long-tail. Migration 0022 (`lead.tg_chat_id`), `app/telegram/sender.py`, LeadCard tg-handle field — all still in scope when picked up. Templates with `channel='tg'` still stage `delivery_status='pending'` Activity rows (Sprint 2.5 stub stays).
- **G4 — Enrichment → Celery + WebSocket** ⏭️ DEFERRED to long-tail. Strand-on-failure problem already closed at G1 (`_mark_run_failed`); remaining motivation is real-time progress UI, and the existing 2-second poll is acceptable.
- **G5 — Sprint close** (this commit): SPRINT_2_7_SENTRY_MULTISTEP.md, SMOKE_CHECKLIST_2_7.md, brain rotation (00 + 02 + 04).
- 21 new mock tests (8 G1 + 13 G2). Combined baseline: **133 mock tests passing** (was 112).
- 0 new npm deps in PR; 0 new Python deps. `sentry-sdk[fastapi]` was pre-pinned since 2.1 G10.
- ADRs reaffirmed: ADR-009 (package-per-domain), ADR-018 (LLM provider abstraction), ADR-019 (email lead-scoping). No new ADRs.
- Operator follow-on (3 items, none blocking): `pnpm add @sentry/nextjs` in apps/web; set `SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` in production .env; configure Sentry-side rate limits before noisy crons burn the 5k/month free tier.

**Sprint 3.1 — DONE (merged + deployed)** · `docs/SPRINT_3_1_LEAD_AI_AGENT_REPORT.md` · 4 PRs ([#18](https://github.com/GlobalSasha/drinkx-crm/pull/18), [#19](https://github.com/GlobalSasha/drinkx-crm/pull/19), [#20](https://github.com/GlobalSasha/drinkx-crm/pull/20), [#22](https://github.com/GlobalSasha/drinkx-crm/pull/22)) merged 2026-05-10
- **Lead AI Agent — first Phase 3 slice. All 5 phases shipped in a single day.**
- **Phase A** (PR #18) — Knowledge files: `apps/api/knowledge/agent/lead-ai-agent-skill.md` (behaviour, SPIN-by-stage, output formats, tone, hard rules) + `apps/api/knowledge/agent/product-foundation.md` (DrinkX positioning, S100–S400, segments, top objections, USP map, vocabulary). Original spec placed them under `docs/`; PR #20 co-located them with the API package so the existing `COPY knowledge ./knowledge` Dockerfile line ships them.
- **Phase B** (PR #18) — Migration `0022_lead_agent_state` adds `leads.agent_state JSONB NOT NULL DEFAULT '{}'`. ORM column type narrowed to plain `JSON` for test-stub compat (Postgres still stores JSONB at the migration level).
- **Phase C** (PR #18) — `app/lead_agent/` package: `schemas.py` (AgentSuggestion / ChatMessage / *Request / *Response), `context.py` (lru_cache loaders + soft-fail repo walker + `build_lead_context`), `prompts.py` (SUGGESTION_SYSTEM Flash + CHAT_SYSTEM Pro, FOUNDATION_INJECT_CHARS=3000), `runner.py` (`get_suggestion` Flash + `chat` Pro, both via `complete_with_fallback`, RU graceful fallback on `LLMError`), `tasks.py` (`refresh_suggestion_async` + `scan_silence_async` via per-task NullPool engine), `routers.py` (3 endpoints under `/leads/{id}/agent/`). Celery wrappers in `scheduled/jobs.py`. New beat schedule entry `lead-agent-scan-silence` every 6h sweeps active leads.
- **Operator follow-on** (PR #19) — `apps/api/Dockerfile` repo-root build context + `COPY docs ./docs`. Later superseded by PR #20's knowledge co-location, but the repo-root context is retained.
- **Phase D** (PR #22) — Frontend: 3 React Query hooks (`useAgentSuggestion`, `useRefreshAgentSuggestion` with 12s soft-poll, `useAgentChat`); `AgentBanner.tsx` between LeadCard header and tabs (empty-row state, full state, low-confidence mute, dismiss, refresh); `SalesCoachDrawer.tsx` slide-over chat with static greeting, four quick chips, in-memory history (per skill §8), Esc/backdrop close, optimistic user-turn append, in-line failure message; FAB `🤖 Чак` bottom-right on LeadCard.
- **Phase E** (PR #22) — Two trigger hooks: `app/automation/stage_change.py` adds `trigger_lead_agent_refresh` POST_ACTION (last in list, fires `apply_async(args=[lead.id])` synchronously); `app/inbox/processor.py` after inbound auto-attach + drainer fires same task with `countdown=900` (15-min «менеджер может ответить сам» window). Both wrapped in `try/except` so a broker hiccup never rolls back the parent commit.
- 51 mock-only tests pass throughout. 0 dedicated lead_agent tests — runner is a thin shim around `complete_with_fallback`, routers are read-only or fire-and-forget enqueues. Real verification is the post-deploy smoke check.
- 0 new npm deps; 0 new Python deps. ADRs reaffirmed: ADR-009, ADR-018, ADR-007. No new ADRs.
- Production state: agent endpoints live at `/api/leads/{id}/agent/*`; `lead-agent-scan-silence` beat entry active; FAB + banner visible on every LeadCard.

**Sprint 3.3 — Companies + Global Search (DONE — merged on `main` as PR [#28](https://github.com/GlobalSasha/drinkx-crm/pull/28))**
- Migration 0023 `companies` table + `leads.company_id` + `contacts.workspace_id/company_id` + pg_trgm; 0024 flips `contacts.workspace_id` to NOT NULL after backfill
- `app/companies/` domain package + `app/search/` for global search hitting fuzzy indexes
- Report: `docs/brain/sprint_reports/SPRINT_3_3_COMPANIES.md`

**Sprint 3.4 (team dashboard) — DONE on `main`**
- Activity dashboard + manager-delete tooling (merge commit `69ebe6e`)

**Sprint 3.4 — Unified Inbox: Telegram + Mango + STT (DONE — on `main`, no PR)**
- Single-source report: `docs/brain/sprint_reports/SPRINT_3_4_UNIFIED_INBOX.md`
- MVP variant B (6-day scope): Telegram Business Bot + Mango Office VPBX + SaluteSpeech-транскрипция
- Backend: 2 миграции (0025 `inbox_messages` с transcript/summary/stt_provider, 0026 `leads.tg_chat_id` + `leads.max_user_id`); `ChannelAdapter` Protocol + `TelegramAdapter` + `PhoneAdapter`; `app/inbox/stt/` (Salute / Whisper / factory); Celery `transcribe_call` (download → STT → MiMo summary → Activity body rewrite → 60s Lead-Agent kick); webhooks `POST /api/webhooks/{telegram,phone}` (TG secret-token, Mango HMAC `sign`); routes `POST /leads/{id}/inbox/send` + `POST /leads/{id}/inbox/call` + `GET /leads/{id}/inbox` + `GET /api/inbox/unmatched/messages` + `PATCH /api/inbox/messages/{id}/assign`
- Frontend: 4-й таб «Переписка» в LeadCard (filter / feed / collapsible transcript / composer / call button); секция «Мессенджеры и звонки» на `/inbox`
- 44 mock-теста (test_inbox_messages 10 + test_inbox_telegram 11 + test_inbox_phone 14 + test_inbox_transcribe 9), все зелёные
- Carry-overs: MAX Bot (G3), Gmail send (G5), per-manager Telegram bots через `channel_connections` — TODO зафиксированы в коде; e-mail плечо в `/leads/{id}/inbox` пока пустое (видно на «Активность»)
- ENV to provision: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `DEFAULT_WORKSPACE_ID`, `MANGO_API_KEY`, `MANGO_API_SALT`, `SALUTE_CLIENT_ID`, `SALUTE_CLIENT_SECRET`. Smoke-чеклист в close-report

## 🔜 NEXT

To be decided by the operator after 3.4 Unified Inbox is smoked in production. Candidates:

### Phase 3 — Sprint 3.5 — Inbox follow-ups (~3-4 days)
Carry-overs from 3.4 Unified Inbox.
- **MAX Bot** (G3 carry-over) — `adapters/max_messenger.py` + `POST /api/webhooks/max`; structure is symmetric to TelegramAdapter
- **Gmail send** (G5 carry-over) — request `gmail.send` scope alongside `gmail.readonly` on first connect; existing connections show inline «переподключить» hint; `POST /leads/{id}/inbox/send` for `channel='email'`
- **Per-manager Telegram bots** — store tokens per `(workspace_id, user_id)` in `channel_connections` (mirror Gmail); webhook URL becomes `/api/webhooks/telegram/{connection_id}`; `DEFAULT_WORKSPACE_ID` retires. TODO already in code.

### Phase 3 — Sprint 3.2 — Lead AI Agent polish (~3-5 days)
See historical entry in this doc + the original 3.1 close-report. Parked since the 3.1 close.

**Main driver:** the 3.1 close-report parked five features as out-of-scope for v1 of the agent. They're the natural follow-on once managers actually use the banner and chat drawer in anger.

Tentative scope:
- **Per-suggestion id + persistent dismiss** — currently the «×» button is session-only (refresh brings the suggestion back). Add `suggestion.id` (UUIDv4 generated by the runner) + `agent_state.dismissed_suggestion_ids[]` so a dismissal sticks across page loads. Migration: not needed (JSONB).
- **Manager rating thumbs up/down** — feeds the «менеджер игнорирует советы» pattern in `agent_state.suggestions_log` (skill §11 «Special scenarios»). After 3+ consecutive ignores, the runner softens the prompt tone (already a documented branch in the skill, just unwired today).
- **Chat streaming via SSE / WebSocket** — current sync POST works but feels laggy on long Pro responses. Reuse the WS infrastructure once Sprint 2.7 G4 lands (or stand up SSE separately if G4 keeps slipping).
- **SPIN-analysis of inbound emails through LLM** — replace the pattern-match heuristic in `runner.get_suggestion` with a focused second LLM call (mirror `_extract_contacts_from_sources` in enrichment).
- **Telegram-notification of recommendations** — push the banner to a Telegram bot when the manager isn't on the web (pairs naturally with Sprint 2.8 G3 carryover for tg outbound dispatch).

### Phase 2 — Sprint 2.8 (long-tail)
Tentative parking lot for the items 2.7 deferred:
- **G3 carryover — tg channel outbound dispatch** — Telegram Bot API client, `lead.tg_chat_id` column + LeadCard input, `send_telegram` tri-state contract mirroring `send_email`
- **G4 carryover — Enrichment → Celery + WebSocket** — when manager-facing real-time progress becomes a priority
- **AmoCRM adapter** — long-tail since Sprint 2.1 G5; skipped 2.5 G3
- **Telegram Business inbox** + **email send (gmail.send scope)** — deferred since Sprint 2.0
- **Quote / КП builder**, **Knowledge Base CRUD UI** — deferred from 2.0 envelope
- **`_GENERIC_DOMAINS` per-workspace setting** (Sprint 2.0 carryover)
- **Gmail history-sync resumable / paginated job** (Sprint 2.0 2000-msg cap)
- **Honeypot / timing trap on `embed.js`** (Sprint 2.2 carryover)
- **Pipeline cloning / templates** (Sprint 2.3 deferred; «start from template» CTA in PipelineEditor)
- **Stage-replacement preview** in PipelineEditor (Sprint 2.3 polish carryover)
- **Workspace AI override → fallback chain wiring** (Sprint 2.4 G3 carryover; UI persists, env still wins)
- **Multi-clause condition UI** in Automation Builder modal (backend supports n-clause; frontend ships single row)
- **Multi-step automation polish** — dnd-kit reorder in the builder (lib already on the page from 2.6 G4); pause-mid-chain UI; per-step retry on failure (Sprint 2.7 G2 carryovers)
- **Default pipeline 6–7 stages confirm + ICP fields** (light-touch DB seed change)
- DST-aware cron edge handling
- pg_dump cron install on host (operator step open since 2.4 G5)
- inbox/processor Celery dispatch retry path

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
