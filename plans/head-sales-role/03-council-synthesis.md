# Council Synthesis — Руководитель отдела продаж: интерфейс выдачи лидов (G2) и задач команды (G4)

## Executive summary
Строим оба экрана поверх готового бэкенда и существующих примитивов, без новых
зависимостей. Три развилки решены по совпадению независимых планов: (1) «N по фильтру»
отправляем **явными id первых N строк из отфильтрованного на клиенте списка**, а не серверным
фильтром — иначе руководитель получит не то, что видит; (2) `/today` не трогаем — виджет
чинится сменой путей в двух хуках; (3) перед фронтом — короткая **бэкенд-волна B1** на четыре
дыры, которые нашёл QA в уже написанном коде (одна из них — обход правила «ставить задачи
другим может только руководитель»).

## Council roster
| Роль | Модель / лейн | Статус |
|---|---|---|
| Product & UX planner | Claude (council:product-planner) | ok |
| QA / security / performance | Claude (council:qa-security-planner) | ok — плюс аудит готового бэкенда |
| Alternative engineer | ~~Grok CLI~~ → Claude general-purpose | Grok: сначала не залогинен, после `grok login` — завис на 600 с (дважды). Заменён. |
| Software architect | ~~Codex CLI~~ → Claude general-purpose | Codex завис на 600 с. Заменён; план получен. |

**Честно:** все четыре плана — из одного семейства моделей (Claude). Кросс-вендорной
независимости в этом раунде нет; компенсация — ролевые призмы и ручная сверка каждого
утверждения с кодом (см. «Проверено оркестратором»).

## Проверено оркестратором по коду (факты, не мнения)
- Ключ кэша пула — `["leads-pool", filters]` (`use-leads.ts:81`), списков — `["leads"]`; context pack ошибался, исправлено здесь.
- `/me` отдаёт `id` (`lib/types.ts:884`). `GET /users` — только принятые пользователи workspace.
- `PageHeader` имеет слот `actions` (`components/ui/PageHeader.tsx:25`).
- Третье место с `/leads/${lead_id}` — `components/reminders/TaskReminders.tsx:72`.
- R1 (пустой `lead_ids` = раздать норму спринта) — закреплено моим же тестом `test_lead_assignment.py:229`; для UI это опасный дефолт.
- R9 («Очистить срок» не работает) — оба пути правки (`activity/services.py:373, 523`) трактуют `None` как «не менять». Pre-existing.
- R11 (уведомление самому себе при выдаче) — в `assign_leads` проверки нет; в задачах есть (`_notify_assignee`).
- Поиск лида: есть `useGlobalSearch` (`use-search.ts:18`) и `useLeads({ q, workspace_search: true })` (`use-leads.ts:37,54`).
- **Vitest + testing-library есть** (`vitest.config.ts`, `package.json:47,60`, образец `components/lead-card/LeadCardHeader.test.tsx`) — context pack ошибался; компонентные тесты на новые модалки и таблицу — делаем.
- Ключ `["team-stats"]` существует (`use-team-stats.ts:14`) — инвалидировать после выдачи, чтобы `/team` не отставал.
- `TaskReminders` смонтирован глобально в `AppShell.tsx:188` (`fixed bottom, z-40`) — панель выделения не должна с ним драться по z-index.

## Consensus (независимо поддержано ≥ 2 планами)
1. **Явные id вместо серверного фильтра** для «N по фильтру» — Product, Engineer, QA (три из трёх).
2. **`/today` не трогать**; `useCompleteMyTask`/`useReopenMyTask` переводятся на `/tasks/{id}/…` с `leadId: string | null` — Engineer, QA, Product.
3. **Гарды `leadId = null`** в `tasks/page.tsx`, `TaskTable.tsx`, `TaskReminders.tsx` — все три.
4. **`TaskEditModal` переводится на `PATCH /tasks/{id}`**, остаётся общим с карточкой лида; селект исполнителя показывается только head/admin — все три.
5. **Одна модалка выдачи на два режима**, селект менеджера из `useUsers()`, тост «Выдано N из M» из ответа сервера — все три.
6. **Без `useSearchParams` на `/tasks`** (вкладка не в URL) — Product, Engineer.
7. **Клиентские чипы статуса/срока/поиска остаются**, с сервера берём только исполнителя/автора — Engineer; Product предлагал серверный `status` — отклонено (см. Disagreements).
8. **Чекбокс — необязательные пропсы `PoolRow`**, `stopPropagation`, `React.memo` — все три.
9. **Бэкенд-правки B1 до фронта** — QA; остальные не смотрели бэкенд, возражений нет.

