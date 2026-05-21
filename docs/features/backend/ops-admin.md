# Бэкенд — Операции и администрирование

Домены: `auth`, `users`, `team`, `assignment`, `settings`, `forms`, `import_export`,
`scheduled`, `audit`, `common` + инфраструктура (`main.py`, `config.py`, `db.py`, `observability.py`).

---

## auth

**Назначение.** Аутентификация через Supabase JWT, bootstrap первого пользователя (создание
workspace), управление ролями (admin/head/manager).

**Файлы** (`app/auth/`): `models.py` (`Workspace`, `User`, `UserInvite`, `ScoringCriteria`),
`jwt.py` (stub / HS256 / ES256-RS256 через JWKS, кэш 10 мин), `dependencies.py` (`current_user`,
`require_admin`, `require_admin_or_head`), `services.py` (`upsert_user_from_token`), `routers.py`.

**Модели.**
- `Workspace` — `name`, `domain`, `plan`, `settings_json`, `sprint_capacity_per_week`, `default_pipeline_id`.
- `User` — `workspace_id` (CASCADE), `email`, `name`, `role`, `supabase_user_id`, `timezone`,
  `specialization` (JSON), `max_active_deals`, `working_hours_json`, `ui_prefs_json`, `onboarding_completed`.
- `UserInvite` — `email`, `suggested_role`, `accepted_at`.
- `ScoringCriteria` — `criterion_key`, `label`, `weight`, `max_value` (default 5).

**Эндпоинты.** `GET /api/auth/me`, `PATCH /auth/me`, `PATCH /auth/me/ui-prefs`.

**Bootstrap.** Первый вход → создаётся `Workspace` + `Pipeline` + 12 этапов; пользователь = `admin`.
Последующие → присоединяются как `manager` (опционально применяется pending-invite + `invite_accepted`).

**⚠️ Подводные камни.**
- **Stub-режим** (если `supabase_url`/`jwt_secret` пусты) возвращает фиксированный `dev@drinkx.tech` —
  в проде оба должны быть заполнены, иначе 500.
- **JWKS кэшируется 10 мин;** при ротации ключей Supabase один force-refetch по новому `kid` восстанавливает.
- `ui_prefs_json` хранит только overrides — читается через property с мержем дефолтов.

---

## users

**Назначение.** Управление командой: приглашения по email (Supabase magic-link), смена ролей
(с защитой последнего admin), удаление (с возвратом лидов в пул).

**Файлы** (`app/users/`): `repositories.py`, `services.py` (`invite_user`, `change_role`,
`delete_user`, `list_users`, `list_invites`), `routers.py`, `ui_prefs.py`, `supabase_admin.py`.
Модели — `User`/`UserInvite` из `auth`.

**Эндпоинты.** `GET /api/users`, `GET /api/users/invites`, `POST /api/users/invite`,
`PATCH /api/users/{id}/role`, `DELETE /api/users/{id}`.

**⚠️ Подводные камни.**
- **Идемпотентный invite:** повторная отправка magic-link даже при существующей `(workspace, email)`;
  если Supabase упал — строка не создаётся (`InviteSendFailed`).
- **`LastAdminRefusal` 409:** нельзя понизить/удалить последнего admin — сначала назначь другого.
- **`delete_user`** возвращает все активные лиды в пул (`assignment_status='pool'`, `assigned_to=NULL`);
  Activity и audit-строки удалённого остаются (FK SET NULL).
- Все мутации пишут audit.

---

## team

**Назначение.** Статистика команды (stats по менеджерам, daily breakdown, матрица загрузки).
**Только admin/head.** Read-only.

**Файлы** (`app/team/`): `repositories.py` (raw SQL агрегаты), `services.py` (`resolve_period`,
`team_stats`, `manager_stats`, `workload`), `routers.py`.

**Эндпоинты.** `GET /api/team/stats?period=today|week|month` (`TeamStatsOut`),
`GET /api/team/stats/{user_id}?period=` (`ManagerStatsOut` + daily breakdown),
`GET /api/team/workload` (`WorkloadOut`: manager × non-terminal stage с count/sum_amount/stuck).

