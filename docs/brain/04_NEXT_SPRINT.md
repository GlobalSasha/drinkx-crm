# Next Sprint: Phase 2 Sprint 2.4 — Full Settings panel + Templates

Status: **READY TO START** (after Sprint 2.3 merge / deploy / smoke check)
Branch: `sprint/2.4-settings-templates` (create from main once 2.3 lands)

## Goal

Sprint 2.3 shipped `/settings` with one live section («Воронки») and
five «Скоро» stubs. Sprint 2.4 fills out the rest of the panel into a
real admin-control surface — and adds a **Templates module** that the
upcoming Automation Builder (Sprint 2.5) will consume to render
outbound messages without reinventing the wheel.

Scope is two parallel tracks: **Settings completion** (4 sections) and
**Templates** (new domain). Both share the admin/head-only gate the
existing Settings UI already enforces. No new domains beyond
Templates, no new vendors, no new AI capability.

## Read before starting

- `docs/brain/00_CURRENT_STATE.md` — what Sprint 2.3 left
- `docs/brain/02_ROADMAP.md` — Phase 2 envelope
- `docs/brain/sprint_reports/SPRINT_2_3_MULTI_PIPELINE.md` — known
  issues + carryover (notification debounce, sentry@nextjs,
  drop-is_default housekeeping, stage-replacement preview)
- `docs/PRD-v2.0.md` §9 (Settings) + §10 (Templates / Automation)
- Existing surfaces to extend, not replace:
  - `app/auth/*` — User / role model already in place
  - `app/inbox/oauth.py` — Gmail OAuth flow already shipped (Sprint 2.0); «Каналы» section just exposes it from Settings
  - `app/notifications/email_sender.py` — SMTP scaffolding from Sprint 1.5; «Каналы» surfaces config
  - `app/enrichment/budget.py` — daily budget cap from Sprint 1.3; «AI» section surfaces it
- Production state at sprint start: 4 app containers + 4 cron entries running, manager workflows for Pipeline / Inbox / Import / Export / Forms / Pipelines all live, Sprints 2.1 + 2.2 + 2.3 merged

## Scope

### ALLOWED

#### G1 — Settings «Команда» backend + UI (~1 day)

Backend:
- `GET /api/users` — list workspace users (id, email, name, role,
  last_login_at). All roles read; admin/head only for the email
  invite path below.
- `POST /api/users/invite` — admin-only. Body `{email, role}`.
  Sends a sign-in magic-link via Supabase admin API; the new user
  becomes a workspace member on first sign-in (existing auth
  bootstrap path handles it). Track invitations in a new
  `user_invites` table for the admin UI.
- `PATCH /api/users/{id}/role` — admin-only. Validates the role is
  one of `('admin', 'head', 'manager')`. Refuses to demote the
  last admin (defensive — every workspace MUST have at least one
  admin).
- Migration `0016_user_invites` (or fold into user table — TBD;
  migration shape decided in G1 plan review). NOTE: 0014 and 0015
  were taken by post-Sprint-2.3 hotfixes (0014_bootstrap_orphan_workspaces,
  0015_merge_workspaces).
- Migration `0017_drop_pipelines_is_default` — housekeeping
  carryover from Sprint 2.3. Drop the legacy `pipelines.is_default`
  boolean. Prep step: in `app/import_export/diff_engine.py` swap
  the one `Pipeline.is_default.is_(True)` read for
  `pipelines_repo.get_default_pipeline_id(...)`. Then the column
  is no longer read anywhere and the migration just drops it.

Frontend:
- New `app/web/components/settings/TeamSection.tsx` — table of
  users (Avatar, Name, Email, Role chip, Last login, Actions).
- Invite modal: email + role dropdown.
- Role-edit inline dropdown (gated by useMe().role === 'admin').
- Confirm-modal for «demote last admin» refusal carries the same
  structured-409 pattern as 2.3's pipeline delete.

Tests (mock-only target ~7):
- invite generates magic-link (mocked Supabase admin client)
- invite refused for non-admin
- role-change refused if it would leave zero admins
- list scoped to workspace
- diff_engine still resolves the default pipeline via the new
  reader after the is_default drop

#### G2 — Settings «Каналы» UI (~0.5 day)

No new backend. Reuse existing surface:
- Gmail: `GET /api/inbox/oauth/url` + `/oauth/callback` (Sprint 2.0)
- SMTP: `email_sender.py` reads from settings already