## Disagreements and alternatives
| Area | Option A | Option B | Chosen | Reason |
|---|---|---|---|---|
| «N по фильтру» | Серверный фильтр `cities/segment/fit_min` + блокировка при немаппируемых фильтрах (Product, **Architect**) | `lead_ids = filtered.slice(0, N)` (Engineer, QA) | **B + флаг `only_pool` на бэкенде** | Архитектор прав: режим `lead_ids` забирает и чужие карточки (`repositories.py:653-655`), при устаревшем кэше head отнимет то, что менеджер взял секунду назад. Но серверный режим знает 3 поля из 13 — руководитель выдаст не то, что видит. Флаг `only_pool=true` (B1) закрывает оба риска: WYSIWYG + пропуск занятых со `skipped` в тосте. |
| Статус задач | Серверный `status` (Product) | Клиентские чипы как сейчас (Engineer) | **B** | Код уже есть; серверный статус = 4 query-key и refetch на каждый чип. |
| Сброс выделения при смене фильтра | Авто-чистка `selectedIds ∩ filtered` (Product, QA) | Оставлять `Set` как есть (Engineer) | **A, но при отправке**: на кнопке показываем `selectedIds ∩ filtered`, отправляем то же | Руководитель не должен выдать то, чего не видит. Один `useMemo`, без `useEffect` на все фильтры. |
| Поле «Лид» в «Новой задаче» | Не делать в v1 (Product) | `<select>` по `useLeads({q})` (Engineer) | **Typeahead на `useGlobalSearch`** | Бриф просит поле; готовый хук с дебаунсом есть. Ограничить 10 результатами, только лиды. |
| Панель выделения на мобильном | `fixed bottom-0` + поднять тосты (Product) | `sticky` внутри контента (Engineer) | **sticky** | Не конфликтует со стеком тостов и reminders (`fixed bottom`). |
| Общие компоненты до параллели | Каждая лента пишет свой селект и хелпер ошибок (Engineer) | Волна W0: `components/ui/UserSelect.tsx` + `lib/api-error.ts` (**Architect**) | **W0** | ~40 строк дублирования и два разных селекта на соседних экранах — хуже, чем 30 минут общей волны. |
| Компонентные тесты | Не заводить (Engineer, QA — думали, что раннера нет) | vitest уже есть (**Architect**) | **Писать** | Инфраструктура на месте; тесты на `AssignLeadsModal`, `TaskCreateModal`, `TaskTable`, `PoolRow`, `use-my-tasks` — дёшево. |
| «Мои» до ответа `/me` | Стартовать `useTasks` сразу | `enabled: !!me` (**Architect**) | **enabled** | Иначе head на мгновение видит всю команду во вкладке «Мои». |
| Уведомление самому себе при выдаче | Оставить | Подавить, как в задачах (QA R11) | **Подавить** | Единое поведение; одна строка в `assign_leads`. |
| Менеджер и `lead_id` чужого лида без исполнителя (QA R2) | Оставить старую семантику «владелец лида делает» | Для `manager` принудительно `assignee = actor` в `create_task` **и** `create_activity` | **B, оба входа** | Иначе `POST /tasks` — удобный обход правила. Задача менеджера всегда на нём; на чужой лид её можно поставить, но делать будет он сам. |

## Rejected ideas
- Отдельный экран «Распределение базы» — больше навигации и работы; панель на `/leads-pool` закрывает сценарий.
- Компонентные тесты для web — инфраструктуры нет; заводить её ради двух экранов дороже фичи.
- Серверная пагинация `GET /tasks` — при 3–5 менеджерах не нужна; порог тревоги 500 открытых задач на workspace.
- Индексы `activities(workspace_id) WHERE lead_id IS NULL` — отложить до `EXPLAIN` на проде.
- Поле «Комментарий» в модалке выдачи — бэкенд принимает, бриф не просит; v1 без него.

## Risks
| Risk | Severity | Probability | Mitigation | Owner |
|---|---:|---:|---|---|
| R3: `/today` и reminders ломаются на задаче без лида **сразу после деплоя бэкенда** (`today:302`, `TaskTable:65,69`, `TaskReminders:72`) | high | high | Волна F0 (гарды + смена путей) идёт первой и деплоится вместе с бэкендом | оркестратор |
| R1: пустой `lead_ids` = раздать норму спринта | high | medium | B1: явное поле `mode: "ids" \| "filter"` в `LeadAssignIn`; клиент не вызывает при 0 выделенных | backend |
| R2: менеджер ставит задачу коллеге через чужой лид без исполнителя | medium | medium | B1: `assignee = actor` для manager в обоих входах + тест | backend |
| R4: две головы Alembic при слиянии с `codex/invite-only-access` (0057); `Dockerfile:38` делает `upgrade head` → API не стартует | high | high (если обе ветки идут в main) | Merge-ревизия при слиянии второй ветки; порядок — решение пользователя | пользователь + оркестратор |
| R6: `downgrade()` 0058 удаляет задачи без лида | medium | low | Runbook: откат только с бэкапом; пункт в `04_NEXT_SPRINT.md` | оркестратор |
| R9: «Очистить срок» не работает (pre-existing) | low | — | В бэклог, не в этот спринт | — |
| R7: explicit-режим перехватывает карточку, взятую секунду назад | low | low | Окно = между загрузкой пула и кликом; `transferred_from` пишется; тост показывает `skipped` | — |
| R16: ключ кэша пула | low | — | Инвалидировать `["leads-pool"]` и `["leads"]` | frontend |
| `TaskEditModal` общий с карточкой лида — смена пути на `/tasks/{id}` | medium | low | Права: владелец лида = эффективный исполнитель → проходит; ручной клик из `TasksTab` в чек-листе | G4 |

