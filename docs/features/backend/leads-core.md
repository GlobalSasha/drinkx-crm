# Бэкенд — Ядро лидов

Домены: `leads`, `contacts`, `companies`, `pipelines`, `activity`, `custom_attributes`.

Это сердце CRM. Почти все остальные домены ссылаются сюда. Изменения здесь
расходятся по всей системе — читай **⚠️ Подводные камни** обязательно.

---

## leads

**Назначение.** Управление лидами B2B-сделок: базовые данные (компания, контакты,
статус), скоринг, пул неназначенных, claim/transfer, движение по воронке.

**Файлы** (`app/leads/`):
- `models.py` — `Lead`, `LeadStageHistory`; enum `DealType`, `Priority`, `AssignmentStatus`.
- `schemas.py` — `LeadCreate/Update/Out/ListItemOut`, `MoveStageIn`, `DealPatchIn`, `ScoreDetailsPatchIn`, `ScoreBreakdownOut`, `StageDurationOut`.
- `repositories.py` — `list_leads`, `list_pool`, `claim_lead`, `claim_sprint`, `transfer_lead`, CRUD.
- `services.py` — CRUD-сервисы, валидация enum, интеграция с automation/notifications.
- `routers.py` — все эндпоинты лида.
- `scoring.py` — чистые функции: `compute_total`, `priority_from_score` (пороги 80/60/40 → A/B/C/D).

**Модели.**
- `Lead` — основное: `company_name` (снимок!), `email`, `phone`, `website`, `inn`, `source`,
  `tags_json`; B2B: `deal_type`, `priority`, `score` (0–100), `fit_score` (0–10, от AI),
  `deal_amount/quantity/equipment`; управление: `assignment_status`, `assigned_to`,
  `transferred_from`, `needs_review`; rotting: `next_action_at`, `last_activity_at`,
  `is_rotting_stage`, `is_rotting_next_step`; lifecycle: `blocker`, `next_step`,
  `archived_at`, `won_at`, `lost_at`, `lost_reason`; AI: `agent_state` (JSON), `ai_data` (JSON);
  мессенджеры: `tg_chat_id`, `max_user_id`; `score_details_json`; `primary_contact_id`;
  FK `pipeline_id`, `stage_id`, `company_id`.
- `LeadStageHistory` — append-only: `lead_id`, `stage_id`, `entered_at`, `exited_at`, `duration_sec`.

**Эндпоинты.**
- `GET /leads` → фильтры stage/pipeline/segment/city/priority/deal_type/assigned_to/q + пагинация; scope по роли.
- `POST /leads` → create, авто-назначение на первый этап (position 0) дефолтной воронки.
- `GET /leads/pool` → пул, сортировка `fit_score DESC NULLS LAST`, фильтр `needs_review`.
- `POST /leads/sprint` → claim N лидов из пула (`FOR UPDATE SKIP LOCKED`, по городам/сегменту).
- `GET /leads/{id}` → с `primary_contact_name`, `open_counts`.
- `PATCH /leads/{id}` → update (запрет переименовать `company_name`, если linked → `CompanyNameLocked`).
- `DELETE /leads/{id}`.
- `POST /leads/{id}/claim` · `/unclaim` · `/transfer` — race-safe `UPDATE`, transfer логируется + уведомление.
- `POST /leads/{id}/move-stage` → через `automation.move_stage`, обработка gate-violations.
- `PATCH /leads/{id}/primary-contact` · `/deal` · `/score-details` (пересчитывает `score`+`priority`).
- `GET /leads/{id}/score-details` · `/stage-durations` · `/attributes`; `PATCH /attributes`.

**Побочные эффекты.**
- На claim/sprint-claim → Activity `lead_assigned`.
- Audit-лог на create/transfer/move_stage.
- На transfer → `safe_notify`.
- `LeadStageHistory` insert/update — **не здесь**, а в `automation/stage_change.py`.
- На create → `followups.seed_for_lead` (lazy import).
- При переименовании компании → `UPDATE leads.company_name` для активных (`archived_at IS NULL`).

**Зависимости.** `contacts`, `companies`, `pipelines`, `activity`, `followups`, `automation`,
`notifications`, `forms` (резолв формы по slug из `source`), `audit`, `auth`.

**⚠️ Подводные камни.**
- **Снимок имени компании (ADR-022):** менять `company_name` у linked-лида можно только через
  переименование компании, иначе `CompanyNameLocked`.
- **Два пути к контактам:** `lead.contacts` (через `Contact.lead_id`) и `lead.primary_contact_id`
  (LEFT JOIN без ORM-relationship). Не путать.
