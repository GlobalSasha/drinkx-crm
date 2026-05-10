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

**Sprint 2.7 — DONE (merged + deployed)** · `docs/SPRINT_2_7_SENTRY_MULTISTEP.md` · branch `sprint/2.7-sentry-multistep` · PR [#12](https://github.com/GlobalSasha/drinkx-crm/pull/12) merged as `d312410` · sprint close PR [#17](https://github.com/GlobalSasha/drinkx-crm/pull/17) merged as `cf91253`
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

### Phase 3 — Lead AI Agent + UI overhaul

**Sprint 3.1 — DONE (merged + deployed)** · `docs/SPRINT_3_1_LEAD_AI_AGENT.md` · branch `sprint/3.1-lead-ai-agent` · PRs [#18](https://github.com/GlobalSasha/drinkx-crm/pull/18) (Phase A+B+C) + [#19](https://github.com/GlobalSasha/drinkx-crm/pull/19) (Dockerfile docs/) + [#20](https://github.com/GlobalSasha/drinkx-crm/pull/20) (knowledge file move) + [#22](https://github.com/GlobalSasha/drinkx-crm/pull/22) (Phase D + E)
- **Lead AI Agent «Чак» — single agent inside the lead card, two modes on a shared system prompt**
- Migration `0022_lead_agent_state` — `leads.agent_state JSONB NOT NULL DEFAULT '{}'` (ADR-022 — opaque JSONB on the lead row, no separate table)
- **Phase A — knowledge files** — `apps/api/knowledge/agent/product-foundation.md` (7259 chars, DrinkX positioning + S100–S400 + segments + objections + USP-by-situation + voice/tone) + `apps/api/knowledge/agent/lead-ai-agent-skill.md` (14044 chars, dual-mode behaviour, `agent_state` schema, SPIN-by-stage methodology, banner / chat output formats, refusal rules). Co-located with the API package per ADR-026 so Docker `COPY knowledge ./knowledge` ships them to `/app/knowledge/agent/...`
- **Phase C — backend `app/lead_agent/`** package — `schemas.py` (AgentSuggestion + ChatMessage + ChatRequest/Response + SuggestionResponse), `context.py` (lru_cache loaders + `_find_knowledge_root` walker + `build_lead_context` RU prompt block), `prompts.py` (`SUGGESTION_SYSTEM` for Flash/`prefilter` + `CHAT_SYSTEM` for Pro/`sales_coach`, foundation injected at 3000-char cap), `runner.py` (`get_suggestion` + `chat` with graceful soft-fail on LLM/parse errors), `tasks.py` (`refresh_suggestion_async` + `scan_silence_async` async cores), `routers.py` (3 endpoints under `/api/leads/{id}/agent`); registered in `main.py` + `scheduled/jobs.py` + Celery beat entry `lead-agent-scan-silence` `crontab(minute=0, hour="*/6")`
- 3 REST endpoints — `GET /api/leads/{id}/agent/suggestion` (cached read, no LLM), `POST /api/leads/{id}/agent/suggestion/refresh` (202 + Celery), `POST /api/leads/{id}/agent/chat` (sync Sales Coach turn, Pro model)
- **Phase D — frontend** — `apps/web/lib/hooks/use-lead-agent.ts` (useAgentSuggestion + useRefreshSuggestion + useAgentChat), `AgentBanner.tsx` (between LeadCard header and tab strip, ✕ dismisses session-locally, refresh icon kicks Celery, action button opens drawer with seed question), `SalesCoachDrawer.tsx` (slide-in right on desktop / full-screen on mobile, ephemeral history per session, 4 quick chips, optimistic user-turn render), LeadCard wires both + a floating «🤖 AI Coach» FAB at `bottom-6 right-6`
- **Phase E — automation hooks** — `app/automation/stage_change.py` post-actions and `app/inbox/processor.py` after-attach call `lead_agent_refresh_suggestion.delay(lead_id)` (inbox path uses `countdown=900` per spec so the manager has 15 min to react before the agent fires)
- Dockerfile delta (PR #19): build context flipped to repo root + new `COPY docs ./docs` slot; PR #20 then moved the agent knowledge into `apps/api/knowledge/agent/` so the long-term path doesn't depend on `docs/` shipping into the image — leaves the `COPY docs ./docs` line as cosmetic carryover (tracked in `04_NEXT_SPRINT.md` tech debt)
- ADRs: ADR-022 (agent_state JSONB on lead), ADR-023 (Чак naming, no «AI/ИИ» in user-facing text), ADR-026 (knowledge files co-located with API)
- 0 new npm deps; 0 new Python deps; agent rides the existing ADR-018 LLM provider chain (MiMo Flash/Pro → Anthropic → Gemini → DeepSeek)
- **Operator follow-on (none blocking):** Phase D banner relies on the cached suggestion — first-time `scan_silence` will populate banners ~6h after deploy (or sooner if a stage-change / inbound triggers it directly). To bootstrap immediately, run `celery -A app.scheduled.celery_app call app.scheduled.jobs.lead_agent_scan_silence` once on the worker host.

**UI / Design System overhaul — DONE (merged + deployed)** · no single sprint number; commit range `5a2701c..0f32f36` across 13 PRs (May 2026)
- **Brand palette switch — `#FF4E00` orange replaces `#1F4D3F` legacy green** (ADR-024)
- New design tokens module `apps/web/lib/design-system.ts` — `C` object: `C.color.{text,muted,mutedLight,accent}`, `C.button.{primary,ghost,pill,nav}`, `C.form.{label,field}`, `C.bodyXs/Sm`, `C.btn/btnLg`, `C.metricSm`, `C.caption`. New components compose from `C.*`; legacy tokens kept in Tailwind config for back-compat
- `apps/web/tailwind.config.ts` — new `colors.brand.{accent, accent-text, accent-soft, primary, muted, muted-strong, muted-light, border, panel, bg, soft, canvas}` palette; `apps/web/app/globals.css` mirrors as CSS variables for non-Tailwind contexts
- 42-file sweep: `bg-accent → bg-brand-accent`, `text-accent → text-brand-accent`, etc.; `apps/web/lib/ui/priority.ts` priority chip A/B/C/D mapped to brand-accent ramp
- AppShell: animated sliding pill on sidebar nav, `bg-brand-soft` active state
- Prototype carryovers (in `crm-prototype` repo, not this repo): brief-drawer → centered modal, manager-profile screen, onboarding profile fields
- **Today screen rewrite (PRs #6–#11)** — 9-widget dashboard with `@dnd-kit/sortable` drag-and-drop persisted per user in localStorage, time-of-day greeting (🌅☀️🌆🌙) + first name. Widgets: `w-tasks` / `w-followup` / `w-rotting` / `w-pipeline` / `w-focus` / `w-tasklist` / `w-chak` / `w-funnel` / `w-notif` — all wired to real API hooks (mock only for `w-chak` until Sprint 3.1 backend lands). Skeleton loading + em-dash fallback. TaskListWidget v2: real `due_at` time, truncate + tooltip, pagination 4/page, inline quick-add. All elements clickable + deep-link query params (`?tab=tasks`, `?stage={id}`, `?filter=…`). New endpoint `GET /me/followups-pending` (PR #7) returns `{pending_count, overdue_count}` for the counter widget.
- **Lead Card overhaul** — Activity-first default tab (ADR-025); «Следующий шаг» moved from Deal tab into Activity (saving persists `lead.next_step` AND mirrors as a `task` activity in the feed); A/B/C/D priority tooltips with tier descriptions; «SCORE» → «ОЦЕНКА ЛИДА»; «FOLLOW-UPS» → «ЭТАПЫ РАБОТЫ»; priority+score panel capped at `max-w-lg`; new «Вернуть в базу» button (POST `/leads/{id}/unclaim`) gated by `lead.assigned_to === me.id` → `router.push('/pipeline')`; `BriefDrawer.tsx` removed (289 lines), pipeline-store cleaned of `selectedLead`/`visibleLeads`/`openDrawer`
- **Pipeline overhaul** — direct nav from cards (`router.push(/leads/{id})` instead of drawer), drawer code path deleted; deep-link `?stage={id}` scrolls the matching column into view via `id="stage-col-{id}"` on `PipelineColumn`; `?filter=rotting` / `?filter=followup_overdue` are read but not yet applied (waiting on `quickFilter` field in pipeline store — `04_NEXT_SPRINT.md` priority 3)
- **17-file Russian-language sweep** — Pipeline → Воронка, Inbox → Входящие, Settings → Настройки, etc. Kept on English (justified): `Slug`, `Fit`, `Follow-up`, `Gmail`/`Telegram`/`LinkedIn`, `AI`, `HoReCa`/`QSR`
- **Infra**: ESLint 9 flat config via FlatCompat (PR #5) — 14 pre-existing warnings, 0 errors. CLAUDE.md doc updates (PR #16) reflect bare-metal deploy (not Vercel/Railway) + Pre-PR checklist requiring `pnpm build` on PRs that touch `<Link href={non-literal}>` or `useSearchParams` (typed-routes + Suspense rules only fire under `next build`, not `tsc --noEmit` — burned 3 deploys before the rule was written down; see PR [#15](https://github.com/GlobalSasha/drinkx-crm/pull/15)). Production deploy bake-out: PRs #15, #19, #20 between them resolved typed-route bug, Dockerfile context, knowledge-file location.

## 🔜 NEXT

### Sprint «Infrastructure & Polish» — READY TO START
See `docs/brain/04_NEXT_SPRINT.md` for the full plan.

After Sprint 3.1 closed the Lead AI Agent loop, the next priority
is hardening the deploy + bringing the three remaining screens
(`/inbox`, `/settings`, `/automations`) onto the brand palette.

Priority order:
1. **CI + Branch Protection (HIGH)** — `apps/web/.github/workflows/web.yml` (pnpm install → tsc → eslint → `pnpm build`), `apps/api/.github/workflows/api.yml` (uv sync → pytest), branch protection on `main`. The May 2026 deploy bake-out (PRs #15, #19, #20) made it clear that `tsc --noEmit` doesn't cover Next.js typed routes / Suspense rules — `pnpm build` has to run on every PR.
2. **Design System carryover screens (MEDIUM)** — `/inbox`, `/settings` + sub-sections, `/automations` still on legacy `bg-canvas / text-accent green` tokens. Sweep to `C.*` + `bg-brand-*`.
3. **Pipeline quick-filters (MEDIUM)** — `?filter=rotting` and `?filter=followup_overdue` are read in `pipeline/page.tsx` but not applied (no matching action in `pipelineStore`). Add `quickFilter` field + `setQuickFilter` action; the existing `useEffect` already depends on `filterParam` — only the body changes.
4. **Sentry activation (LOW)** — Sprint 2.7 G1 wired the chokepoint; operator just needs `pnpm add @sentry/nextjs` + DSNs in production env, plus a Sentry-side rate-limit on noisy crons.

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
- **`AgentSuggestion.manager_action` extension** — Sprint 3.1 simplified the schema by dropping `manager_action`; PATCH «accept / ignore» endpoint isn't built. When recommendation-quality metrics matter, extend `AgentSuggestion` schema + add `PATCH /api/leads/{id}/agent/suggestion/action`.

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
