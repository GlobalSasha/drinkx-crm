# DrinkX CRM — Current State

Last updated: 2026-05-10 (Sprint 2.7 DONE on branch `sprint/2.7-sentry-multistep`, PR [#12](https://github.com/GlobalSasha/crm/pull/12); G3 + G4 deferred to long-tail. Sprint 2.6 already merged into main.)

## Phase 0 — COMPLETED ✅ (lives in `crm-prototype` repo)

Clickable HTML prototypes deployed at https://globalsasha.github.io/drinkx-crm-prototype/

| File | Description |
|---|---|
| `index.html` | Service-grade prototype, 11+ screens, 7+ modals, 3 drawers — full functionality |
| `index-soft-full.html` | taste-soft hi-fi version (Plus Jakarta Sans + double-bezel) |
| `index-soft.html` | Landing / preview page |
| `index-b2b.html` | **B2B enterprise design reference** — 11-stage pipeline, gate criteria, 0-100 scoring, multi-stakeholder, deal type, A/B/C/D priority, dual rotting, pilot contract |
| `data.js` | 131 real DrinkX clients with full enrichment |
| `drinkx-client-map-v0.6-foodmarkets-audit/` | +85 foodmarkets candidates added 2026-05-06 |
| `docs/PRD-v2.0.md` | 988-line product requirements |
| `build_data.py` | Parses drinkx-client-map → data.js |

---

## Phase 1 — IN PROGRESS (production repo `drinkx-crm`)

Production: https://crm.drinkx.tech (live, healthy, auto-deploys on push)
Repo: https://github.com/GlobalSasha/drinkx-crm

### Production stack (4 app containers + 2 infra)

```
drinkx-api-1       FastAPI + Alembic, port 8000 (127.0.0.1)
drinkx-web-1       Next.js 15 + standalone, port 3000 (127.0.0.1)
drinkx-worker-1    Celery worker — concurrency=2
drinkx-beat-1      Celery beat — 4 cron entries (unchanged in Sprint 2.1):
                     :00 hourly  → daily_plan_generator
                     :*/15       → followup_reminder_dispatcher
                     :30 hourly  → daily_email_digest (Sprint 1.5)
                     :*/5        → gmail_incremental_sync (Sprint 2.0)
                   + Manual-trigger tasks (Sprint 2.1):
                     bulk_import_run, run_bulk_update, run_export
drinkx-postgres-1  Postgres 16
drinkx-redis-1     Redis 7
```

nginx outside Docker reverse-proxies HTTPS → containers on localhost.

### ✅ Sprint 1.0 — Foundation (DONE)
- Monorepo, Docker stack, GitHub Actions auto-deploy on push to main (~90s).

### ✅ Sprint 1.1 — Auth (DONE — Supabase live)
- SQLAlchemy 2 async models: Workspace / User / Pipeline / Stage
- JWT verifier supports legacy HS256 AND modern asymmetric ES256/RS256 via JWKS endpoint (10-min cache)
- Auto-bootstrap workspace + 11 B2B stages on first sign-in
- `@supabase/ssr` browser/server/middleware clients, root middleware protects authed routes, `/auth/callback` exchanges OAuth code for session, sign-in with Google + magic link
- `api-client` transparently attaches Bearer token from current Supabase session

### ✅ Sprint 1.2 — Core CRUD with B2B model (DONE — backend + frontend + import)
- Migration 0002: 5 new tables (leads, contacts, activities, followups, scoring_criteria); 11 B2B stages; gate_criteria_json
- Lead REST: CRUD + filters + Lead Pool + race-safe Sprint claim + transfer
- Stage transitions through `app/automation/stage_change.py` with gate engine (hard `check_pipeline_match` + soft `check_economic_buyer_for_stage_6_plus`)
- AppShell sidebar; pages /today, /pipeline, /leads-pool, /leads/[id]; Lead Card with 5 tabs; Pipeline drag-drop
- 216 leads imported from prototype data (131 v0.5 + 85 v0.6 foodmarkets)

### ✅ Sprint 1.3 — AI Enrichment (DONE — Phases A+B+C+D+E+F)
- LLMProvider Protocol + 4 providers (MiMo primary, Anthropic / Gemini / DeepSeek fallback chain)
- Sources: Brave + HH.ru + web_fetch with 24h Redis cache
- Migration 0003: `enrichment_runs` + Research Agent orchestrator
- AI Brief tab on Lead Card with hero band, fit_score badge, score_rationale, growth/risk signals, decision-maker hints, next-steps
- DrinkX `profile.yaml` injected into synthesis prompts; KB markdown library (segment-tagged playbooks + always-on objections / competitors / icp_definition)
- Cost guards: per-lead 1-running rate limit, workspace concurrency cap, daily budget cap (Redis counter)
- Synthesis prompt forbids jargon; MiMo strict-validates params (we keep payload to OpenAI-spec basics)

### ✅ Sprint 1.4 — Daily Plan + Follow-ups (DONE — Phases 1+2+3 + 4 hotfixes)
**First Celery service in the system.**

Backend:
- Migration 0004: `daily_plans`, `daily_plan_items`, `scheduled_jobs` (UNIQUE(user_id, plan_date) for upsert)
- Migration 0005: `followups.dispatched_at` for idempotency
- `priority_scorer.score_lead()` pure function with module-level tunable weights (overdue + due_soon + priority A/B/C + rotting + fit_score; archived/unassigned penalties)
- `DailyPlanService.generate_for_user()` — score → pack into work_hours → MiMo Flash 1-line hints (deterministic fallback) → time-block spread → upsert; budget guard reused from Sprint 1.3
- Celery `"drinkx"` app on Redis broker+backend, UTC clock, `task_time_limit=600s`
- Cron beat:
  - `daily-plan-generator` hourly at :00, picks workspaces where `user.timezone`-local hour == 08:00
  - `followup-reminder-dispatcher` every 15 min, creates `Activity(type='reminder')` for followups due in +24h, idempotent via `dispatched_at`
- Audit: `ScheduledJob` row per cron tick (status / affected_count / error)
- REST: `GET /api/me/today`, `GET /api/daily-plans/{date}`, `POST /api/daily-plans/{date}/regenerate` (202 + Celery), `POST /api/daily-plans/items/{id}/complete`

Frontend:
- `/today` rewritten with real plan rendering: states empty/generating(shimmer+2s poll)/failed/ready
- Time-block sections: Утро / День / После обеда / Вечер / Без времени
- Compact card design (~72px target via single primary row + sub-hint), URL-driven pagination 10/page (`?page=N`); "hot lead" 2px left rail when `priority_score >= 80`
- "🔄 Пересобрать план" button triggers Celery `regenerate_for_user`

Infra:
- `infra/production/docker-compose.yml`: api env extracted to `&api-env` YAML anchor; new `worker` (concurrency=2) and `beat` services share image + env
- `apps/web/Dockerfile`: bumped to `node:22-alpine` (corepack auto-upgraded to pnpm 11 which dropped Node 20)
- `apps/web/package.json`: pinned `packageManager: pnpm@10.18.0` + `onlyBuiltDependencies` allow-list (corepack reproducibility)

### ✅ Sprint 1.5 — Polish + Launch (DONE — merged + live in production)
**8 groups + 2 post-merge hotfixes · merged `4261526` · current main HEAD `434428c`**

Backend:
- Migration `0006_notifications` — `notifications` table + 3 indexes; emit hooks in lead transfer / enrichment success+failure / daily plan ready / followup_due
- Migration `0007_audit_log` — append-only `audit_log` + admin-only `GET /audit`; emit hooks in lead.create / lead.transfer / lead.move_stage / enrichment.trigger
- `app/notifications/email_sender.py` + `digest.py` + `templates/daily_digest.html` — daily morning digest (top-5 plan items, top-5 overdue followups, top-5 yesterday's briefs); stub mode while `SMTP_HOST=""`
- New Celery task `daily_email_digest` + beat entry `crontab(minute=30)`
- 22 mock-only tests (10 notifications + 7 audit + 5 digest), 0 DB / 0 SMTP / 0 network

Frontend:
- AppShell: bell icon + drawer (30s polling) + admin-only "Журнал" link + mobile hamburger overlay
- `/audit` admin page — filter chips + table + pagination
- `/today`, `/leads/[id]`, `/pipeline` — mobile responsive pass (≥375px)
  - `/pipeline` mobile fallback: read-only `PipelineList` grouped by stage
  - `/leads/[id]` mobile: rail stacks above tab content, `<select>` tab switcher
- LeadCard header chips refactor — Stage / "Приоритет X" / Deal type / Score "X/100" / "AI X/10" with color bands; Won/Lost banner; functional Передать modal (UUID input, replaces toast stub); Won/Lost buttons disabled when terminal
- AIBriefTab empty state: "ICP" → "портретом идеального клиента"
- `useMe()` hook against `/auth/me` (frontend now knows backend role)
- `tsc --noEmit` clean; `next build` clean (10 routes, no new warnings)
- 0 new npm dependencies

See `docs/brain/sprint_reports/SPRINT_1_5_POLISH_LAUNCH.md` for the full report.

**Post-merge hotfixes** (committed direct to main after sprint close):
- `9a580cd` `fix(nginx): increase proxy_buffer_size for Supabase 2.x cookie stack` — `/auth/callback` was returning 502 because Supabase JS 2.x cookie chunks (sb-access-token + sb-refresh-token + chunked PKCE auth-token) overflowed the 8K default `proxy_buffer_size`. Bumped to 16k / 32k. Applied manually on VPS first, then mirrored into `infra/production/nginx/crm.drinkx.tech.conf`.
- `434428c` `fix(web): make sidebar logo clickable, links to /today` — desktop sidebar logo was a `<span>`; now wraps in `<Link href="/today">` matching the mobile top-bar pattern.

**Production state at session close:**
- All 6 containers up, api healthy
- Migrations `0006_notifications` + `0007_audit_log` applied
- Beat firing 3 cron entries (daily_plan_generator @ :00 hourly, followup_reminder_dispatcher @ */15, daily_email_digest @ :30 hourly)
- Worker registered all 4 tasks (3 cron + `regenerate_for_user` manual)
- Sign-in flow verified working end-to-end
- Logo home-link verified working

### ✅ Sprint 2.0 — Gmail Inbox sync (MERGED + DEPLOYED — `2938810` is current `main` HEAD)
**7 groups, commit range `8745394..2938810`**

Backend:
- Migration `0008_channel_connections` — workspace+user FKs, channel_type, credentials_json (TEXT plaintext for v1, encryption TODO 2.1), status, extra_json (cursor + audit), last_sync_at + 2 indexes
- Migration `0009_inbox_items_and_activity_email` — `inbox_items` table (workspace+user FKs, gmail_message_id UNIQUE, suggestion JSON, partial-unique on activities.gmail_message_id) + activities adds gmail_message_id / gmail_raw_json / from_identifier / to_identifier + subject widened 300→500
- New `app/inbox/` package: `gmail_client` (async wrapper, auto-refresh, fail-soft), `oauth` (HMAC-signed state, exchange flow), `email_parser` (stdlib-only Gmail-payload walker), `matcher` (contact 1.0 → lead 0.95 → unique-domain 0.7, generic-mailbox skip), `processor` (parse → dedup → match → store, rolls back on any failure), `sync` (history + incremental cores), `services` (list/count/confirm/dismiss with audit hooks), `routers` (REST), `schemas`, `models` (ChannelConnection + InboxItem)
- New Celery tasks: `gmail_history_sync(user_id)` (one-shot 6-month backfill, 2000-msg cap), `gmail_incremental_sync` (every-5-min via Gmail History API), `generate_inbox_suggestion(item_id)` (MiMo Flash via TaskType.prefilter, fail-soft)
- Beat: 4th cron `gmail-incremental-sync */5` (configurable via `GMAIL_SYNC_INTERVAL_MINUTES`)
- AI Brief synthesis injects last 10 email Activities as `### Переписка с клиентом` system-prompt section (cap 2000 chars, body preview 200 chars per email)
- Email-context invariant: ADR-019 — `Activity.user_id` is audit trail, not visibility filter

Frontend:
- New `/inbox` page: pending list with AI suggestion chips (create_lead green / add_contact blue / match_lead gray) or `AI анализирует…` spinner; action buttons (Создать карточку modal, Привязать к лиду dropdown, Игнор optimistic hide); pagination 20/page; empty state with `Подключить Gmail` CTA
- AppShell: `Входящие` promoted out of disabled list with red-dot pending badge (30s poll, 99+ cap), same style as the bell
- Lead Card Activity Feed: new `EmailActivityItem` branch — direction icon ← / →, sender, bold subject, 200-char body preview with `Показать полностью` toggle
- 5 new hooks in `lib/hooks/use-inbox.ts`: useInboxCount, useInboxPending, useConfirmItem, useDismissItem, useConnectGmail

Tests:
- 18 mock-only Sprint 2.0 tests across `test_inbox_matcher.py` (9), `test_email_context_in_brief.py` (3), `test_inbox_services.py` (6). Combined with Sprint 1.5 baseline: 30 mock tests passing, 0 DB, 0 network.
- `pnpm typecheck` + `pnpm build` clean throughout the sprint

Architecture decisions:
- ADR-019 — Email ownership model lead-scoped, not manager-scoped
- Variant 1 ownership = per-user channels in v1 (workspace-level allowed by schema for v2 drop-in)
- Gmail History API (polling), not Push/Pub-Sub
- Auto-attach threshold 0.8; below → human review via inbox_items
- 18-entry hardcoded `_GENERIC_DOMAINS` skip-set
- Raw payload kept inline if < 50KB, dropped otherwise

Known issues / risks (full list in `SPRINT_2_0_GMAIL_INBOX.md`):
1. ~~`credentials_json` stored as plaintext~~ — addressed in **Sprint 2.1 G1**: Fernet encryption with prefix marker, graceful stub-mode fallback while `FERNET_KEY` is empty
2. 2000-message history-sync cap — TODO if a workspace exceeds it
3. `generate_inbox_suggestion` not yet bench-tested with real MiMo
4. `_GENERIC_DOMAINS` hardcoded — TODO promote to per-workspace setting
5. `pnpm-lock.yaml` generated by G4 `pnpm install` not committed (housekeeping)
6. ~~Migrations 0008 + 0009 NOT YET applied on production~~ — applied automatically via the api Dockerfile entrypoint (`uv run alembic upgrade head && uv run uvicorn`); `2938810` deploy verified web/api 200
7. `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` not yet in production `.env` — graceful 503 on `Подключить Gmail` until set; rest of CRM unaffected

### ✅ Sprint 2.1 — Bulk Import / Export + AI Bulk-Update (READY FOR REVIEW — branch `sprint/2.1-bulk-import-export`)
**9 groups + G10 close (G5 AmoCRM deferred), commit range `46cc6a2..HEAD`**

Backend:
- Migration `0010_import_jobs` — `import_jobs` (workspace+user FKs, status enum, format enum, source_filename, upload_size_bytes, total/processed/succeeded/failed counters, error_summary, diff_json, created_at, finished_at) + `import_errors` (FK CASCADE, row_number, field, message)
- Migration `0011_export_jobs` — `export_jobs` (workspace+user FKs, status/format enums, filters_json, row_count, error, redis_key, created_at, finished_at) + `(workspace_id, created_at DESC)` index
- New `app/import_export/` package: parsers (XLSX/CSV/JSON/YAML with auto-detect delimiter + utf-8/cp1251 fallback), mapper (stdlib fuzzy match + conflict resolution), validators (email/INN/deal_amount/priority), exporters (5 formats incl. Markdown ZIP), snapshot (YAML for AI bulk-update), diff_engine (compute_diff with batched 3-query resolve + apply_diff_item), services (job lifecycle), routers (10 endpoints split across `/api/import` and `/api/export`)
- New adapters: Bitrix24 (RU CSV with auto-detect via header signature, drops 8 bookkeeping columns), bulk_update (DrinkX Update Format v1.0 from external LLM)
- New Celery tasks: `bulk_import_run` (per-row commit, real-time UI poll), `run_export` (Celery + Redis blob), `run_bulk_update` (diff apply with per-item rollback)
- Redis bytes client (separate, no `decode_responses` so binary blobs survive)
- Credentials encryption via Fernet (Sprint 2.0 carryover): `fernet:` prefix in existing TEXT column, graceful stub-mode fallback when FERNET_KEY empty, hard-fail on encrypted-row + missing-key

Frontend:
- New `/import` wizard: 4-step modal on `/pipeline` (upload → mapping → preview → progress); skips mapping step when uploaded file is bulk_update_yaml format
- New «Экспорт» popover on `/pipeline` + `/leads-pool`: 5 format radio cards + AI Brief toggle + scope info; phase machine (idle → loading → polling → done|error); auth-aware blob download via `lib/download.ts` (works on prod cross-origin)
- New «AI Обновление» modal on `/leads-pool`: 3-step (download snapshot → copy prompt → handoff to ImportWizard)
- BulkUpdatePreview component for the AI bulk-update step 3: per-item collapsible rows with Change list, op-specific icons (+/−/↻/~), error panel separate
- ImportWizard mounted globally in `(app)/layout.tsx` so any page can open it via pipeline-store

Architecture decisions (full list in `SPRINT_2_1_BULK_IMPORT_EXPORT.md`):
- Diff resolution via 3 batched queries, not N round-trips
- Stage moves via diff bypass gate engine — preview UI is the human-in-the-loop ADR-007 gate
- `is_bulk_update_yaml` is a 1KB regex sniff, not a yaml.safe_load
- Per-item commit in apply tasks for real-time UI poll
- Redis blob storage for exports (TTL 1h)
- Separate `redis_bytes.py` client without `decode_responses`
- Credentials at rest: prefix marker, not BYTEA migration

Tests:
- 64 mock-only Sprint 2.1 tests (crypto 6, import_jobs_service 6, import_parsers 16, bitrix24_adapter 9, exporters 10, snapshot 6, bulk_update 11). Combined with Sprint 1.5/2.0 baseline: **94 mock tests passing**, 0 DB, 0 network.
- `pnpm typecheck` + `pnpm build` clean throughout, 0 new npm dependencies

Known issues / risks (carryover-aware):
1. `_GENERIC_DOMAINS` (Sprint 2.0) — still hardcoded, TODO 2.2+
2. Gmail history-sync 2000-msg cap (Sprint 2.0) — TODO 2.2+ with resumable job
3. `pg_dump` cron (Sprint 1.5) — still not configured
4. ~~`credentials_json` plaintext~~ — closed in 2.1 G1
5. ~~`pnpm-lock.yaml` not committed~~ — closed in 2.1 G10
6. `apps/web/package-lock.json` is stale npm lockfile, causes Next.js multi-lockfile warning — TODO 2.2 G1 housekeeping
7. Sentry DSNs still empty — backend init wired since 1.0, web stub added in 2.1 G10; operator just needs to set env vars + `pnpm add @sentry/nextjs`
8. `FERNET_KEY` required pre-deploy — generation command in `SPRINT_2_1_BULK_IMPORT_EXPORT.md`
9. AmoCRM adapter (G5) deferred — same plumbing as Bitrix24, lands in 2.2+
10. E2E UX smoke deferred to staging — all Sprint 2.1 verifications are structural (`tsc`, `next build`, mock pytest)

### ✅ Sprint 2.2 — WebForms (READY FOR REVIEW — branch `sprint/2.2-webforms`)
**4 groups, commit range `32b5d79..HEAD`**

Backend:
- Migration `0012_webforms` — `web_forms` (workspace_id CASCADE, name, slug UNIQUE, fields_json, target_pipeline_id SET NULL, target_stage_id SET NULL, redirect_url, is_active default true, submissions_count default 0, created_by SET NULL, created_at, updated_at) + `form_submissions` (web_form_id CASCADE, lead_id SET NULL, raw_payload, utm_json, source_domain, ip, created_at) + indexes
- New `app/forms/` package: models, schemas (FieldDefinition + WebFormOut + FormSubmissionOut), repositories, services (create_form auto-slug + IntegrityError retry × 3, soft_delete, update with model_dump exclude_unset), slug.py (stdlib-only RU translit + 6-char base36 random suffix), routers (admin REST, admin/head gated for write), public_routers (`/api/public/forms/{slug}/{submit,embed.js}`), rate_limit (Redis INCR + conditional EXPIRE, fail-open envelope), embed.py (self-contained ~90-line JS blob, once-loaded guard via `window.__drinkxFormLoaded_<slug>`), lead_factory (FORM_FIELD_TO_LEAD case-insensitive RU+EN dictionary, projects payload → Lead in pool, ADR-007 compliance — never assigns / never advances stage / never triggers AI)
- `PublicFormsCORSMiddleware` (Starlette `BaseHTTPMiddleware`) — wildcard CORS scoped to `/api/public/*` only; global `CORSMiddleware` stays restrictive
- Activity types extended: `form_submission` joins the enum (DB column is `String(30)`, no migration); `Activity(type='form_submission')` carries `{form_name, form_slug, source_domain, utm}` for the Activity-Feed render

Frontend:
- New `/forms` admin page (admin/head gated, redirect non-privileged via `useMe`): sticky header + table (name + slug + submissions_count + is_active toggle + relative-time + delete) + empty state + confirm-delete modal explaining soft-delete semantics
- New `FormEditor` modal — «Настройки» tab (name + fields editor with stable `_clientId` keys + target stage flat picker + redirect URL) and «Встроить» tab (composes full snippet from `embed_snippet`, copy button with `clipboard.writeText` + select-fallback, direct embed.js URL, slug-stability tip)
- AppShell: «Формы» nav item with ClipboardList icon, gated to admin/head
- Lead Card Activity Feed: new `form_submission` branch — ClipboardList icon, bold form name, source domain mono, optional UTM source; «Заявки» filter chip
- Lead Card header: `source` chip (mono, max-w-[180px], truncate with title attr) — surfaces provenance (form:slug, import:bitrix, manual…)

Tests:
- 18 mock-only Sprint 2.2 tests (`test_webforms.py` 9 + `test_public_submit.py` 9), 0 DB / 0 Redis / 0 network
- Combined with Sprint 1.5 / 2.0 / 2.1 baseline: **117 mock tests passing**
- `pnpm typecheck` + `pnpm build` clean (12 routes prerender, was 11)
- 0 new npm deps; 0 new Python deps

Architecture decisions (full list in `SPRINT_2_2_WEBFORMS.md`):
- Scoped `PublicFormsCORSMiddleware`, not global wildcard
- Per-`(slug, ip)` rate-limit, not per-IP global
- Once-loaded guard in embed.js, not idempotent rendering
- Soft-delete returns 410 Gone (not 404) so embed.js doesn't crash landing pages
- `form_submission` separate Activity type, not a plain comment — keeps provenance from being eroded by manager-edited comments and lets filter chips separate the two

Known issues / risks (full list in `SPRINT_2_2_WEBFORMS.md`):
1. `target_stage_id` workspace validation client-side only — backend service-layer check TODO Sprint 2.3
2. Notification fan-out has no debounce — bot abuse could page every admin
3. CORS preflight smoke test deferred to staging (needs real DNS)
4. ~~Sentry `@sentry/nextjs` package~~ — still carryover from 2.1, not addressed
5. No honeypot / CAPTCHA on public endpoint — rate-limit alone protects v1

### ✅ Sprint 2.3 — Multi-pipeline switcher (MERGED + DEPLOYED — `b306a97`)
**4 groups, commit range `4294988..b306a97`**

Backend:
- Migration `0013_default_pipeline` — `workspaces.default_pipeline_id` (UUID NULL FK to pipelines.id ON DELETE SET NULL) + two-pass backfill (prefer `pipelines.is_default=true`, fall back to oldest pipeline). Legacy `is_default` boolean kept for diff_engine + back-compat.
- `app/pipelines/services.py` (NEW) + `app/pipelines/repositories.py` extended: `list_pipelines / get_pipeline_or_404 / create_pipeline / update_pipeline (rename + replace_stages) / delete_pipeline (with PipelineHasLeads + PipelineIsDefault guards) / set_default_pipeline (with admin/head notify fan-out)`. Custom exceptions map cleanly to HTTP via the router.
- `app/pipelines/routers.py` — 5 endpoints under `/api/pipelines` with admin/head gating: `GET / (list)`, `GET /{id}`, `POST /`, `PATCH /{id}`, `DELETE /{id}` (structured 409 with `code` + `lead_count` / `message`), `POST /{id}/set-default`. All write endpoints emit audit log rows (`pipeline.create / pipeline.delete / pipeline.set_default`).
- `app/leads/{routers,repositories}.py` — new `pipeline_id` filter on `GET /leads`. /today + /leads-pool intentionally don't pass it.
- `app/auth/{models,services,schemas}.py` — `Workspace.default_pipeline_id` Mapped column with `foreign_keys` disambiguation; bootstrap_workspace also sets the FK; `WorkspaceOut.default_pipeline_id` so the switcher hydrates cold-load without an extra round-trip.
- `app/forms/services.py` (Sprint 2.2 G4 carryover) — new `WebFormInvalidTarget` exception + `_validate_target` helper that checks `target_pipeline_id` belongs to the form's workspace and `target_stage_id` is a child of it. Closes the cross-workspace leak documented in `SPRINT_2_2_WEBFORMS.md`.

Frontend:
- New `/settings` page with left-sidebar layout. «Воронки» live; «Профиль» / «Команда» / «Уведомления» / «Интеграции» / «API» are «Скоро» stubs marked for Phase 2.4+.
- `PipelinesSection.tsx` — pipeline table (Название / Стадий / «По умолчанию» / 🗑) with set-default + delete actions. Three-branch friendly delete modal consuming the structured 409 detail (`pipeline_has_leads` / `pipeline_is_default` / happy-path confirm).
- `PipelineEditor.tsx` — max-w-2xl modal with `@dnd-kit` sortable stage list, color picker, rot_days input. Min-1-stage validation. Full-replacement on PATCH (matches `replace_stages` backend contract).
- `PipelineSwitcher.tsx` — chevroned dropdown with «по умолчанию» badge + «Управление воронками →» link. Single-pipeline workspaces see a non-interactive chip (no false implication of switchability).
- `lib/store/pipeline-store.ts` — `selectedPipelineId` + `setSelectedPipeline` + `hydrateSelectedPipeline`. localStorage namespaced as **`drinkx:pipeline:{workspaceId}`** (risk #2 from `04_NEXT_SPRINT.md` — prevents cross-workspace selection leak).
- `lib/hooks/use-pipelines.ts` — `usePipelines / usePipeline / useCreate/Update/Delete/SetDefaultPipeline` with proper invalidation chains.
- AppShell — «Настройки» nav item promoted out of the disabled list.

Tests:
- 12 mock-only Sprint 2.3 tests in `test_pipelines_service.py` (10 G1 + 2 G4 — fan-out happy path + fan-out failure swallowed). 0 DB / 0 Redis / 0 network.
- Combined with Sprint 1.5 / 2.0 / 2.1 / 2.2 baseline: **129 mock tests passing**.
- `pnpm typecheck` + `pnpm build` clean throughout. **13 routes prerender** (was 12; `/settings` is the new one at 7.61 kB).
- 0 new npm deps; 0 new Python deps.

Architecture decisions (full list in `SPRINT_2_3_MULTI_PIPELINE.md`):
- `workspaces.default_pipeline_id` FK as the single source of truth, not the legacy `pipelines.is_default` boolean
- Per-workspace localStorage namespace for switcher state
- Single-pipeline workspaces show a chip, not a dropdown
- Optimistic DELETE → structured 409 (no pre-flight endpoint added)
- `as any` cast convention for typedRoutes same-build new routes (codebase-universal pattern)
- Sprint 2.2 G4 cross-workspace forms validation bundled into G1

Known issues / risks (full list in `SPRINT_2_3_MULTI_PIPELINE.md`):
1. Browser E2E smoke deferred to staging
2. `as any` carryover in `PipelineSwitcher` + `AppShell` (typedRoutes limitation)
3. ~~Sentry `@sentry/nextjs` package~~ — still carryover from Sprint 2.1
4. Per-stage gate-criteria editor not exposed (Phase 3)
5. Pipeline cloning / templates deferred (Sprint 2.4+)
6. PATCH stage replacement is full-list, no row-level merge — leads at deleted stages drop to `stage_id=null` until reassigned
7. No multi-pipeline reporting (Phase 3)
8. set-default notification fan-out has no debounce (acceptable for a config event)

### 🔥 Post-Sprint 2.3 emergency hotfixes (2026-05-08, all in main)

A user-reported `/leads-pool` failure exposed three latent bugs in
sequence. All four fixes are deployed to production.

| Commit | Fix |
|---|---|
| `8349516` | `list_pool` page_size cap raised 200 → 500. Latent since `480d0a9` (2026-05-07): /leads-pool started fetching the whole pool with `page_size=500` for client-side filtering, but the backend cap rejected with 422 on every request. /leads-pool was silently broken for ~24h. |
| `904a0d2` | Typo «леды» → «лиды» in /leads-pool empty-state copy. |
| `9d6ef92` | Migration 0014 — defensive bootstrap of orphan workspaces. Idempotent: finds workspaces with zero pipelines and seeds «Новые клиенты» + 12 stages, sets `default_pipeline_id`. No-op for healthy databases. |
| `6781145` | **Single-workspace model (ADR-021)** + migration 0015. The previous `bootstrap_workspace` created a NEW workspace per first-time signing user → two production silos accumulated («Gmail» 1fa8ccb3-… 216 leads, «Drinkx» 456610a9-… 0 leads). Refactored auth bootstrap so subsequent users join the canonical (oldest) workspace as `manager`; first-ever user is `admin`. Workspace name now from `WORKSPACE_NAME` env var. Migration 0015 folded Gmail INTO Drinkx (leads remapped by stage NAME). Both team members now see the same 216 leads. |

After the hotfixes:
- Combined mock-test baseline: **132 mock tests passing** (Sprint 2.3 baseline 129 + 3 new auth tests).
- Migrations applied: `0013_default_pipeline`, `0014_bootstrap_orphan_workspaces`, `0015_merge_workspaces`.
- Single-workspace assumption now baked in for the entire team. Multi-tenancy (second client) is Phase 3.

### ✅ Sprint 2.4 — Full Settings panel + Templates (DONE — branch `sprint/2.4-settings-templates`, pending merge)
**5 groups complete. Single merge to main scheduled after G5 commit lands.**

Commit range: `01e104a..HEAD` on `sprint/2.4-settings-templates`.

Full sprint report: `docs/SPRINT_2_4_SETTINGS_TEMPLATES.md`.

Gates summary:
- **G1** (`01e104a`) Settings «Команда» + drop `pipelines.is_default`
- **G2** (`871467c`) Settings «Каналы»
- **G3** (`12be0d6`) Settings «AI» + «Кастомные поля» (migration 0018)
- **G4** (`1ff4419`) Templates module (migration 0019)
- **G4.5** (`36a4c97`) Quick wins (accent / dropzone / audit labels)
- **G5** (this commit) Audit user-join + formatDelta + notifications click split + dismiss endpoint + priority colour centralization (`lib/ui/priority.ts`) + `scripts/pg_dump_backup.sh` + `docs/crontab.example` + sprint report + smoke checklist + brain memory rotation.

New modules in this sprint:
- `apps/api/app/users/` (G1)
- `apps/api/app/settings/` (G2 + G3)
- `apps/api/app/custom_attributes/` (G3)
- `apps/api/app/template/` (G4 — singular per CLAUDE.md domain registry; route prefix `/api/templates`)
- `apps/web/lib/ui/priority.ts` (G5)
- `scripts/pg_dump_backup.sh` (G5 — soft-launch carryover from 1.5)
- `docs/SPRINT_2_4_SETTINGS_TEMPLATES.md` (G5)
- `docs/SMOKE_CHECKLIST_2_4.md` (G5)
- `docs/crontab.example` (G5)

Test baseline (mock-only, the codebase pattern): **281 passed / 14 pre-existing failed (env-related, fastapi import) / 58 skipped**.

`pnpm typecheck` clean throughout. 0 new npm deps; 0 new Python deps in this sprint.

Old per-gate notes preserved below for reference; the canonical write-up lives in the sprint report.

Commit range: `01e104a..HEAD`.

#### G1 — Settings «Команда» + drop legacy `pipelines.is_default` ✅ DONE (`01e104a`)

Backend:
- New `app/users/` package: schemas / repositories / services / routers + `supabase_admin.py` (httpx wrapper around Supabase admin REST `invite_user_by_email`, stub-mode when SUPABASE_SECRET_KEY empty).
- 4 endpoints under `/api/users`: `GET /` (all roles), `GET /invites` (all roles), `POST /invite` (admin), `PATCH /{id}/role` (admin).
- Custom exceptions map to HTTP: UserNotFound (404), InvalidRole (400), LastAdminRefusal (409 with `code: last_admin`), InviteSendFailed (502 with `code: invite_send_failed`).
- Idempotent re-invite: existing (workspace, email) row → re-send magic-link, no duplicate INSERT.
- `app/auth/models.py:UserInvite` ORM class — workspace-scoped, FK SET NULL on `invited_by_user_id`, unique (workspace_id, email).
- Migration `0016_user_invites` — table + indexes.
- Migration `0017_drop_pipelines_is_default` — drops the legacy boolean. Idempotent (`DROP COLUMN IF EXISTS`). Downgrade re-creates + re-derives from `workspaces.default_pipeline_id`.
- 5-place refactor stopping reads/writes of `is_default`: Pipeline model, PipelineOut schema, repositories.{get_default_pipeline_id, set_default, create_pipeline}, auth.bootstrap_workspace, diff_engine._resolve_stage_id (now reads `pipelines_repo.get_default_pipeline_id`).

Frontend:
- New `components/settings/TeamSection.tsx` — table of users (avatar + role chip + last login) + table of pending invites. Admin sees «Пригласить» CTA → `InviteModal` (email + suggested role, structured 502 retry handling) and inline role `<select>` per row (structured 409 last_admin handling).
- New `lib/hooks/use-users.ts` — `useUsers / useUserInvites / useInviteUser / useChangeUserRole`.
- `lib/types.ts` — Users domain types + `Pipeline.is_default` field removed.
- `/settings/page.tsx` — «Команда» promoted out of «Скоро».

Tests (mock-only, 0 DB / 0 Supabase / 0 network):
- New `tests/test_users_service.py` — 9 tests (invite happy path / idempotent re-invite / aborts on Supabase error / role promote / role demote-last-admin refused / role demote allowed when ≥2 admins / invalid role × 2 / diff_engine reads via FK after drop).
- `tests/test_auth_bootstrap.py:test_first_user_creates_workspace` updated: `"is_default" not in pipelines_created[0]`.
- Combined baseline: **141 mock tests passing** (was 132 → +9).
- `pnpm typecheck` + `pnpm build` clean. `/settings` 7.61 → 9.83 kB (+2.2 kB TeamSection).

#### G2 — Settings «Каналы» (Gmail + SMTP read-only view) ✅ DONE (`871467c`)

Backend (NEW `app/settings/` package):
- `GET /api/settings/channels` (any role) — resolves env config + per-user `ChannelConnection` row into one payload.
- `GmailChannelOut` (configured / connected / last_sync_at) + `SmtpConfigOut` (configured / host / port / from / user — NO password).
- 0 new tables, 0 new migrations.

Frontend:
- New `components/settings/ChannelsSection.tsx` — Gmail card with 3 states (not configured / not connected / connected) + SMTP card with 4-field grid + active/stub-mode chip.
- New `lib/hooks/use-channels.ts` — `useChannelsStatus()` with `refetchOnWindowFocus`.
- `lib/types.ts` — channels types.
- `lib/hooks/use-inbox.ts` — `useConnectGmail` typed with explicit `ApiError` generic.
- `/settings/page.tsx` — «Каналы» replaces former «Интеграции» stub, positioned between «Команда» and «Профиль».

Tests: 0 new (G2 spec: «build only — wires existing endpoints»). Baseline still **141 mock tests passing**. `/settings` 9.83 → **11.6 kB** (+1.8 kB ChannelsSection). 13 routes prerender.

#### G3 ⏸ NEXT — Settings «AI» + «Кастомные поля» backend + UI

Per spec in `04_NEXT_SPRINT.md`:
- `GET / PATCH /api/settings/ai` (admin) — surfaces `workspace.settings_json` daily budget / model selection. NO migration (workspace.settings_json already exists since Sprint 1.1).
- Migration `0018_custom_attributes`: `custom_attribute_definitions` (workspace_id CASCADE, key, label, kind ∈ text/number/date/select, options_json, is_required, position) + `lead_custom_values` (lead_id CASCADE, definition_id CASCADE, value_text/number/date — kind-discriminated).
- New `app/custom_attributes/` package: models, schemas, repositories, services, routers (admin/head gated for writes).
- New frontend sections: `AISection.tsx` (budget card + model selector + spend gauge) + `CustomFieldsSection.tsx` (list + create/edit + plain up/down position buttons — dnd-kit deferred).
- Tests target ~8.

Carryover for G5 polish (NOT G3):
- Stage-replacement preview UX in PipelineEditor («N лидов потеряют стадию»).
- Render custom fields on LeadCard — explicitly out of scope for G3 (Settings CRUD only).

#### G4 ⏸ — Templates module
Migration `0019_message_templates`. New `app/templates/` package. Tests ~6.

#### G5 ⏸ — Polish + sprint close
Audit hooks, notification on invite acceptance, sprint report, brain memory rotation, smoke checklist.

#### Cadence note for next session
- **DO NOT merge to main per group.** User wants a single merge after G5 close. G1 + G2 are pushed to `sprint/2.4-settings-templates` on origin; do NOT fast-forward main.
- Migration 0017 (drop `pipelines.is_default`) is destructive — extra reason to hold the merge.
- launch.json's web preview config was cleared (`b3f865c`) so the preview hook stops auto-firing on UI edits.

### ✅ Sprint 2.5 — Automation Builder (DONE — branch `sprint/2.5-automation-builder`, pending merge)
**4 of 5 gates shipped (G3 AmoCRM skipped by product decision).**

Commit range: `363b371..HEAD` on `sprint/2.5-automation-builder`.

Full sprint report: `docs/SPRINT_2_5_AUTOMATION_BUILDER.md`.

Gates summary:
- **G1** (`363b371`) Automation Builder core — migration 0020, condition evaluator, render, 3 trigger fan-outs, `/automations` page
- **G2** (`a3b48ad`) Notification dedupe (1h window + empty daily_plan_ready skip) + day grouping in drawer
- **G3** SKIPPED — AmoCRM adapter dropped (Bitrix24 covers the lead-import story for ops)
- **G4** (`f32fe89`) Invite accept-flow — `accepted_at` write + `safe_notify(invite_accepted)` to inviter inside the same transaction
- **G5** (this commit) Sprint close — report, brain rotation, smoke checklist additions

New modules in this sprint:
- `apps/api/app/automation_builder/` — distinct from `app/automation/` (the gate engine); user-defined builder rules
- `docs/SPRINT_2_5_AUTOMATION_BUILDER.md`
- `docs/SMOKE_CHECKLIST_2_5.md` (supplement to 2.4 checklist)

Test baseline (mock-only): **301 passing** (281 base + 12 G1 + 5 G2 + 3 G4). 14 pre-existing failures (env-related fastapi import) unchanged.

`pnpm typecheck` clean throughout. 0 new npm deps; 0 new Python deps.

### ✅ Sprint 2.6 — Real outbound email + UX polish (DONE — branch `sprint/2.6-outbound-email`, pending merge)
**4 of 5 gates shipped (G2 multi-step automation chains skipped by product decision). 2 mid-sprint stability commits landed alongside the planned gates.**

Commit range: `b740a76..HEAD` on `sprint/2.6-outbound-email`.

Full sprint report: `docs/SPRINT_2_6_OUTBOUND_EMAIL.md`.

Gates summary:
- **G1** (`b740a76`) Real email dispatch — new `app/email/sender.py` (tri-state True/False/EmailSendError), `_send_template_action` routes by channel
- **STB #1** (`cc8db53`) Stability audit fixes — SMTP-after-commit (new `app/automation_builder/dispatch.py` post-commit queue), per-automation SAVEPOINT, whitespace email strip
- **STB #2** (`323aa85`) Stability audit fixes — `TemplateInUse` 409 guard on delete, N+1 bulk-fetch in followups dispatcher
- **G3** (`6f19d4d`) Pipeline + LeadCard polish — accent +Лид, outline Sprint, Settings «Скоро» disclosure, LostModal, mobile pipeline polish
- **G4** (`df7bfc2`) Custom fields inline editing on LeadCard + dnd-kit reorder in Settings
- **G2** SKIPPED — Multi-step automation chains (product decision; back to long-tail)
- **G5** (this commit) Sprint close — report, brain rotation, smoke checklist additions

New modules in this sprint:
- `apps/api/app/email/sender.py` — tri-state SMTP wrapper for the Automation Builder
- `apps/api/app/automation_builder/dispatch.py` — post-commit email dispatch queue (contextvar-scoped)
- `apps/web/components/lead-card/LostModal.tsx` — replaces window.confirm/prompt
- `apps/web/components/lead-card/CustomFieldsPanel.tsx` — inline-edit custom fields on LeadCard
- `apps/web/lib/hooks/use-lead-attributes.ts`
- `docs/SPRINT_2_6_OUTBOUND_EMAIL.md` + `docs/SMOKE_CHECKLIST_2_6.md`

No new migrations this sprint — pure code on the existing schema.

Test baseline (mock-only): **112 passing** (108 → +4 G4 = 112; full sprint trajectory 95 → 99 → 100 → 108 → 112). 14 pre-existing fastapi-import failures unchanged.

`pnpm typecheck` clean throughout. 0 new npm deps; 0 new Python deps.

Stability audit summary: 0 CRITICAL remain, 2 of 4 HIGH fixed (template delete 409 + followups N+1). The remaining 2 HIGH (cron swallow, BackgroundTasks-strands-running) both depend on Sentry activation in Sprint 2.7 G1.

### ✅ Sprint 2.7 — Sentry activation + multi-step automations (DONE — branch `sprint/2.7-sentry-multistep`, PR [#12](https://github.com/GlobalSasha/crm/pull/12), pending merge)
**3 of 5 planned gates shipped (G1 + G2 + G5); G3 + G4 deferred to long-tail by product decision.**

Commit range: 3 commits on the branch (`65c5bef..HEAD`).

Full sprint report: `docs/SPRINT_2_7_SENTRY_MULTISTEP.md`.

Gates summary:
- **Sprint 3.1 spec save** (`65c5bef`) — `docs/SPRINT_3_1_LEAD_AI_AGENT.md` saved verbatim from the user's message so a future session can read it as authoritative spec. Includes a fix-up note that the original migration index 0013 is taken; actual index will be 0022+ once Sprint 2.7 lands.
- **G1** (`1c4283d`) Sentry activation — backend swallow obёртки + frontend error boundaries + 8 tests
- **G2** (`03bf762`) Multi-step automation chains — Migration 0021 (additive `steps_json` JSONB column + `automation_step_runs` table) + handler refactor + Celery beat scheduler + 13 tests
- **G3** SKIPPED — tg outbound dispatch (long-tail; templates with `channel='tg'` continue to stage `delivery_status='pending'` Activity rows)
- **G4** SKIPPED — Enrichment → Celery + WebSocket (strand-on-failure already closed by G1; real-time UI defers to manager-demand)
- **G5** (this commit) Sprint close — report, smoke checklist, brain rotation

New modules in this sprint:
- `apps/api/app/common/sentry_capture.py` — single capture chokepoint with lazy import + soft no-op
- `apps/api/app/observability.py` — `init_sentry_if_dsn(settings)` extracted from main.py:lifespan for testability
- `apps/api/app/automation_builder/...` — extended with `_dispatch_step`, `_compute_schedule_offsets`, `_resolved_chain`, `_validate_steps`, `execute_due_step_runs`, `list_step_runs_for_run`
- `apps/web/lib/sentry-capture.ts` — runtime captureClientException helper
- `apps/web/app/global-error.tsx` + `apps/web/app/(app)/error.tsx` — React error boundaries
- `apps/api/alembic/versions/20260510_0021_automation_steps.py` — additive multi-step migration
- `docs/SPRINT_2_7_SENTRY_MULTISTEP.md` + `docs/SMOKE_CHECKLIST_2_7.md`

Migration delta: 0021 (additive `automations.steps_json JSONB NULL` + new `automation_step_runs` table with partial index `(scheduled_at) WHERE executed_at IS NULL`).

Beat schedule delta: new entry `automation-step-scheduler` every 5 min.

Test baseline (mock-only): **133 passing** (was 112; +8 G1 + +13 G2). 14 pre-existing fastapi-import failures unchanged. `pnpm typecheck` clean.

Net-new dependencies: **0** in this PR. `sentry-sdk[fastapi]` was pre-pinned since 2.1 G10. `@sentry/nextjs` install is an operator step (see «Operator follow-on» below).

ADR work: none new — Sprint 2.7 was implementation-shaped on top of existing patterns (ADR-009 package-per-domain, ADR-018 LLM provider abstraction, ADR-019 email lead-scoping).

Operator follow-on (3 items, none blocking the merge):
1. `cd /opt/drinkx-crm/apps/web && pnpm add @sentry/nextjs` — flips `lib/sentry.ts` from warn-once to live (~50KB minified bundle)
2. Set `SENTRY_DSN` (backend) + `NEXT_PUBLIC_SENTRY_DSN` (frontend) in `/opt/drinkx-crm/infra/production/.env`; redeploy via `deploy.sh`
3. Configure Sentry-side rate limits before noisy crons burn the 5k/month free tier

### ⏸ NOT YET BUILT (after Sprint 2.7)
- **Sprint 3.1 — Lead AI Agent** — see `docs/SPRINT_3_1_LEAD_AI_AGENT.md`. Background mode (Celery task watching for paused conversations + sales-methodology gaps → banner-recommendation) + Foreground mode (Sales Coach chat drawer with full lead context). Phase A blocks on user providing the artifact files (`lead-ai-agent-skill.md` + `product-foundation.md`).
- **Sprint 2.8 long-tail** — Sprint 2.7 G3 + G4 carryovers (tg outbound, Enrichment Celery+WS); multi-clause condition UI; AmoCRM adapter; Telegram Business inbox + email send (gmail.send scope); Quote/КП builder; Knowledge Base CRUD UI; multi-step automation polish (dnd-kit reorder, pause-mid-chain UI, per-step retry).
- **Phase 3** — Multi-tenancy (invite-flow + per-tenant routing for second client), MCP server, OCR визиток, pgvector

---

## Production blockers resolved during Sprint 1.4

Four hotfixes had to land **on top of** the Sprint 1.4 merge before everything was actually live. Documented in `SPRINT_1_4_DAILY_PLAN.md` for posterity:

1. `4dd4b7d` — Node 22 in `apps/web/Dockerfile` (pnpm 11 dropped Node 20)
2. `b720f5d` — `packageManager: pnpm@10.18.0` + `onlyBuiltDependencies` (corepack reproducibility + build-script allow-list)
3. `e5b8fe9` — Side-effect model imports in `app/scheduled/celery_app.py` (worker process doesn't import `app.main`, mapper registry was incomplete)
4. `8d2e644` — Per-task NullPool engine in Celery jobs (each `asyncio.run()` creates a new event loop; reusing the global asyncpg pool across loops crashed with "Future attached to a different loop")

---

## Open dependencies / production env state

User-provided keys in `/opt/drinkx-crm/infra/production/.env`:
- ✅ `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_JWT_SECRET`
- ✅ Google OAuth provider configured in Supabase
- ✅ `MIMO_API_KEY` (primary)
- ✅ `ANTHROPIC_API_KEY` (fallback — note: 403 from RU IP, never fires in practice)
- ✅ `BRAVE_API_KEY`
- ⚠ `GEMINI_API_KEY` — not configured
- ⚠ `DEEPSEEK_API_KEY` — not configured (intentional)
- ⏸ Sentry DSNs — empty in production env. Sprint 2.7 G1 wired the init path (`app/observability.py:init_sentry_if_dsn` + `app/common/sentry_capture.py` + 4 cron-swallow obёртки + `_bg_run` failure capture); when the operator sets `SENTRY_DSN` + `NEXT_PUBLIC_SENTRY_DSN` and runs `pnpm add @sentry/nextjs`, telemetry activates without a code change. Until then, structlog + journalctl + ScheduledJob audit table remain the visibility layer.

---

## Known issues / risks

1. **Anthropic always 403 from RU IP** — fallback chain wastes one round-trip before falling through to Gemini/DeepSeek. Documented since Sprint 1.3.
2. **DST edge cases** — `daily_plan_generator` and `daily_email_digest` both match `local hour == 8`. On DST days an hour skips or duplicates. Acceptable.
3. **No retry on per-user LLM failure** in the daily plan cron — that user gets no plan today, error is logged.
4. **`fit_score` last-writer-wins** — orchestrator and the manual scoring tab both write the column. No conflict resolution. Documented since Sprint 1.3.
5. **Tab content overflow on mobile, not exhaustively audited** (Sprint 1.5 group 6) — DealTab / ScoringTab / AIBriefTab / etc. weren't reviewed for hard-coded grids or wide tables at 375px. Point-fix with `overflow-x-auto` on observation.
6. **TransferModal UUID input** (Sprint 1.5 group 7) — no `/api/users` listing endpoint yet, so the manager pastes the recipient's UUID. Backend validates membership and surfaces 400 inline. Replace with a picker once the endpoint lands.
7. **Email digest stub mode not yet verified in production** (Sprint 1.5 group 5) — `SMTP_HOST=""` keeps the digest in stub mode (`[EMAIL STUB]` lines in worker logs). Smoke-test on the morning after deploy.
8. **Soft-launch checklist partially open** — see `SPRINT_1_5_POLISH_LAUNCH.md` for the row-by-row state. Sentry DSNs, pg_dump backups, onboarding doc, end-to-end smoke, and log-volume review are all still ⏸.

### Post-2026-05-08 hotfix tech debt (folding into Sprint 2.4)

9. **No post-deploy smoke checklist ritual.** /leads-pool tihо
   ломалось >24h из-за `page_size=500` mismatch (frontend change
   `480d0a9` 2026-05-07 → backend hotfix `8349516` 2026-05-08).
   Каждый sprint close должен включать визит на каждую главную
   страницу (/today, /pipeline, /leads-pool, /inbox, /forms,
   /settings) после деплоя и подтверждение отсутствия 4xx/5xx в
   Network tab. Добавлено в Sprint 2.4 plan.
10. **Multi-tenancy assumption baked in.** `bootstrap_workspace`
    SELECTs the OLDEST workspace as the canonical one. If DrinkX
    sells the codebase to a second client, their first user
    silently joins workspace #1 — wrong tenant. Phase 3 surface:
    invite-flow + per-tenant routing or per-tenant DB. See
    `02_ROADMAP.md` Phase 3 entry.
11. **Drop legacy `pipelines.is_default` boolean.** Sprint 2.3 G1
    moved «which is the default» onto `workspaces.default_pipeline_id`
    FK, but kept `is_default` for diff_engine + back-compat. Drop
    via migration in Sprint 2.4 G1 housekeeping; `diff_engine.py`
    needs a one-line read swap to use `repositories.get_default_pipeline_id`
    instead.
12. **Stage-replacement preview missing** in `PipelineEditor`. When
    the manager removes/renames stages, leads on those stages drop
    to `stage_id=NULL` (FK SET NULL). The UI does NOT surface «N
    лидов потеряют стадию» before save. Sprint 2.4 polish.

Resolved this sprint:
- ~~Stuck `DailyPlan` row from the asyncpg loop bug~~ — flipped to `failed` mid-sprint via the production debugging session; `regenerate_for_user` end-to-end confirmed working (24 items, 27s).

---

## Next
**Sprint 3.1 — Lead AI Agent** is the next product-shaped slice.
Spec lives in `docs/SPRINT_3_1_LEAD_AI_AGENT.md` (saved during
Sprint 2.7 G5 close). Branch `sprint/3.1-lead-ai-agent` to be cut
from main after Sprint 2.7 PR #12 lands.

**Phase A is blocked on the user** — the spec references two
artifact files (`docs/skills/lead-ai-agent-skill.md` and
`docs/knowledge/agent/product-foundation.md`) that haven't been
provided yet. The next Claude session for Sprint 3.1 should
ask for them before starting Phase A.

Carryovers from 2.7 deferred to Sprint 2.8+:
- tg channel outbound dispatch (G3 carryover — Telegram Bot API + `lead.tg_chat_id` migration)
- Enrichment → Celery + WebSocket (G4 carryover — when manager-facing real-time progress becomes a priority)
- Multi-step automation polish: dnd-kit reorder in builder, pause-mid-chain UI, per-step retry on failure

Active migrations on `sprint/2.7-sentry-multistep`: `0001..0021` (added 0021_automation_steps in G2). Next free index for Sprint 3.1: `0022`.