## Final architecture decision
- **Бэкенд B1 (до фронта, одна волна):** `LeadAssignIn.mode` обязательный (`"ids"` требует непустой `lead_ids`; `"filter"` — хотя бы один фильтр или `limit`); **`only_pool: bool = True`** для режима `ids` — занятые карточки пропускаются и считаются в `skipped` (перехват остаётся через `only_pool=false`, для API); `create_task`/`create_activity`: для `manager` `assignee_user_id = actor.id`, если не задан; `update_task_by_id`: `strip()` и отказ на пустой текст; `create_task` с `lead_id` из корзины → 404; `assign_leads` не шлёт уведомление, когда получатель = актор. Тесты на каждое.
- **Фронт W0 (общее, до параллели):** `components/ui/UserSelect.tsx` (селект сотрудника, подписи ролей, «(вы)», `allowEmpty`) и `lib/api-error.ts` (`apiErrorDetail(err, fallback)`), оба с vitest-тестами.
- **Фронт F0 (первым):** `use-my-tasks.ts` → `/tasks/{id}/complete|reopen`, `leadId: string | null`, инвалидация `["tasks"]`; гарды в `TaskTable.tsx` и `TaskReminders.tsx`. После F0 `tsc` даёт 3 ошибки только в `tasks/page.tsx` (закрывает G4).
- **G2:** `useAssignLeads` в `use-leads.ts`; `PoolRow` с `selectable/selected/onToggleSelect` + `memo`; `SelectionBar` (sticky); `AssignLeadsModal` (режимы `selected` / `topN`, оба шлют `mode:"ids"` + `lead_ids` + `only_pool:true`; в `topN` — refetch пула перед отправкой); интеграция в `leads-pool/page.tsx` с гейтом `useMe`.
- **G4:** `tasks/page.tsx` — `useTasks`, `Tabs` (Мои / Поставлено мной / Команда), селект исполнителя на «Команда», колонка «Кому», гард `leadId`, кнопка в `PageHeader.actions`, локальный стек тостов; `TaskCreateModal` (текст, срок, исполнитель через `UserSelect`, лид-typeahead на `useLeads({q, workspace_search:true, page_size:12})` по образцу `inbox/UnmatchedMessagesSection.tsx:75-81`); `TaskEditModal` → `useUpdateTask` + селект исполнителя для head/admin.
- **Не трогать:** `today/page.tsx`, `TasksTab.tsx`, `PoolFilterBar`, `Modal`, `Tabs`, `DataTable`, `use-users.ts`, `use-me.ts`. `lib/types.ts`, `lib/tasks.ts`, `use-tasks.ts` — коммитятся до волн (в `use-tasks.ts` добавляются `placeholderData: keepPreviousData` и `options.enabled`; в `types.ts` — `mode` и `only_pool` в `LeadAssignIn`).

## Human approval gates
- [ ] **Бэкенд-волна B1** — меняет контракт `POST /leads/assign` (обязательное поле `mode`; клиентов у эндпоинта пока нет, кроме этого фронта) и правило прав для менеджера в двух входах создания задач.
- [ ] **Обратная совместимость `TaskEditModal`** — общая модалка карточки лида переезжает на `PATCH /tasks/{id}`.
- [ ] **Порядок слияния с `codex/invite-only-access`** (две головы Alembic) — решение до PR в `main`, не до начала кода.
- [ ] Незакоммиченные файлы `lib/types.ts`, `lib/tasks.ts`, `lib/hooks/use-tasks.ts` (написаны до подключения совета) — принять как основу волн.

