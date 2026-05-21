# DrinkX CRM — Техническая документация по функционалу

> **Назначение этого раздела.** Описать, *как именно работает* каждая функция CRM
> на уровне механик: что вызывается, что пишется в БД, какие события и фоновые
> задачи запускаются, от чего зависит. Цель — **менять код, не ломая механики**.
>
> Прежде чем трогать домен, прочитай его страницу здесь и обрати особое внимание
> на блок **⚠️ Подводные камни**.
>
> Документация для менеджера (как *пользоваться* CRM) лежит отдельно:
> [`docs/manual/РУКОВОДСТВО-МЕНЕДЖЕРА.md`](../manual/РУКОВОДСТВО-МЕНЕДЖЕРА.md).

## Как читать

Каждый домен описан по единому шаблону:

- **Назначение** — за что отвечает.
- **Файлы** — что в каком файле живёт.
- **Модели/таблицы** — ключевые поля.
- **Операции / эндпоинты** — публичные функции и HTTP-маршруты.
- **Побочные эффекты** — что пишется, какие события/задачи/уведомления.
- **Зависимости** — какие домены вызываются.
- **⚠️ Подводные камни** — то, что сломается при неосторожном изменении.

## Карта документации

### Бэкенд (`apps/api/app/`)

| Файл | Домены |
|---|---|
| [backend/leads-core.md](backend/leads-core.md) | `leads`, `contacts`, `companies`, `pipelines`, `activity`, `custom_attributes` |
| [backend/ai-analytics.md](backend/ai-analytics.md) | `enrichment`, `lead_agent`, `llm_usage`, `daily_plan`, `knowledge`, `search` |
| [backend/comms-automation.md](backend/comms-automation.md) | `inbox`, `email`, `notifications`, `automation`, `automation_builder`, `followups`, `template` |
| [backend/ops-admin.md](backend/ops-admin.md) | `auth`, `users`, `team`, `assignment`, `settings`, `forms`, `import_export`, `scheduled`, `audit`, `common`, инфраструктура |

### Фронтенд (`apps/web/`)

| Файл | Содержимое |
|---|---|
| [frontend.md](frontend.md) | Все разделы `app/(app)/`, общая инфраструктура (api-client, stores, hooks, AppShell) |

## Стек (фактическое состояние)

| Слой | Технология |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, shadcn/ui + Tailwind, Zustand, TanStack Query |
| Backend | Python 3.12, FastAPI (async), SQLAlchemy 2.0 (async), Alembic |
| Очередь | Celery + Celery Beat, брокер/бэкенд — Redis |
| БД | PostgreSQL (asyncpg) |
| Auth | Supabase JWT (HS256 / ES256-RS256 через JWKS) + Google OAuth |
| LLM | MiMo (primary) → Anthropic → Gemini → DeepSeek (fallback-цепочка); OpenAI GPT-4o только для vision |
| Хостинг | bare-metal Ubuntu, Docker Compose (`web`, `api`, `worker`, `beat`) |

## Сквозные паттерны и инварианты

Эти правила действуют во **всех** доменах. Нарушение почти всегда означает баг.

1. **Workspace-изоляция.** Каждый запрос, каждый запрос к БД фильтруется по `workspace_id`.
   На текущем этапе single-workspace hotfix: первый вошедший пользователь создаёт
   workspace и становится `admin`, остальные — `manager`. Чужой `workspace_id` →
   404/no-op, а не утечка данных.

2. **Роли:** `admin` > `head` > `manager`. Мутирующие админ-операции защищены
   зависимостями `require_admin` / `require_admin_or_head` (`app/auth/dependencies.py`).

3. **Транзакции уведомлений и аудита.** `notify()` и `audit.log()` только *стейджат*
   строку в текущей сессии (flush, не commit) — коммит делает вызывающий домен вместе
   со своим изменением. Поэтому при откате родительской операции не остаётся
   «осиротевших» уведомлений/логов. `safe_notify()` и `audit.log()` **никогда не бросают
   исключение** (best-effort) — телеметрия не должна ронять бизнес-операцию.

4. **Длинные AI-задачи не блокируют REST.** POST создаёт job-сущность, возвращает 202,
   Celery-воркер дозаполняет результат, клиент опрашивает/подписывается. См. `enrichment`,
   `daily_plan`, `import_export`.

5. **Schemas AI-выводов — с дефолтами, без жёстких enum.** Pydantic-схемы LLM-ответов
   (`ResearchOutput`, `AgentSuggestion`) используют `Optional` + defaults и **никогда не
   падают** на отсутствующих/кривых полях — нормализацию делает фронтенд. См. PRD §7.2.

6. **Переходы по этапам — только через `app/automation/stage_change.py:move_stage`.**
   Это единственная точка, где меняется `lead.stage_id`. Она прогоняет pre-checks (гейты),
   применяет переход и запускает post-actions (Activity, история этапов, fan-out
   автоматизаций, refresh AI-подсказки). Прямой `UPDATE lead.stage_id` в обход этого —
   нарушение инварианта.

7. **Celery-задачи создают свой движок БД с `NullPool` на каждый вызов.** `asyncio.run()`
   создаёт новый event loop, а asyncpg-соединения привязаны к loop. Шаблон —
   `_build_task_engine_and_factory` в `app/scheduled/jobs.py`. Не переиспользуй
   глобальный engine в задачах.

8. **AI-бюджет.** Дневной лимит трат на LLM считается в Redis (`enrichment/budget.py`).
   Перед дорогими вызовами проверяется остаток; все вызовы пишутся в ledger `llm_usage`.

9. **Soft-delete там, где есть внешние ссылки.** `companies` (`is_archived`), `forms`
   (`is_active`). Жёсткое удаление — у `templates`, `users`, `automations` (с CASCADE на
   историю). `leads` сохраняют `company_name` снимком даже после архивации компании.

10. **Снимок названия компании (ADR-022).** `lead.company_name` — это снимок. У связанного
    с компанией лида имя меняется *только* через переименование компании (которое делает
    `UPDATE leads.company_name` для активных лидов), иначе — исключение `CompanyNameLocked`.

> Источники истины по продукту и решениям: `docs/PRD-v2.0.md`, `docs/brain/01_ARCHITECTURE.md`,
> `docs/brain/03_DECISIONS.md` (ADR), `docs/brain/05_GLOSSARY.md`.
