# Фронтенд (`apps/web`)

Next.js 15 (App Router) · TypeScript strict · shadcn/ui + Tailwind · Zustand (клиентское
состояние) · TanStack Query (серверное состояние). Маршруты повторяют IA продукта и лежат
в группе `app/(app)/`. Весь UI на русском.

> ⚠️ **Перед PR с фронтендом** `tsc --noEmit` недостаточно. Запускай `pnpm build` из `apps/web`
> (build-time проверки Next.js 15: typed routes, Suspense вокруг `useSearchParams`, RSC-импорты).
> Подробнее — `CLAUDE.md` → «Pre-PR checklist».

---

## Общая инфраструктура (`_shared`)

| Файл | Роль |
|---|---|
| `lib/api-client.ts` | Типизированная обёртка над `fetch`: авто-инжект Supabase JWT, единый разбор ошибок. Все запросы идут через неё. |
| `lib/design-system.ts` | Централизованные Tailwind-токены (типографика, цвета, поверхности, формы, кнопки, лэйаут). Не хардкодь стили мимо токенов. |
| `lib/store/pipeline-store.ts` | Zustand: фильтры (segments, cities, q), `selectedPipelineId` (localStorage), состояния модалок. |
| `lib/hooks/use-me.ts` | Текущий пользователь из `/auth/me`, `staleTime` 5 мин. Источник роли для гейтинга. |
| `lib/hooks/use-leads.ts` | Список лидов + `poolLeads`-вариант + мутации (claim, transfer, move-stage, create). |
| `lib/hooks/use-pipelines.ts` | Воронки: список/деталь, CRUD-мутации, установка дефолтной. |
| `components/.../AppShell.tsx` | Корневой лэйаут: Supabase-auth, `NotificationsDrawer`, `GlobalSearch` (⌘K), `SidebarNav`, адаптивная сетка. |
| `lib/types.ts` | TS-типы, зеркалящие Pydantic-схемы бэка (`LeadOut`, `ContactOut`, `Pipeline`, `Stage`, `MeOut`, enum `Priority A–D`, `AssignmentStatus`, `DealType`). |

**Сквозные паттерны.**
- **TanStack Query** для серверного состояния; инвалидация кэша на мутациях, оптимистичные апдейты.
- **Suspense-границы** вокруг динамических query-параметров (`/pipeline?stage=`, `/leads-pool?form_id=`, `/today?tab=`).
- **Гейтинг по ролям** через `useMe()`: `/team`, `/settings`, админ-секции форм — admin/head.
- **Cursor-пагинация** для длинных списков (зеркалит бэкенд).
- **Мобильность** — mobile-first; ряд экранов меняет лэйаут на < md.

---

## Разделы `app/(app)/`

### `/today` — Рабочий стол дня
Дашборд из перетаскиваемых виджетов (`@dnd-kit/core`, порядок в localStorage): счётчик задач,
follow-ups, rotting-лиды, мини-воронка, фокус-лиды, список задач (`TaskListWidget` с инлайн-чекбоксом
и прогресс-баром X/Y), инсайты Блейка, уведомления.
Данные: `GET /me/today`, `GET /me/followups-pending`. Инлайн-выполнение задач —
`POST /daily-plans/items/{id}/complete` (клик по чекбоксу не уводит в карточку).

### `/pipeline` — Воронка (Kanban)
Канбан на ≥ md, read-only список на < md (с липкой полосой-чипами этапов). Deep-link скролл к этапу
(`?stage=`). **Owner-scope: admin/head** видят чужих; менеджер — своих. Drag-drop карточек → модалки
перехода. Карточка — «чистая» (кто/что/когда); score/fit/rotting сознательно убраны (живут в карточке лида).
Данные/мутации через `use-leads`, `use-pipelines`, `pipeline-store`.

### `/leads/[id]` — Карточка лида
Динамическая страница, оборачивает компонент `LeadCard`: контакты, лента активности (Unified Feed),
follow-ups, сделка и AI-бриф, скоринг, история этапов. FAB «Блейк» → drawer с чатом
(`POST /leads/{id}/feed/ask-blake`). Обогащение — `POST /leads/{id}/enrichment` (202 + поллинг).

### `/leads-pool` — Пул лидов
Неназначенные лиды; фильтрация по 7 осям, AI bulk-update, кнопка «Взять» (claim, rate-limited),
сортировка по `fit_score`. Данные: `GET /leads/pool`.

### `/companies` — Компании
B2B-компании: список (фильтры city/segment/archived), карточка (лиды + контакты + активность),
soft-archive, предупреждение о дублях, merge. Данные: `GET /companies`, `GET /companies/{id}`.

### `/triage` — Несматченные сообщения
Входящие из Telegram/MAX/телефонии без привязки к лиду (`UnmatchedMessagesSection`).
Ручная привязка: `GET /api/inbox/unmatched/messages`, `PATCH /api/inbox/messages/{id}/assign`.

### `/automations` — Автоматизации (admin/head)
Конструктор правил триггер→условие→действие, история запусков (runs drawer).
Данные: `GET/POST/PATCH/DELETE /api/automations`, `GET /api/automations/{id}/runs`.

### `/forms` — Веб-формы (admin/head)
Конструктор форм для лендингов, живые счётчики сабмитов, тумблер активности, сниппет embed.js.
Данные: `GET/POST/PATCH/DELETE /api/forms`, `GET /api/forms/{id}/stats`.

### `/team` — Команда (admin/head)
Дашборд статистики менеджеров: карточки активности (today/week/month + daily breakdown) и
матрица загрузки (manager × этап). Данные: `GET /api/team/stats`, `/stats/{user_id}`, `/workload`.

### `/settings` — Настройки
Хаб из секций. Живые: воронки, команда, каналы, AI, затраты, кастом-поля, шаблоны, оформление.
В роадмапе: уведомления, API. Гейтинг админ-секций по роли.

### `/audit` — Журнал аудита (admin)
Просмотр append-only лога с пагинацией (50). Данные: `GET /api/audit`.

### `/knowledge` — База знаний
Заглушка-плейсхолдер (roadmap-стиль). Реальная KB сейчас — статичные markdown на бэке.

### Вне группы
- `/sign-in` — вход: Google OAuth + magic-link (email OTP) + кнопка тестового пользователя; обёрнут в Suspense.
- `/` — лендинг с брендингом и ссылками на вход / превью `/today`.
- `auth/` — служебные коллбэки авторизации.

---

## Где что искать при правках

| Меняешь… | Смотри |
|---|---|
| Запрос к API / обработку ошибок | `lib/api-client.ts` |
| Глобальные стили/токены | `lib/design-system.ts` |
| Фильтры воронки / выбранную воронку | `lib/store/pipeline-store.ts` |
| Поведение списков лидов / claim / transfer | `lib/hooks/use-leads.ts` |
| Корневой лэйаут, поиск ⌘K, уведомления | `AppShell.tsx` |
| Типы, зеркалящие бэкенд | `lib/types.ts` (синхронь с Pydantic-схемами) |