Frontend:
- New `app/web/components/settings/ChannelsSection.tsx`:
  - Gmail card: connection state (connected / disconnected / error),
    «Подключить» CTA pointing at `/inbox/oauth/url`.
  - SMTP card: read-only display of `SMTP_HOST` / `SMTP_PORT` /
    `SMTP_FROM` from a new `GET /api/settings/channels` admin
    endpoint that returns the resolved server config. Editing
    SMTP is intentionally left to env vars in v1 — no DB-backed
    SMTP config means we don't have to ship a credentials-at-rest
    story for this sprint (carryover from the Sprint 2.0 Fernet
    work).
- Tests: 0 (build only — wires existing endpoints).

#### G3 — Settings «AI» + «Кастомные поля» backend + UI (~1 day)

AI section — surfaces existing config:
- `GET /api/settings/ai` (admin) returns daily budget cap,
  selected model, current spend.
- `PATCH /api/settings/ai` (admin) flips model selection +
  budget cap. Reads from `workspace.settings_json` (already
  exists since Sprint 1.1) — no migration.
- New `app/web/components/settings/AISection.tsx` with budget
  card + model selector + spend gauge.

Custom fields — new EAV-shaped surface:
- Migration `0018_custom_attributes`:
  - `custom_attribute_definitions` (workspace_id CASCADE, key,
    label, kind ∈ ('text','number','date','select'), options_json,
    is_required, position, created_at)
  - `lead_custom_values` (lead_id CASCADE, definition_id CASCADE,
    value_text / value_number / value_date — one populated per
    row depending on kind)
- `app/custom_attributes/` package: models, schemas (CreateIn,
  UpdateIn, Out), repositories, services, routers
  (`/api/custom-attributes/*` admin/head gated for writes).
- New `app/web/components/settings/CustomFieldsSection.tsx` —
  list + create + edit + drag-reorder.
- LeadCard integration deferred to a follow-on (G3 only ships the
  Settings CRUD; rendering the custom fields on the lead detail
  is a 2.4+ polish item).

Tests (~8 mock-only):
- definition create / list / update / delete
- value upsert per kind
- role gating

#### G4 — Templates module (~1 day)

Backend:
- Migration `0019_message_templates`:
  - `message_templates` (workspace_id CASCADE, channel ∈
    ('email', 'tg', 'sms'), name, subject, body, variables_json,
    is_active, created_by SET NULL, created_at, updated_at)
- `app/templates/` package: models, schemas, repositories,
  services, routers (`/api/templates/*` admin/head gated for
  writes).
- Variable substitution helper (`render_template(template, ctx)`)
  — string-replace `{{lead.company_name}}` style placeholders.
  Documented but not yet consumed (Automation Builder lands in
  2.5).

Frontend:
- New `/settings/templates` sub-route OR a new section in
  `/settings` (TBD G4 plan review — sub-route reads more
  natural for a list+detail surface).
- Template list table + editor modal with channel selector +
  subject + body textarea + a static «Доступные переменные»
  reference panel.

Tests (~6 mock-only):
- create / update / delete with workspace scope
- variables_json validation
- rendering with missing variable falls back gracefully

#### G5 — Polish + sprint close (~0.5 day)

- Audit log emit hooks for `user.invite / user.role_change /
  template.create / template.delete / custom_attribute.*`.
- Notifications — invitation acceptance pings the inviter
  («{name} принял приглашение в воронку»).
- AppShell: nothing new (the «Настройки» entry covers everything;
  Templates land as a sub-section).
- Sprint report `SPRINT_2_4_SETTINGS_TEMPLATES.md`.
- Brain memory rotation: 00 + 02 + 04 updates as usual.

### NOT ALLOWED (out of scope)

- **Automation Builder.** Templates are the data model + admin UI
  only. Wiring templates into actual outbound flows is Sprint 2.5.
- **Workspace-level RBAC beyond admin/head/manager.** «Custom
  permissions» is a 3.x concept.
- **DB-backed SMTP credentials.** Env-var reads only in v1 — see
  G2 rationale.
- **Drag-reorder in Custom Fields v1.** Position is editable but
  the UI is plain up/down buttons; dnd-kit can land in a follow-on.
- **Cross-workspace template sharing.** «Marketplace» is Phase 3.

## Risks

1. **Magic-link invite delivery in stub mode.** SMTP host is
   empty in production today (Sprint 1.5 stub mode). Invites
   should still produce a clickable URL in the worker logs (same
   pattern as the daily digest stub). G1 should NOT block on
   real SMTP — verify the URL is logged and the user copies it
   manually until staging gets real SMTP creds.