- **Загрузка списка:** `primary_contact_name`, `open_tasks_count`, `open_followups_count` резолвятся
  через LEFT JOIN + коррелированные подзапросы; требуют `db` в `_populate_extras()`, иначе остаются `None`.
- **Атрибуция форм (Sprint 3.6):** `source → slug → форма` батчем (один SELECT), UTM — DISTINCT ON;
  при ошибке fallback в `None`, не падает.
- **Пагинация пула:** `fit_score DESC NULLS LAST`, `created_at ASC`. Несогласованный nullsort при
  правках сортировки → пропуски/дубли на страницах.
- **PATCH score-details** не просто сохраняет JSON — пересчитывает `score` и `priority`; значения
  вне `0..max_value` → 400.
- **Rotting-флаги** (`is_rotting_*`) обновляет отдельная задача; жёсткой связи с `rot_days`/датой нет.
- **`needs_review`** = TRUE только у AI-автосозданных лидов; везде ещё (формы, ручной ввод, CSV) — FALSE.

---

## contacts

**Назначение.** Множественные контакты/стейкхолдеры на каждый лид (ЛПР, champion, technical,
operational) с ролями и статусом верификации. Всё scoped по `lead_id`.

**Файлы** (`app/contacts/`): `models.py` (`Contact`, enum `ContactRoleType`, `VerifiedStatus`),
`schemas.py`, `repositories.py`, `services.py`, `routers.py`.

**Модель `Contact`** — `lead_id` (FK CASCADE), `workspace_id`, `company_id` (FK SET NULL),
`name`, `title`, `role_type` (`economic_buyer|champion|technical_buyer|operational_buyer`),
`email`, `phone`, `telegram_url`, `linkedin_url`, `source`, `confidence` (default medium),
`verified_status` (default `to_verify`), `notes`.

**Эндпоинты.** `GET/POST /leads/{lead_id}/contacts`, `PATCH/DELETE /leads/{lead_id}/contacts/{id}`.

**Зависимости.** `leads`.

**⚠️ Подводные камни.**
- Только lead-scoped: кросс-лидовых операций нет.
- Удаление лида → каскадное удаление контактов (FK CASCADE).
- Если удалить контакт, который является primary → `lead.primary_contact_id` обнуляется (FK SET NULL).
- `company_id` опционален; при удалении компании контакт становится orphaned (SET NULL).
- `role_type = economic_buyer` нужен для гейта этапов ≥ 6 (см. `automation`).

---

## companies

**Назначение.** B2B-компании как контейнеры лидов: нормализация имени для дедупликации,
бизнес-данные, мягкая архивация (Sprint 3.3), merge.

**Файлы** (`app/companies/`): `models.py` (`Company`), `schemas.py` (+ `CompanyCardOut`,
`DuplicateCandidate`), `repositories.py`, `services.py`, `utils.py` (`normalize_company_name`,
`extract_domain`), `merge.py`, `routers.py`.

**Модель `Company`** — `workspace_id`, `name`, `normalized_name` (ключ дедупа), `legal_name`,
`inn`, `kpp`, `domain` (извлекается из website), `website`, `phone`, `email`, `city`, `address`,
`primary_segment`, `employee_range`, `notes`, `is_archived`, `archived_at`.

**Эндпоинты.**
- `GET /companies` (фильтры city/segment/is_archived).
- `POST /companies` → 409 `DuplicateCompanyWarning` по `normalized_name`, обход через `?force=true`.
- `GET /companies/{id}` → карточка (leads + contacts + recent activities).
- `PATCH /companies/{id}` → name-sync к активным лидам, пересчёт domain.
- `DELETE /companies/{id}` → soft-archive (`is_archived=true`).
- `POST /companies/{id}/merge-into/{target_id}` → 409 при конфликте ИНН без `?force`.

**⚠️ Подводные камни.**
- `normalized_name` и `domain` генерируются server-side; клиент их не шлёт.
- `DuplicateCompanyWarning` — это управляемый 409 с кандидатами, **не ошибка**; клиент может повторить с `?force=true`.
- Soft-archive: лиды сохраняют `company_id` + снимок `company_name`.
- Name-sync обновляет **только активные** лиды (`archived_at IS NULL`).

---

## pipelines

**Назначение.** Воронки продаж и этапы. Скоринг на этапах (`probability`, `rot_days`), gate-критерии.
Дефолтная воронка хранится на `Workspace.default_pipeline_id`.

**Файлы** (`app/pipelines/`): `models.py` (`Pipeline`, `Stage`, `PIPELINE_TYPES`, `DEFAULT_STAGES`
— 12 семян, `DEFAULT_GATE_CRITERIA`), `schemas.py`, `repositories.py`, `services.py`, `routers.py`.

