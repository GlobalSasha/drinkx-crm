# Бэкенд — AI и аналитика

Домены: `enrichment`, `lead_agent`, `llm_usage`, `daily_plan`, `knowledge`, `search`.

Общая LLM-инфраструктура живёт в `enrichment/providers/`: фабрика
`complete_with_fallback()` гоняет цепочку **MiMo → Anthropic → Gemini → DeepSeek**
(любой 5xx/rate-limit/auth-error → следующий провайдер). OpenAI GPT-4o зарезервирован
только под vision. Все вызовы пишутся в ledger `llm_usage`, дневной бюджет считается
в Redis (`enrichment/budget.py`).

---

## enrichment

**Назначение.** Sales Research Agent — обогащает лид: профиль компании, ЛПР, сигналы
роста/риска. Оркеструет Brave Search + HH.ru + web-fetch + RSS → синтез LLM → `ResearchOutput`
в `lead.ai_data`.

**Файлы** (`app/enrichment/`):
- `models.py` — `EnrichmentRun` (lead_id, status, provider, duration_ms, sources_used, result_json, error).
- `schemas.py` — `ResearchOutput` (company_profile, signals[], decision_maker_hints, **fit_score 0–10**, next_steps[]), `FoundContact`.
- `services.py` — `trigger_enrichment` (гарды), `get_latest_run` (авто-протухание зависших > 5 мин), `list_runs`.
- `orchestrator.py` — `run_enrichment()`: build queries → параллельный fetch → промпт+KB → LLM → parse → persist.
- `tasks.py` — `pool_auto_enrich_batch` (Sprint 3.9, авто-обогащение пула, шаг 3с).
- `kb.py` — загрузка markdown KB (frontmatter YAML), `render_kb_for_prompt` (≤ 6000 симв.).
- `budget.py` — Redis-счётчик дневных трат `ai_budget:{workspace}:{day}`.
- `concurrency.py` — гард по числу параллельных run на workspace (`AI_MAX_PARALLEL_JOBS`).
- `providers/` — `base.py` (TaskType, CompletionResult, LLMError), `factory.py` (`complete_with_fallback`), `{mimo,anthropic,gemini,deepseek}.py`.
- `sources/` — `brave.py`, `hh.py`, `web_fetch.py`, `rss_feed.py`, `cache.py` (Redis-кэш по company_name).

**Эндпоинты.**
- `POST /leads/{id}/enrichment?mode=full|append|lightweight` → **202**, ставит фоновую задачу.
- `GET /leads/{id}/enrichment/latest` → `EnrichmentRunOut | None`.
- `GET /leads/{id}/enrichment` → история.

**Режимы.** `full` (перезаписать `ai_data`), `append` (только пустые ключи), `lightweight`
(без Brave/HH, только RSS+web — бесплатно).

**Побочные эффекты.** Создаёт `EnrichmentRun` (running → succeeded/failed + result_json);
обновляет `lead.ai_data` (+ `fit_score`, `company_profile`); audit `enrichment.trigger`;
`add_to_daily_spend` в Redis; Activity при найденных контактах; на низкой/нет уверенности
матча в inbox — Celery `auto_create_lead_from_email`.

**Зависимости.** `leads`, `contacts`, `activity`, `pipelines`, `audit`, `providers/*`,
`sources/*`, `scheduled.jobs`, Redis, Sentry.

**⚠️ Подводные камни.**
- **Зависший run.** Если фоновая задача упала посреди, строка остаётся `running` навсегда;
  `get_latest_run` авто-переводит её в `failed` спустя 5 минут (best-effort) — UI крутит спиннер
  до следующего опроса.
- **ResearchOutput не валидируется жёстко.** Любые строки (role, confidence, urgency) принимаются,
  чтобы не ронять пайплайн (PRD §7.2). Нормализация — на фронте.
- **`FoundContact.confidence`** мягко коэрсится: `None|""` → 0.0, `"high"` → 0.9. Непарсимое → 0.0.
- **KB режется по 1800 симв./запись** с суффиксом `…(обрезано)`.
- **Фоновая задача — `NullPool` engine**, dispose() в finally; при ошибке dispose возможна утечка (soft-log).
- Если все источники упали — синтез всё равно идёт с пустыми блоками («(нет результатов)»).

---

## lead_agent

**Назначение.** Sales Coach «Блейк». Два сервиса: (1) **подсказка-баннер** — короткая рекомендация
по лиду (confidence 0–1), кэшируется в `lead.agent_state['suggestion']`; (2) **чат** —
синхронный диалоговый коуч (подготовка к звонку, работа с возражениями, черновик КП) на MiMo Pro.

**Файлы** (`app/lead_agent/`): `schemas.py` (`AgentSuggestion`, `ChatRequest/Response`),
`context.py` (`load_product_foundation`, `build_lead_context`), `prompts.py`
(`SUGGESTION_SYSTEM` Flash, `CHAT_SYSTEM` Pro, `FOUNDATION_INJECT_CHARS=3000`),
`runner.py` (`get_suggestion`, `chat`), `tasks.py` (`refresh_suggestion_async`, `scan_silence_async`), `routers.py`.

**Состояние.** Своих моделей нет — состояние в `Lead.agent_state` (JSON, ключ `suggestion`).

**Эндпоинты.**
- `GET /agent/suggestion` → читает кэш, **без LLM**.
- `POST /agent/suggestion/refresh` → **202**, Celery `lead_agent_refresh_suggestion`.
- `POST /agent/chat` → синхронный LLM-вызов, 200.

