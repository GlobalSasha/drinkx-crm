# Next Sprint — CEO Overview (role-based /today) + extensible lead sources

**Status:** 🟢 ACTIVE — start at **Sprint CEO** below (the Odoo-reuse sprint G1–G5 is DONE,
kept below as record). **Alembic head `0056`. Next free index `0057`.**
**Prev:** Odoo-reuse arc — 8 PRs (#102–#109) shipped. Full record in `00_CURRENT_STATE.md`
(section «Odoo-reuse arc + test CI (2026-06-04)»). Sprint 3.5 (Production Polish v2)
and Website Leads Intake are done; their record is in git history + `00_CURRENT_STATE.md`.

---

## Ad hoc — модель сделки «Продажа / Аренда»

- [x] Добавить `leads.commercial_model` (`sale` / `rental`, nullable для старых лидов)
      миграцией `0056`; сохранить прежний `deal_type` как отдельную классификацию.
- [x] В карточке лида добавить «Модель сделки» и менять смысл подписи `deal_amount`:
      полная сумма продажи либо аренда в месяц.
- [x] Добавить API-валидацию и тест сохранения модели вместе с суммой.

---

## Ad hoc — доступ в CRM только по приглашению

- [x] Сохранить вход всем существующим пользователям, но запретить создание нового
      пользователя без ожидающего приглашения на ту же почту.
- [x] Применять выбранную в приглашении роль; повторное приглашение снова открывает
      доступ ранее удалённому сотруднику.
- [x] До загрузки CRM проверять доступ через `/auth/me`; при отказе завершать сессию
      и показывать понятное сообщение на странице входа.
- [x] Запретить публичной форме magic link автоматически создавать аккаунты.

---

## Sprint CEO — обзорный /today для руководителя + расширяемые источники лидов

**Why:** руководителю (`role` = `head`/`admin`) нужен НЕ операционный «мой день», а сводка
по **входящему потоку заявок**: сколько лидов, откуда, конверсия с рекламы, по дням, у кого
в работе, что висит без движения. Сделки идут редко и долго — выручку/forecast наверх НЕ тащим.
Концепт утверждён на моках (см. сессию 2026-06-29). Решения: **плоский список источников**,
порог «без движения» = **7 дней** без касания, «конверсия с рекламы» = заявка → **квалификация**
(лид вышел из первой/intake-стадии), считаем по источникам с `is_paid=true`.

**Build foundation first (источники), then the dashboard** — дашборд группирует по `source_id`.

### CEO-G1 — Справочник источников `LeadSource` (backend) ⭐ фундамент
Сейчас `lead.source` — свободный текст (`String(60)`, [leads/models.py:98]) и в форме не
заполняется. Делаем настраиваемый справочник по образцу Pipeline/Stage + каталога.
- [x] Новый пакет-домен `app/lead_sources/` (models/schemas/repositories/services/routers),
      по образцу `app/utm/`. Модель `LeadSource`: `id`, `workspace_id` (FK + unique
      `(workspace_id, name)`), `name`, `is_active`, `is_paid`, `is_system`, `sort_order`,
      timestamps. `DEFAULT_LEAD_SOURCES` в models.py.
- [x] Миграция `0051_lead_sources`: создать `lead_sources` + `leads.source_id` (nullable FK →
      SET NULL, index) + сид дефолтов для всех существующих воркспейсов (INSERT…SELECT,
      ON CONFLICT DO NOTHING). Старый текстовый `leads.source` не трогаем.
- [x] Seed-дефолты при bootstrap воркспейса (`app/auth/services.py`, рядом с `DEFAULT_STAGES`):
      Яндекс Директ (paid+system), Сайт (system), Выставка, Холодный обзвон, Реферал.
- [x] CRUD `/api/lead-sources`: GET list (`?active_only` для формы, любой авторизованный),
      POST/PATCH/DELETE под `require_admin_or_head`; DELETE → 409 при `is_system`.
- [x] DB-backed тест `tests/test_lead_sources.py`: seed-идемпотентность, create+unique-конфликт,
      list active_only, delete system→409 / custom→ok. Локально нет PG → скип; пойдут в CI.

### CEO-G2 — Источник в форме лида (full-stack)
- [x] `LeadCreate`/`LeadUpdate` принимают `source_id` (Optional); persist в `leads.source_id`
      (через `model_dump` — доп. кода в сервисе не нужно). `LeadOut.source_id` тоже отдаётся.
- [x] `CreateLeadModal` — поле «Откуда появился лид»: дропдаун из `GET /lead-sources?active_only=true`
      (хук `use-lead-sources.ts`), проброс `source_id` в create. Необязательное.
- [x] Pre-PR (frontend): `npm run typecheck` ✓ + `npm run lint` (0 errors) ✓ + `pnpm build` ✓.

### CEO-G3 — Settings → «Источники лидов» (frontend)
- [x] Раздел `LeadSourcesSection` в `/settings` (icon Megaphone) по образцу `CatalogSection`:
      список (вкл. неактивные), add/rename/toggle active/paid, delete. Gated `role in (admin, head)`.
      `is_system` → бейдж «системный» без кнопки удаления.

### CEO-G4 — Агрегаты для дашборда (backend)
- [x] Новый домен `app/company/` (schemas/repositories/services/routers).
      `GET /api/company/summary?period=week|month` → пульс (сегодня/вчера/7д/средн.в день),
      `stuck_count` (open assigned, non-terminal, `COALESCE(last_activity_at,created_at)` >7д),
      конверсия с рекламы (paid: stage.position>0 ÷ всего за период), `sources[]` (count+conversion),
      `daily[]` за 14 дн. по `source_id`. «Квалификация» = вышел из intake (position 0).
- [x] `GET /api/company/attention` → `stuck[]` (top-30: компания, источник, менеджер, days_idle) +
      `managers[]` (в работе / новых за неделю / зависших), всё raw-SQL по образцу `team/*`.
- [x] Оба под `require_admin_or_head`. DB-тест `tests/test_company.py` (2 теста; скип без PG, в CI).

### CEO-G5 — Обзорный /today по роли (frontend) ⭐ цель
- [x] `/today` → `TodayRouter` по `useMe().role`: head/admin видят `<CeoOverview />`, менеджеры —
      прежний `<TodayPageInner />`. Один роут, разветвление по роли.
- [x] `CeoOverview` ([components/today/CeoOverview.tsx]) по утверждённому макету: тумблер неделя/месяц ·
      пульс (4 числа) · заявки по дням (стек по источникам, recharts) · откуда пришли + конверсия ·
      по менеджерам (клик → /team/[id]) · без движения (клик → /leads/[id]). Хук `use-company.ts`.
- [x] Pre-PR (frontend): `npm run typecheck` ✓ + `npm run lint` (0 errors) ✓ + `pnpm build` ✓.

> Отложено (НЕ в этом спринте): AI-дайджест дня, воронка лид→КП→сделка, прогресс к плану/квоте
> (модель `Quota` есть, но без эндпоинтов), разбивка внутри источника, workspace-wide лента
> событий. Плейсхолдеры под AI-дайджест/план можно оставить в макете.

---

## Record — Odoo-reuse sprint (G1–G5, DONE)

---

## Context — read before touching code

- **Backend already shipped (in prod):** phone E.164 normalization; lead duplicate
  **detection** (`GET /leads/{id}/duplicates`) + **merge** (`POST /leads/{id}/merge`,
  soft/reversible via `leads.merged_into_id`); UTM dictionaries auto-resolved on form
  submit (`leads.utm_source_id/medium_id/campaign_id`). New code lives in
  `app/common/phone.py`, `app/common/email.py`, `app/leads/dedup.py`, `app/utm/`.
- **Alembic head `0045`. Next free index `0046`.**
- **Test CI now exists** — `.github/workflows/test.yml` (postgres:16). Every PR touching
  `apps/api/**` runs pytest. Write DB-backed integration tests with the `db` / `workspace`
  fixtures + `@skip_no_pg` (see `tests/test_utm.py`, `tests/test_lead_merge.py` for the
  pattern). Push → watch the «Tests (api)» check green before merging.
- **Merge to `main` auto-deploys to prod.** Always: branch → PR → CI green → merge.

---

## Scope (gated — pick top-down)

### G1 — Dedup merge UI  ⭐ highest value
The merge backend is live but unreachable from the app. Build the human-in-the-loop UI.
- [x] On LeadCard, a «Найти дубли» action → `GET /leads/{id}/duplicates` → list candidates
      (company, email domain, phone, city). Empty → nothing shown.
- [x] «Объединить» → confirmation modal: the current lead is the master; user picks which
      duplicates → `POST /leads/{id}/merge {duplicate_ids}` → toast + refresh.
      **Never auto-merge** (anti-pattern #4 — human confirms).
- [x] On a lead that absorbed dups, show a «← объединён из N» note (read it from the
      `system` audit Activity the merge writes).
- Frontend only (backend done). Pre-PR: `npm run typecheck` + `npm run lint` + `pnpm build`.

### G2 — UTM channel analytics
UTM dims now land on leads. Surface «какой канал приносит сделки».
- [x] `GET /api/leads/utm-stats` (or under `/forms`) — GROUP BY source → `{leads, won, sum}`.
      DB-backed test.
- [x] A «Каналы привлечения» table card on `/forecast` (or `/forms`).

### G3 — Backfill normalized columns
Existing rows have NULL `phone_e164` / `email_normalized` / `email_domain_criterion`
(they fill only on next save). UTM ids likewise only on new form leads.
- [x] One-off Celery task (or `scripts/…`) iterating leads + contacts, re-deriving the keys
      via `app.common.phone.to_e164` + `app.common.email.normalize_email/email_domain_criterion`.
      Idempotent; batch-commit. DB-backed test on a few rows.
      Done: `app/common/backfill.py` core + `app.scheduled.jobs.backfill_normalized_keys`
      manual-trigger task + 4 DB-backed tests. UTM-id backfill left out of scope (needs the
      form_submissions.utm_json join — separate follow-up if wanted).

### G4 — UI consistency fixes 3–5 (from the UI plan)
- [x] One shared empty-state component used everywhere (replace ad-hoc divs e.g. `/team`).
      Done: `/team` access-denied + no-members states now use the shared `Empty`.
- [x] Lint rule banning arbitrary Tailwind sizes (`text-[28px]`, `border-[1.5px]`) — use the scale.
      Done: local `drinkx/no-arbitrary-px` at **warn** level (flags new ones, doesn't break the
      build). The ~235 pre-existing usages are deliberately left untouched — see BACKLOG #3.
- [~] Break the 617-line `LeadCard` header + the `leads/[id]` / `companies/[id]` detail pages
      into reusable sections and wrap them in `PageContainer` — **deferred to BACKLOG #3**.
      These are bespoke full-bleed layouts (own sticky header); wrapping/splitting risks visual
      regressions on the most-used screen with no E2E. Do it as its own PR with preview checks.

### G5 — Finish the 2 quarantined tests  (needs a local Postgres)
In `apps/api/tests/conftest.py` → `_KNOWN_PRE_EXISTING_FAILURES`:
- [x] `test_inbox_matcher::test_processor_creates_activity_on_high_confidence_match` — the
      attach_to_lead path fans out to Automation Builder + Celery (imported in-function in
      `app/inbox/processor.py`); the broad `try/except` swallows the failure. Mock the
      collaborators (`safe_evaluate_trigger`, `collect_pending_email_dispatches`,
      `lead_agent_refresh_suggestion`) so the path returns True, then remove the quarantine entry.
- [x] `base_update/test_e2e::test_e2e_extract_match_apply` — root cause was NOT a moved flow:
      the shared `pipeline` fixture is stale (Sprint 2.4 made the default pipeline a
      workspace FK + first stage `position == 0`). Without that, `get_default_first_stage`
      returns None and `apply_record` bails to ACTION_CONFLICT before creating the lead. Fixed
      in-test (set `workspace.default_pipeline_id` + `stage.position = 0`); un-quarantined.
- Run locally: `cd apps/api && TEST_DATABASE_URL=postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test uv run pytest`
  (needs a local Postgres — Docker `infra/docker/docker-compose.yml` or a `drinkx_test` DB).

---

## Pre-PR gates (per CLAUDE.md)

- **Frontend:** `npm run typecheck` + `npm run lint` + `pnpm build` (Next.js 15 build-time
  checks only fire during `next build`).
- **Backend:** `python -m py_compile` touched modules + `uv run alembic heads` (must be a
  single head) + push → watch the «Tests (api)» CI check go green.

## Stop-rules / anti-patterns
- Never auto-merge duplicates — human confirms (anti-pattern #4).
- Don't add entries to the xfail quarantine — fix the test instead.
- One PR per logical change; remember merge-to-`main` = prod deploy.