**Модели.**
- `Pipeline` — `workspace_id`, `name`, `type` (`sales|partner|service`), `position`.
- `Stage` — `pipeline_id`, `name`, `position`, `color`, `rot_days`, `probability` (0–100),
  `is_won`, `is_lost`, `gate_criteria_json` (list[str]).

**Эндпоинты.** `GET /pipelines`, `GET /{id}`, `POST /pipelines` (admin/head),
`PATCH /{id}` (rename + **полная** замена этапов), `DELETE /{id}` (с гардами),
`POST /{id}/set-default` (+ уведомление admin/head).

**⚠️ Подводные камни.**
- **`PATCH` со `stages` — это полная замена, не merge.** Клиент шлёт весь список. Лиды на удалённых
  этапах → `stage_id = NULL` (FK SET NULL). Очень легко осиротить лидов.
- Дефолтная воронка — единственный источник истины `workspaces.default_pipeline_id` (миграция 0017
  убрала `pipelines.is_default`).
- `gate_criteria_json` — список строк, **не enforced на уровне БД**; проверка в `automation`.
- Гарды удаления: `PipelineHasLeads` (409 с count), `PipelineIsDefault` (409).

---

## activity

**Назначение.** Полиморфная лента событий лида: комментарии, задачи, напоминания, файлы, email,
сообщения мессенджеров, звонки, system-события, изменения этапа, AI-подсказки, сабмиты форм.
Unified Feed.

**Файлы** (`app/activity/`): `models.py` (`Activity`, enum `ActivityType`), `schemas.py`
(`FeedItemOut`, `AskBlakeIn/Out`), `repositories.py`, `services.py`, `routers.py`.

**Модель `Activity`** — `lead_id`, `user_id` (SET NULL), `type`, `payload_json`, `task_due_at`,
`task_done`, `task_completed_at`, `reminder_trigger_at`, `file_url/file_kind`, `channel/direction`,
`subject`, `body`, `gmail_message_id`, `gmail_raw_json`, `from/to_identifier`.

**Эндпоинты.**
- `GET /leads/{id}/activities` — фильтр по типу, cursor-пагинация, `ORDER BY COALESCE(received_at, created_at) DESC, id DESC`.
- `POST /leads/{id}/activities` (task требует `task_due_at`).
- `POST /leads/{id}/activities/{id}/complete-task`.
- `GET /leads/{id}/feed` — unified, с резолвом `author_name` (`ai_suggestion` → «Блейк»).
- `POST /leads/{id}/feed/ask-blake` → создаёт Activity(comment) + Activity(ai_suggestion) в одной транзакции, вызывает `lead_agent.chat`.

**⚠️ Подводные камни.**
- **Composite cursor** (`ISO_TIMESTAMP|UUID`): без UUID-тайбрейкера будут пропуски на коллизиях времени.
- Полиморфные колонки без CHECK-констрейнтов — дисциплина типа держится на сервисе.
- `ai_suggestion` на фронте всегда показывается как «Блейк» независимо от `user_id`.
- Gmail-ingest пишет `received_at` в `payload_json` — старые батчи сортируются по времени отправки.
- `chat()` глотает `LLMError` и возвращает вежливый русский fallback — `ask_blake` не видит ошибки.

---

## custom_attributes

**Назначение.** EAV (entity-attribute-value) — пользовательские поля на лидах. 4 типа
(text/number/date/select), workspace-scoped, **неизменяемый ключ**, переупорядочиваемые.

**Файлы** (`app/custom_attributes/`): `models.py` (`CustomAttributeDefinition`, `LeadCustomValue`),
`schemas.py`, `repositories.py`, `services.py`, `routers.py`.

**Модели.**
- `CustomAttributeDefinition` — `workspace_id`, `key` (immutable, unique per workspace), `label`,
  `kind` (`text|number|date|select`), `options_json`, `is_required`, `position`.
- `LeadCustomValue` — `lead_id`, `definition_id` (unique-пара), `value_text|value_number|value_date`.

**Эндпоинты.** `GET /custom-attributes`, `POST` (admin), `PATCH /{id}`, `DELETE /{id}` (CASCADE values),
`PATCH /reorder` (атомарно), `GET/PATCH /leads/{id}/attributes`.

**⚠️ Подводные камни.**
- **Ключ неизменяем** после создания (иначе осиротит значения). `kind` тоже менять нельзя.
- Соответствие `kind ↔ value` держится на сервисе (нет DB CHECK); миснетч → `InvalidValueForKind` (400).
- `upsert_value_from_string` парсит дату как ISO, число как float; ошибка парсинга → 400.
- `reorder` — all-or-nothing: если хоть один id не из workspace → 404, без частичной записи.