**AI-детали.** Подсказка — TaskType.prefilter (MiMo Flash), JSON `{text, action_label, confidence}`.
Чат — TaskType.sales_coach (MiMo Pro). В промпт инжектится 3000 симв. product-foundation
(`apps/api/knowledge/agent/product-foundation.md`) + контекст лида.

**⚠️ Подводные камни.**
- **Файл foundation может отсутствовать** — soft-fail, агент работает без него (warning в лог).
  Прод-образ обязан `COPY knowledge ./knowledge`.
- **`confidence < 0.4` → `action_label` форсируется в null** (UI не предлагает действовать на шатком).
- **История чата:** клиент шлёт до 20 ходов, в промпт идёт только последние 6 (бюджет).
- **Чат при сбое LLM** возвращает вежливую строку (не исключение); подсказка — `None` (сохраняет предыдущий баннер).

---

## llm_usage

**Назначение.** Единый ledger стоимости всех LLM-вызовов (provider, task_type, токены, USD).
Нужен для дневного бюджет-гарда и админского дашборда затрат.

**Файлы** (`app/llm_usage/`): `models.py` (`LlmUsage`), `schemas.py` (`ProviderCostOut`, `LlmCostsOut`),
`repositories.py` (`insert_usage`, `period_bounds`, `aggregate_by_provider`),
`service.py` (`record_llm_usage`, `get_costs`).

**Модель `LlmUsage`** — `workspace_id`, `task_type`, `provider`, `model`, `prompt_tokens`,
`completion_tokens`, `cost_usd` (Numeric 10,6).

**⚠️ Подводные камни.**
- **Best-effort:** если `insert_usage` падает — исключение глотается (warning), обогащение/чат
  всё равно успешны; телеметрия молча теряется.
- Вызывается из `complete_with_fallback` после успешного LLM-вызова; строка стейджится в сессию
  вызывающего и коммитится вместе с ней.
- Нет FK на workspace — при удалении workspace остаются осиротевшие строки (ок для аудита).
- `period_bounds` работает в UTC; локальные TZ-допущения вызывающего могут сместить окна.

---

## daily_plan

**Назначение.** Дневной план менеджера — AI-ранжированный список лидов на сегодня с тайм-блоками
(утро/день/вечер), приоритет-скором и однострочными подсказками. Хранится как `DailyPlan` +
`DailyPlanItem`, перегенерируется по запросу.

**Файлы** (`app/daily_plan/`): `models.py` (`DailyPlan`, `DailyPlanItem`, `ScheduledJob`),
`priority_scorer.py` (`score_lead`), `services.py` (`generate_for_user`, `get_today_plan_for_user`,
`request_regenerate`, `mark_item_done`), `routers.py`, `api_schemas.py`.

**Формула приоритета** (`score_lead`, чистая, без LLM): база = `stage.probability` + бонусы
(просрочено +25, скоро +15, приоритет A/B/C +10/5/3, rotting +20, `fit_score`×1) − штрафы
(архив/терминал −50, не назначен −100).

**Эндпоинты.** `GET /me/today`, `GET /daily-plans/{date}`, `POST /daily-plans/{date}/regenerate` (202),
`POST /daily-plans/items/{id}/complete`.

**Модели.** `DailyPlan` — unique `(user_id, plan_date)`, `status` (pending/generating/ready/failed),
`summary_json`. `DailyPlanItem` — `priority_score`, `estimated_minutes`, `time_block`, `task_kind`,
`hint_one_liner` (≤ 80 симв.), `done`.

**⚠️ Подводные камни.**
- **Тайм-блоки** — наивное деление на трети, не учитывает `estimated_minutes`.
- **Рабочие часы:** `working_hours_json` ожидается как `{"mon": {"start","end"}, ...}`; кривая форма
  → fallback 360 мин (6 ч). Выходной = пустой слот = fallback.
- **План не инвалидируется**, если лид ушёл в won/lost/archived после генерации — устаревшие позиции остаются.
- `task_kind` определяется по ключевым словам в `next_step` («встреча»/«meeting») — слабая эвристика.

---

## knowledge

**Назначение.** Заглушка под будущий админ-UI базы знаний. Сейчас KB — это статичные markdown-файлы
в `apps/api/knowledge/`, которые на лету читают `enrichment` и `lead_agent`.

**Файлы.** Только `__init__.py` — реализации/моделей/эндпоинтов нет.

**⚠️ Подводные камни.** Редактирование KB = git-коммит + редеплой. `enrichment.kb` кэширует записи
через `@lru_cache` — изменения требуют рестарта процесса.

---

## search

**Назначение.** Глобальный поиск по workspace: компании, лиды, контакты. 1–2 символа → ILIKE
(точное вхождение); 3+ → триграммная схожесть PostgreSQL (`pg_trgm`, оператор `%`) + ILIKE с ранжированием.

**Файлы** (`app/search/`): `schemas.py` (`SearchHit`, `SearchResponse`), `repositories.py`
(`_search_ilike`, `_search_trgm`, `search`), `routers.py`.

**Эндпоинт.** `GET /search?q=...&limit=20` (только GET, read-only).

**⚠️ Подводные камни.**
- **Требует расширение `pg_trgm`** (`CREATE EXTENSION pg_trgm`) — иначе 3+-символьные запросы падают.
- 1–2 символа = только ILIKE (без fuzzy); пустой запрос → `mode=empty`.
- URL контакта: при orphaned-контакте (нет lead_id/company_id) ведёт на `/contacts/{id}`.
- У каждой ветки UNION свой LIMIT — итог может быть меньше `limit` при неравномерном распределении.