## Final task DAG
| ID | Task | Owner role | Depends on | Files | Acceptance criteria | Validation |
|---|---|---|---|---|---|---|
| B1 | Бэкенд-правки по QA + архитектору: `mode` и `only_pool` в `LeadAssignIn` (repo `assign_leads_by_ids` пропускает занятые при `only_pool`); `assignee=actor` для manager в `create_task` и `create_activity`; `strip()` в `update_task_by_id`; 404 на лид из корзины; без self-notify в `assign_leads` | backend (codex-implementer или fast-worker) | — | `apps/api/app/leads/schemas.py`, `leads/services.py`, `activity/services.py`, `tests/test_lead_assignment.py`, `tests/test_task_assignment.py` | 6 новых тестов зелёные (в т.ч. `only_pool` пропускает занятую карточку); тест `falls_back_to_sprint_capacity` переписан под `mode:"filter"` | полный `pytest` на Postgres |
| C0 | Закоммитить `lib/types.ts` (+`mode`), `lib/tasks.ts`, `use-tasks.ts` (+`keepPreviousData`) | оркестратор | B1 (контракт `mode`) | те три файла | `tsc` даёт ровно 4 известные ошибки | `npx tsc --noEmit` |
| W0 | `UserSelect.tsx` + `lib/api-error.ts` + их vitest-тесты | frontend (fast-worker) | C0 | новые 2 файла + 2 теста | `vitest run` зелёный; `tsc` без новых ошибок | `vitest run`, `tsc` |
| F0 | Гарды `leadId=null` + пути `/tasks/{id}` в `use-my-tasks.ts`, `TaskTable.tsx`, `TaskReminders.tsx` | frontend (grok/fast-worker) | C0 | те три файла | `tsc` → 3 ошибки только в `tasks/page.tsx`; `/today` закрывает задачу без лида | `npx tsc --noEmit`, ручной `/today` |
| G2-1 | `useAssignLeads` | frontend-G2 | C0 | `use-leads.ts` | инвалидирует `leads-pool` и `leads` | `tsc` |
| G2-2 | `PoolRow` чекбокс + `memo` | frontend-G2 | — | `PoolRow.tsx` | без пропсов рендер идентичен; Space/клик не открывают карточку | ручной |
| G2-3 | `SelectionBar` + `AssignLeadsModal` + тесты (`PoolRow.test`, `AssignLeadsModal.test`) | frontend-G2 | G2-1, W0 | новые файлы в `components/leads-pool/` | disabled/loading/error по §5 брифа; оба режима шлют `mode:"ids"`, `only_pool:true` | `vitest run`, `tsc` |
| G2-4 | Интеграция в `leads-pool/page.tsx` | frontend-G2 | G2-2, G2-3 | `leads-pool/page.tsx` | сценарии 1–2 брифа; менеджер — без чекбоксов | `pnpm build`, ручной head+manager |
| G4-1 | `TaskEditModal` → `useUpdateTask`, `leadId\|null`, селект исполнителя (`UserSelect`) + тест | frontend-G4 | F0, W0 | `TaskEditModal.tsx` | правка из `TasksTab` работает; задача без лида правится | ручной |
| G4-2 | `TaskCreateModal` с лид-typeahead + тест | frontend-G4 | F0, W0 | новый `TaskCreateModal.tsx` | disabled/error; задача с исполнителем и без лида создаётся | ручной |
| G4-3 | `tasks/page.tsx`: вкладки, фильтр, «Кому», гард, кнопка, тосты, Empty | frontend-G4 | G4-1, G4-2 | `tasks/page.tsx` | `tsc` 0 ошибок; сценарии 3–5 брифа; менеджер без «Команды» | `pnpm build`, ручной |
| V | typecheck + lint + build + `vitest run` + полный pytest + ручной чек-лист QA §8.3 в двух сессиях (Browser pane; добавить конфиг `next dev` в `.claude/launch.json`) | оркестратор | G2-4, G4-3 | — | всё зелёное, чек-лист пройден | команды + Browser pane |

**Волны:** W1 = B1 → C0 → {W0 ∥ F0} (быстрые) · W2 = {G2-1, G2-2, G2-3, G2-4} ∥ {G4-1, G4-2, G4-3} (файлы не пересекаются) · W3 = V.

## Вклад архитектора (пришёл последним, учтён выше)
- Поймал главный конфликт трёх планов: `lead_ids` отнимает чужие карточки → принят флаг `only_pool`.
- Поправил карту: vitest есть → компонентные тесты в DAG.
- Волна W0 с общими `UserSelect` и `apiErrorDetail`; `enabled` для `useTasks`; `["team-stats"]` в инвалидацию; `TaskReminders` глобален (`AppShell.tsx:188`) — панель выделения `sticky`, не `fixed`, чтобы не спорить за нижний край.
- Его же открытый вопрос про «Очистить срок» (R9) — подтверждён, в бэклог.

## Critique round
Не проводился (medium).
