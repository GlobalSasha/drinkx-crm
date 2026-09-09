# Repository Context Pack — Руководитель отдела продаж (оставшийся объём: G2 + G4)

## Repository facts
- Монорепо pnpm: `apps/web` (Next.js ^15.1, React 19, TS ^5.7, TanStack Query ^5.62,
  TanStack Table, Radix Tabs, Tailwind, lucide-react) и `apps/api` (FastAPI, SQLAlchemy async,
  Alembic, pytest+asyncpg). См. `apps/web/package.json`, `apps/api/pyproject.toml`.
- Скрипты web: `npm run typecheck` (`tsc --noEmit`), `npm run lint` (`eslint .`),
  `pnpm build` (`next build`) — **build обязателен** при правках роутинга/`useSearchParams`
  (`CLAUDE.md` «Pre-PR checklist»).
- Дизайн-система: `.interface-design/system.md` — Manrope, кремовый канвас, один оранжевый
  акцент `brand-accent`, контролы `rounded-full`, карточки `rounded-card`. Токены и классы
  `C.*`, `T.*` — `apps/web/lib/design-system.ts`; типографика `.type-*` — `apps/web/app/globals.css`.
- Ветка работы: `feat/head-lead-assignment-and-tasks` (от `origin/main`). Коммиты `e7e9a98` (G1)
  и `4820308` (G3) уже в ней.

## Что уже сделано на бэкенде (факт из репозитория, коммиты в ветке)
| Что | Где |
|---|---|
| `POST /leads/assign` — admin/head; `lead_ids[]` **или** фильтр `cities/segment/fit_min/limit`; ответ `{assigned_count, requested, skipped, items[]}` | `apps/api/app/leads/routers.py` (после `/pool`), `services.assign_leads`, `repositories.assign_leads_by_ids` / `assign_pool_by_filter` |
| Уведомление `leads_assigned` (одно на пачку), `task_assigned`; оба выведены из часового окна дедупликации | `apps/api/app/notifications/services.py:46` |
| Миграция `0058`: `activities.assignee_user_id`, `activities.workspace_id`, `lead_id` nullable, CHECK `ck_activities_scope` | `apps/api/alembic/versions/20260909_0058_task_assignee_and_standalone.py` |
| `GET /tasks?assignee_user_id&author_user_id&status=all|open|done|overdue` — head/admin видят всех, менеджеру бэкенд сужает до своих | `apps/api/app/activity/routers.py` (`tasks_router`), `services.list_tasks` |
| `POST /tasks` `{text, task_due_at?, assignee_user_id?, lead_id?}` → `MyTaskOut`; `PATCH /tasks/{id}` `{text?, task_due_at?, assignee_user_id?}`; `POST /tasks/{id}/complete` / `/reopen` | там же; `schemas.TaskCreateIn`, `TaskPatchIn`, `MyTaskOut` |
| `MyTaskOut` расширен: `lead_id` nullable, `assignee_user_id/assignee_name/author_user_id/author_name` | `apps/api/app/activity/schemas.py:87` |
| Права на задачу: автор, исполнитель (явный → владелец лида → автор) или admin/head | `apps/api/app/activity/services.py` `_authorize_task_actor`, `effective_assignee_id` |
| `ActivityBase.assignee_user_id` — можно передать в существующий `POST /leads/{id}/activities` (type=task); менеджер на чужого → 403 | `apps/api/app/activity/schemas.py:10`, `services.create_activity` |