**⚠️ Подводные камни.**
- **Bind-параметры в raw SQL — только `CAST(:p AS type)`, не `:p::type`** (постфиксный каст ломает
  парсинг имени параметра в SQLAlchemy → непривязанные значения → 500). Это была причина бага
  `/team/[manager]` 500 (PR #59).
- `resolve_period` — UTC-only, часовые пояса не учитываются.
- `daily_breakdown` опускает дни с нулевыми событиями — gaps добивает фронт.
- `workload` фильтрует терминальные этапы; `stuck` = `is_rotting_stage OR is_rotting_next_step` на текущий момент.

---

## assignment

**Назначение.** Заглушка под будущее распределение лидов (Phase 3). Сейчас логика
claim/transfer/pool↔assigned живёт в `app.leads.services`.

**Файлы.** Только `__init__.py`.

---

## settings

**Назначение.** Чтение/запись workspace-конфига: AI-бюджет, основная модель, статус Gmail/SMTP.
Мутации — admin-only.

**Файлы** (`app/settings/`): `routers.py`, `services.py` (`get_ai_settings`, `update_ai_settings`),
`schemas.py` (`AI_MODEL_CHOICES`, `ChannelsStatusOut`, `AISettingsOut`).

**Эндпоинты.** `GET /api/settings/channels` (Gmail+SMTP, read-only), `GET /api/settings/ai` (admin),
`PATCH /api/settings/ai` (admin).

**⚠️ Подводные камни.**
- `settings_json` **переписывается целиком** (`settings_json = {...}`) — in-place мутация JSON не
  отслеживается SQLAlchemy.
- `daily_budget_usd` = `ai_monthly_budget_usd / 30.0` из env.
- `current_spend_usd_today` читается из Redis; при сбое Redis → 0.0.

---

## forms

**Назначение.** Публичные веб-формы (Sprint 2.2) для захвата лидов через `embed.js`.

**Файлы** (`app/forms/`): `models.py` (`WebForm`, `FormSubmission`), `repositories.py`,
`services.py` (`create_form`, `update_form`, `delete_form` soft, `get_form_stats`),
`routers.py` (защищённые), `public_routers.py` (публичные: submit + embed.js),
`lead_factory.py`, `embed.py`, `slug.py`, `rate_limit.py`, `field_map.py`.

**Модели.** `WebForm` — `slug` (**unique глобально**), `fields_json`, `target_pipeline_id/stage_id`,
`redirect_url`, `is_active`, `submissions_count`. `FormSubmission` — `web_form_id`, `lead_id`,
`raw_payload`, `utm_json`, `source_domain`, `ip`.

**Эндпоинты.** `GET /api/forms`, `GET /{id}`, `GET /{id}/submissions`, `GET /{id}/stats` (admin/head),
`POST /api/forms` (admin/head), `PATCH/DELETE /{id}` (admin/head);
публичные: `POST /api/forms/{slug}/submit` (rate-limit 10/мин/IP), `GET /api/forms/{slug}/embed.js`.

**⚠️ Подводные камни.**
- **Slug уникален глобально**, не per-workspace; автогенерится из name + random suffix при коллизии (retry ×3).
- `delete_form` — soft (`is_active=False`); сабмиты и форма остаются, лендинги не 404-ятся.
- Валидация target: `stage` должна принадлежать `target_pipeline`.
- Публичный submit создаёт лид с `needs_review=False`; CORS для `/api/public/*` — wildcard (отдельный middleware, см. инфраструктуру).

---

## import_export

**Назначение.** Массовый импорт/экспорт лидов (CSV/Excel/JSON/YAML/Bitrix24/AmoCRM) по схеме
preview → apply через Celery.

**Файлы** (`app/import_export/`): `models.py` (`ImportJob`, `ExportJob`, `ImportError`),
`services.py` (`create_job`, `confirm_mapping`, `request_apply`, `create_export_job`, `fetch_export_payload`),
`parsers.py`, `mapper.py`, `diff_engine.py`, `exporters.py`, `redis_bytes.py`, `validators.py`, `field_map.py`, `routers.py`.

**Состояния `ImportJob`:** uploaded → mapping → previewed → running → succeeded/failed/cancelled.

**Эндпоинты.** `POST /api/import/upload`, `POST /{id}/mapping`, `POST /{id}/apply` (202), `GET /{id}`,
`GET /api/import`; `POST /api/export`, `GET /api/export`, `GET /api/export/{id}`, `GET /{id}/download`.

**⚠️ Подводные камни.**
- `diff_json` меняет структуру по стадиям (all_rows → mapped_rows → diff).
- Импорт/экспорт-задачи: **per-row commit** (UI поллит прогресс), per-failure → `ImportError`.
- `EXTRAS_FOR_COMMENT`: `deal_amount`/`notes` пишутся **не в строку лида**, а в comment-Activity (ADR-007).
- Экспорт-байты лежат в Redis с TTL 1 ч (`ExportPayloadGone` при промахе).
- `PREVIEW_ROWS=100` — UI видит первые 100 строк превью.
- Celery worker — `NullPool`, свежий engine на задачу (event-loop asyncpg).

---

## scheduled (Celery Beat)

**Назначение.** Планировщик периодических задач. Брокер/бэкенд — Redis.

**Файлы** (`app/scheduled/`): `celery_app.py` (конфиг + beat-расписание + импорт моделей),
`jobs.py` (задачи + `_build_task_engine_and_factory` + `_run()`-обёртка с аудитом `ScheduledJob`),
`daily_plan_runner.py`, `digest_runner.py`.

**Расписание (crontab, UTC).**
| Задача | Расписание |
|---|---|
| `daily_plan_generator` | каждый час `:00` |
| `followup_reminder_dispatcher` | каждые 15 мин |
| `daily_email_digest` | каждый час `:30` (runner шлёт только при local hour=8) |
| `gmail_incremental_sync` | каждые `GMAIL_SYNC_INTERVAL_MINUTES` (по умолч. 5 мин) |
| `automation_step_scheduler` | каждые 5 мин |
| `lead_agent_scan_silence` | каждые 6 ч `:00` |
| `pool_auto_enrich_batch` | ежедневно `03:00` |

Также задачи по запросу: `regenerate_for_user`, `gmail_history_sync`, `auto_create_lead_from_email`
(порог confidence **0.85**), `run_export`, `run_bulk_update`, `bulk_import_run`,
`lead_agent_refresh_suggestion`, `transcribe_call`, `run_enrichment_task`.

**⚠️ Подводные камни.**
- **`NullPool` на каждый вызов** (`asyncio.run()` создаёт новый event loop; asyncpg-коннекты привязаны к loop).
- **Сериализатор задач — JSON:** аргументы должны быть JSON-сериализуемы (UUID как `str`, не `uuid.UUID`).
- `_run()` пишет строку аудита `ScheduledJob` на каждую задачу, ловит исключения → structlog + Sentry.
- `auto_create_lead_from_email`: ниже порога 0.85 — молча отбрасывается (без `InboxItem`).
- Импорт моделей в `celery_app.py` обязателен — гидрирует mapper-registry до запуска задач.

---

## audit

**Назначение.** Append-only лог действий (workspace-scoped). Заполняется через `log()`, читается
только admin'ом.

**Файлы** (`app/audit/`): `models.py` (`AuditLog`), `audit.py` (`log()`), `repositories.py`, `routers.py`.

**Модель `AuditLog`** — `workspace_id`, `user_id` (nullable, SET NULL), `action` (напр. `lead.move_stage`),
`entity_type`, `entity_id`, `delta_json`. Индексы: `(workspace_id, created_at)`, `(entity_type, entity_id)`.

**Эндпоинт.** `GET /api/audit` (admin-only, пагинация, фильтр entity).

**⚠️ Подводные камни.**
- `log()` стейджит строку в **ту же транзакцию**, что и операция — при откате родителя лог тоже откатывается.
- **Никогда не бросает** (Sentry + warning), операция продолжается.
- `user_id` = NULL для системных событий (cron/вебхуки).
- `delta_json` — ad-hoc по вызывающему, без схемы.

---

## common

**Файлы** (`app/common/`): `models.py` (`Base`, `TimestampedMixin`, `UUIDPrimaryKeyMixin`),
`sentry_capture.py` (`capture(exc, fingerprint, tags)`).

Все доменные модели наследуют `Base` + `UUIDPrimaryKeyMixin` + (где нужно) `TimestampedMixin`.
Таймстемпы — server-side (`func.now()` + `onupdate`).

---

## Инфраструктура

**`main.py` (`create_app`).** Порядок middleware: `PublicFormsCORSMiddleware` (wildcard `/api/public/*`,
**первым**, шорт-кат OPTIONS) → `CORSMiddleware` (рестриктивный для `/api/*`) → lifespan (Sentry-init
при DSN) → `/health`, `/version` → регистрация всех доменных роутеров.

**`config.py` (Pydantic Settings, env + `.env`).** Ключевое: `app_env`, `cors_origins`, `workspace_name`
(single-workspace hotfix); `database_url` (asyncpg), `redis_url`; Supabase-креды; AI
(`mimo_*`, `anthropic/gemini/deepseek/openai` keys, `crm_ai_backend=mimo`, `llm_fallback_chain`);
бюджет (`ai_monthly_budget_usd`, `ai_max_parallel_jobs`); SMTP (stub при пустом host); Google OAuth
(`gmail_*`); `fernet_key` (шифрование кредов); `import_max_upload_mb`; `form_rate_limit_per_minute`;
Telegram; Mango VPBX; STT (`stt_provider=salute`); `sentry_dsn`.

**`db.py`.** Lazy-синглтоны `get_engine()` / `get_session_factory()`; asyncpg, `pool_pre_ping=True`,
`expire_on_commit=False`; FastAPI-dependency `get_db()`.

**`observability.py`.** `init_sentry_if_dsn()` — no-op при пустом DSN; `traces_sample_rate=0.1`.