2. **Custom-field render on /pipeline + LeadCard.** Defining
   custom fields without a place to display them is a footgun.
   Carryover to a 2.4+ polish ticket — at minimum, the LeadCard
   should grow a «Дополнительные поля» tab in 2.4 after G3.
3. **Template variable schema drift.** Hardcoding the lead-shape
   into the variables reference panel risks falling out of sync
   if Lead grows new columns. G4 should derive the reference
   list from a single source of truth (e.g.
   `app/leads/schemas.py:LeadOut.model_fields`).
4. **2.3 carryover bundling.** Drop-`is_default` migration is now
   wired into G1 (migration 0017). Stage-replacement preview UX
   stays a small isolated PR within G5 — keep the new work clean,
   don't smear it across other groups.
5. **Settings page surface area.** Three new backend endpoints
   for «AI» + «Кастомные поля» + «Команда» + «Templates». Add
   them to the existing routers list in `app/main.py` carefully;
   the route count will jump and `pnpm build` time will too.

## Stop conditions — post-deploy smoke checklist

**Before declaring Sprint 2.4 complete, run this ritual on
staging (and again on prod after merge to main).** Lesson from
2026-05-08: `/leads-pool` was silently broken for >24h because
nobody hit the page after a frontend `page_size` bump. We don't
catch latent 4xx without explicit verification.

For each of the live pages, open it logged-in, watch the Network
tab Fetch/XHR rows, and confirm zero non-2xx responses:

- [ ] `/today` — daily plan loads, no 422/500 on `/api/me/today`
      or `/api/leads`.
- [ ] `/pipeline` — switcher dropdown renders, board reflows,
      `/api/pipelines` 200, `/api/leads?pipeline_id=...` 200.
- [ ] `/leads-pool` — pool table renders OR empty state shows;
      `/api/leads/pool?page_size=500` 200 (NOT 422 — see hotfix
      `8349516`).
- [ ] `/inbox` — pending list renders (or empty-state OAuth CTA).
- [ ] `/forms` — admin/head only, table loads, embed snippet
      copies (Sprint 2.2).
- [ ] `/settings` — all 4 sections render, «Воронки» table opens,
      switch + delete + create flows работают.
- [ ] `/audit` — admin only, recent events visible.

If any row 4xx/5xx, sprint is NOT complete — fix before close.
The smoke checklist gets a row in `SPRINT_2_4_*.md`'s production-
readiness section and again as a pre-PR-merge gate.

Same pattern carries forward to Sprint 2.5+. Add new pages to the
list as they ship.

## Done definition

- Migrations 0016 (user_invites), 0017 (drop pipelines.is_default),
  0018 (custom_attributes), 0019 (message_templates) apply cleanly
  via `alembic upgrade head` on staging.
- All 4 Settings sections live: Команда / Каналы / AI /
  Кастомные поля.
- Templates module live at `/settings/templates` (or sub-route
  TBD).
- Audit log shows the new emit kinds.
- ≥20 new mock tests across G1 / G3 / G4. Combined baseline
  ≥149 mock tests passing.
- `pnpm typecheck` + `pnpm build` clean.
- Sprint report written, brain memory rotated.
- 0 new npm deps target (matches Sprints 2.0 / 2.1 / 2.2 / 2.3).

---

**Out-of-scope but parked here for awareness — fold into 2.5+:**

- Automation Builder (consumes Templates from 2.4)
- AmoCRM adapter (Sprint 2.1 G5 deferred)
- Telegram Business inbox + `gmail.send` scope (Sprint 2.0 deferred)
- Quote / КП builder (Sprint 2.0 deferred)
- Knowledge Base CRUD UI (Sprint 2.0 deferred)
- `_GENERIC_DOMAINS` per-workspace setting (Sprint 2.0 carryover)
- Gmail history-sync resumable / paginated job (Sprint 2.0 carryover)
- Notification debounce on form-submission fan-out (Sprint 2.2 carryover)
- Honeypot / timing trap on `embed.js` (Sprint 2.2 carryover)
- `pnpm add @sentry/nextjs` activation (Sprint 2.1 G10 carryover)
- pg_dump cron + Sentry DSNs (Sprint 1.5 soft-launch carryover)
- Per-stage gate-criteria editor (Phase 3)
- Pipeline cloning / templates (Sprint 2.3 carryover)
- Cross-pipeline reporting (Phase 3)
- DST-aware cron edge handling
- Custom-field render on LeadCard (Sprint 2.4 polish carryover; G3
  ships Settings CRUD only)