## Relevant files (frontend, оставшийся объём)
| Путь | Назначение | Почему важен | Риск изменения |
|---|---|---|---|
| `apps/web/app/(app)/leads-pool/page.tsx` | Страница «База лидов»: фильтры, таблица, тосты, `useClaimLead` | Сюда добавляется выделение и панель выдачи | Средний: большой файл (~480 строк), клиентская фильтрация, `Suspense` + `useSearchParams` → нужен `pnpm build` |
| `apps/web/components/leads-pool/PoolRow.tsx` | Строка таблицы базы: `<tr role="link" onClick=openLead>`, кнопка «Взять в работу» | Чекбокс должен жить здесь и **не** открывать карточку по клику (`stopPropagation`) | Низкий |
| `apps/web/components/leads-pool/PoolFilterBar.tsx` | Панель фильтров (город, сегмент, fit…) | Режим «N по фильтру» должен брать **текущие** фильтры страницы; бэкенд поддерживает только `cities/segment/fit_min` — остальные (tier, приоритет, теги, источник) клиентские | Не трогать; читать state из page |
| `apps/web/lib/hooks/use-leads.ts` | `usePoolLeads`, `useClaimLead` (ключи кэша) | Инвалидация после выдачи: `["leads","pool"]` и `["leads"]` | Низкий — только добавить хук |
| `apps/web/lib/hooks/use-users.ts` | `useUsers()` → `GET /users` (`{items: UserListItemOut[]}`) — все роли | Список менеджеров для селекта | Не трогать |
| `apps/web/lib/hooks/use-me.ts` | `useMe()` → `role` | Гейт UI по роли (как в `SidebarNavContainer.tsx:47-48`) | Не трогать |
| `apps/web/app/(app)/tasks/page.tsx` | Страница «Задачи»: чипы статус/срок, поиск, `DataTable`, `TaskEditModal`; данные `useMyTasks` | Сюда добавляются вкладки, фильтр по исполнителю, «Новая задача», колонка «Кому» | Средний: `router.push(/leads/${row.leadId})` при `leadId=null` даст `/leads/null` — надо гардить |
| `apps/web/components/tasks/TaskTable.tsx` | Таблица виджета `/today` (простая `<table>`) | `row.leadId` теперь `string \| null` — гард на клик | Низкий |
| `apps/web/components/tasks/TaskEditModal.tsx` | Правка задачи через `useUpdateLeadTask(leadId)` → `PATCH /leads/{id}/activities/{id}` | Для задач без лида путь не работает → перевести на `PATCH /tasks/{id}`; добавить селект исполнителя для head | Средний: модалку также использует карточка лида? — проверить `grep TaskEditModal` |
| `apps/web/lib/hooks/use-my-tasks.ts` | `useMyTasks`, `useCompleteMyTask`, `useReopenMyTask` — lead-scoped complete/reopen | Перевести на `/tasks/{id}/complete|reopen` (работает и с лидом, и без) | Низкий, но используется `/today` |
| `apps/web/lib/hooks/use-tasks.ts` | **Новый, уже написан (не закоммичен)**: `useTasks(filters)`, `useCreateTask`, `useUpdateTask`, `useSetTaskDone` с инвалидацией `tasks/my-tasks/daily-plan/feed` | Готовый слой данных для G4 | — |
| `apps/web/lib/tasks.ts` | `TaskRow`, `myTaskToRow`, `isOverdue`, `formatDueDateTime` — **уже расширен** (`leadId: string\|null`, `assigneeId/Name`, `authorId/Name`) | Общая модель строки для `/tasks` и `/today` | — |
| `apps/web/lib/types.ts` | **Уже расширен**: `MyTaskOut`, `TaskCreateIn`, `TaskPatchIn`, `TaskStatusFilter`, `LeadAssignIn/Out` | Контракты с API | — |
| `apps/web/components/ui/Modal.tsx` | `Modal({open,onClose,title,size,dismissOnBackdrop})` — role=dialog, Escape, focus trap | Обе новые модалки | Не трогать |
| `apps/web/components/ui/Tabs.tsx` | Radix `Tabs/TabsList/TabsTrigger/TabsContent` | Вкладки на `/tasks` | Не трогать |
| `apps/web/components/ui/DataTable.tsx` | TanStack-обёртка: `columns`, `data`, `onRowClick`, `rowKey`, `emptyState`, `meta.width/align` | Таблица `/tasks` | Не трогать |
| `apps/web/components/ui/Toast.tsx`, `Empty.tsx`, `Badge.tsx`, `PageHeader.tsx` | Готовые примитивы | Состояния success/error/empty | Не трогать |
| `apps/web/components/settings/TeamSection.tsx` | `ROLE_LABEL` {admin: Админ, head: Руководитель, manager: Менеджер} | Подписи ролей в селекте исполнителя | Взять паттерн, не импортировать |

## Existing product patterns
- Гейт по роли на клиенте: `const isAdminOrHead = me?.role === "admin" || me?.role === "head"` —
  `SidebarNavContainer.tsx:47`, `team/page.tsx`, `TeamSection.tsx:47`. Менеджер видит
  явное «нет доступа» (Empty с ShieldAlert), а не редирект — `team/page.tsx` шапка.
- Тосты на `/leads-pool`: локальный стек `ToastState[]` + `<Toast message type>` внизу справа
  (`leads-pool/page.tsx:15-20, 455-460`).
- Модалки с формой: `TaskEditModal.tsx` — шапка с `X`, поля с лейблом
  `text-xs font-mono uppercase`, `C.form.field`, кнопки `C.button.primary` + текстовая «Отмена»,
  `dismissOnBackdrop={false}`, ошибка `text-xs text-rose`.
- Чипы-фильтры: локальный `Chip` в `tasks/page.tsx:44-60` (`rounded-full`, активный —
  `bg-brand-accent text-white`).
- Кнопки в таблице не должны всплывать клик до строки-ссылки: `e.stopPropagation()`
  (`PoolRow.tsx:33`, `TaskTable.tsx:73`).
- Строки-ссылки: `<tr role="link" tabIndex=0 aria-label onKeyDown Enter>` (`PoolRow.tsx:47`).
- Даты: `datetime-local` ↔ ISO через `isoToLocalInput` (`TaskEditModal.tsx:19`), `new Date(local).toISOString()`.
- Списки пользователей в селектах: `<select>` с `ROLE_OPTIONS` (`TeamSection.tsx:330`).

## Data and API
- Лид: `assignment_status` `pool|assigned`, `assigned_to`, `transferred_from`; список пула —
  `GET /leads/pool?page_size=500` (весь пул одной страницей, фильтрация на клиенте:
  `leads-pool/page.tsx:149-170` в API).
- Пользователи: `GET /users` → `{items: [{id, name, email, role, last_login_at}], total}`.
- Задача = `activities(type=task)`; контракты см. таблицу «Что уже сделано».
- Tenant boundary: везде `workspace_id` пользователя из JWT; `POST /leads/assign` проверяет,
  что получатель в том же workspace; `GET /tasks` для менеджера принудительно сужен.
- Роли: `USER_ROLES = ("admin","head","manager")` — `apps/api/app/auth/models.py:19`;
  `require_admin_or_head` — `apps/api/app/auth/dependencies.py:68`.

## Test and CI setup
- API: `pytest` с asyncpg; DB-тесты требуют `postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test`
  (`tests/conftest.py:27-41`). Локально Postgres 16 поставлен через brew 2026-09-09
  (`brew services start postgresql@16`, роль `drinkx`, база `drinkx_test`). CI:
  `.github/workflows/test.yml` — Postgres-сервис, `uv run pytest -q` на PR.
- **Известная особенность**: запуск подмножества файлов падает на `NameError: Pipeline/Contact`
  (SQLAlchemy не успевает зарегистрировать модели) — pre-existing; гонять **весь** набор.
- Полный прогон 2026-09-09 (второй, после правки `tests/test_activities_crud.py` под новую
  сигнатуру `create_activity(..., actor: User, ...)`): **960 passed, 0 failed, 0 errors** —
  включая 12 тестов `test_lead_assignment.py` и 17 `test_task_assignment.py`. Первый прогон
  на свежей базе давал 7 errors в `test_utm*.py` и 1 в моём тесте — во втором исчезли, похоже
  на разовую гонку создания схемы; следить в CI.
- Web: тестов на компоненты нет; проверка — typecheck + lint + build + ручной прогон в
  браузере (Browser pane, `.claude/launch.json` — проверить наличие).

## Constraints
- Обратная совместимость: старые задачи (`assignee_user_id IS NULL`) читаются как «делает
  владелец лида»; `/today` виджет и карточка лида (`use-lead-tasks.ts`, `FeedComposer.tsx`)
  продолжают работать без правок.
- Не трогать `PoolFilterBar`, `Modal`, `Tabs`, `DataTable` — только использовать.
- Без новых зависимостей и без анимаций (инструмент на каждый день).
- Правило репозитория: задачи — только ручные, никакого AI в них (`tasks-no-ai` в памяти).
- `router.push(\`/leads/${leadId}\`)` при `null` — регрессия; гардить везде, где `leadId`.
- `pnpm build` обязателен: `/leads-pool` использует `useSearchParams` внутри `Suspense`.
- File ownership для параллельных implementer'ов: G2 (`leads-pool/*`, `use-leads.ts`) и
  G4 (`tasks/*`, `components/tasks/*`, `use-my-tasks.ts`, `use-tasks.ts`) не пересекаются;
  общие `lib/types.ts` и `lib/tasks.ts` уже изменены и в волны не входят.

## Open questions
- Нужна ли руководителю выдача **самому себе** в селекте (бэкенд разрешает) — предположение «да».
- Показывать ли на `/leads-pool` для руководителя, **кому** уже выдана карточка после выдачи —
  сейчас она просто исчезает из пула (это ожидаемо: пул = только `pool`).
