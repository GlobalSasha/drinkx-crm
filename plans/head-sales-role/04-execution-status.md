# Execution Status

APPROVE PLAN получен 2026-09-09 («да по всем» чекбоксам). Source of truth — DAG в `03-council-synthesis.md`.

Лейны: Codex и Grok CLI сегодня зависают (600 с без прогресса, дважды) → исполнители на Claude (`fast-worker`), оркестратор перепроверяет каждый дифф и сам перезапускает verification.

## Волна W1 — бэкенд-правки, общие файлы, гарды

| ID | Status | Agent | Changed files | Validation | Notes |
|---|---|---|---|---|---|
| B1 | validated | fast-worker | `apps/api/app/leads/{schemas,services,repositories,routers}.py`, `activity/services.py`, tests | полный `pytest` на Postgres | `mode`, `only_pool`, assignee=actor для manager, strip, лид из корзины, без self-notify |
| C0 | validated | оркестратор | `apps/web/lib/types.ts`, `lib/tasks.ts`, `lib/hooks/use-tasks.ts` | `npx tsc --noEmit` = 4 известные ошибки | `mode`/`only_pool` в типах, `keepPreviousData`, `enabled` |
| W0 | validated | fast-worker | `components/ui/UserSelect.tsx`, `lib/api-error.ts` + тесты | `vitest run`, `tsc` | после C0 |
| F0 | validated | fast-worker | `use-my-tasks.ts`, `TaskTable.tsx`, `TaskReminders.tsx` | `tsc` → 3 ошибки только в `tasks/page.tsx` | после C0 |

## Волна W2 — G2 ∥ G4 (запущена до завершения B1: файлы не пересекаются, контракт `mode`/`only_pool` уже в типах C0)

| ID | Status | Agent | Changed files | Validation | Notes |
|---|---|---|---|---|---|
| G2 (1–4) | validated | fast-worker | `use-leads.ts`, `PoolRow.tsx`, `SelectionBar.tsx`, `AssignLeadsModal.tsx`, `leads-pool/page.tsx` + 2 теста | `vitest`, `tsc`, `lint` | `mode:"ids"`, `only_pool:true`, topN = первые N из клиентского `filtered` после refetch |
| G4 (1–3) | validated | fast-worker | `tasks/page.tsx`, `TaskEditModal.tsx`, `TaskCreateModal.tsx` + 2 теста | `vitest`, `tsc` = 0, `lint` | вкладки, «Кому», «Новая задача», лид-typeahead |

## Волна W3 — верификация

| Проверка | Статус | Результат |
|---|---|---|
| `pytest` (api, Postgres) | validated | 977 passed, 0 failed |
| `vitest run` (web) | validated | 12 файлов, 53 теста |
| `tsc --noEmit` | validated | 0 ошибок (было 4) |
| `eslint .` | validated | 0 ошибок, 90 старых предупреждений |
| `pnpm build` | validated | exit 0; `/leads-pool` 12 kB, `/tasks` 6.3 kB |
| `alembic upgrade head` на чистой базе | validated | 0056 → 0058 без ошибок |
| Ручной прогон (head / manager) | **blocked** | см. «Блокер ручного E2E» ниже |

## Ревью (параллельно, не авторы кода)

| Ревью | Агент | Статус |
|---|---|---|
| QA | agent-skills:test-engineer | done — 12 находок (1 high, 5 medium, 5 low, 2 suggestion) |
| UX/UI | council:ux-reviewer | done — 2 blocking, 9 recommended, 13 optional |
| Code | agent-skills:code-reviewer | упал по лимиту сессии (429) — перезапущен |
| Security/perf | agent-skills:security-auditor | упал по лимиту сессии (429) — перезапущен |

## Волна W4 — правки по ревью (через codex-implementer)

| ID | Что | Status |
|---|---|---|
| F1 (high) | Метрика «просрочено» на панели руководителя считала задачи по владельцу лида: задача на чужой карточке уходила в чужой счётчик, задача без лида — никуда. Теперь COALESCE(assignee → владелец лида → автор), LEFT JOIN, workspace через COALESCE, архивные не считаются | validated — 977 pytest |
| F2 | «Очистить срок» не работало: null трактовался как «не менять», а один только срок давал 400. Роутеры отличают «не передано» от «передано null» через model_fields_set | validated |
| F3 | 3 теста на второй вход постановки задач (POST /leads/{id}/activities) | validated |
| F9 | fit_min=0.0 больше не считается отсутствием фильтра | validated |
| G2-01 (blocking) | Панель выделения лежала внутри overflow-x-auto — sticky прилипал к концу таблицы, а не к экрану. Вынесена наружу | validated — прочитан дифф |
| G2-02 (blocking) | Чекбокс строки 13 px рядом с кликабельной строкой: область тапа доведена до 44×44 через label | validated |
| G2-03…G2-07, G4-01…G4-04, G4-10 | Акцентный чекбокс вместо системного синего, честный текст кнопки, видимая причина неверного N, flex-wrap в шапке, «Кому» на мобильном, плейсхолдер в UserSelect, состояния поиска лида, тост при закрытии задачи, фолбэк имени вместо «null» | validated — 53 vitest, tsc 0, eslint 0 |
| G2-06 | Убран вызов refetchPool, который ничего не менял (id захвачены замыканием), и комментарий, обещавший несуществующую защиту | validated |

## Волна W5 — компенсация ручного прогона
Компонентные тесты ролевых гейтов страниц (находка F4): менеджер не видит чекбоксов,
панели выдачи и вкладки «Команда»; руководитель видит. Запущено через codex-implementer.

### Блокер ручного E2E
Supabase не пускает на локальный стенд: страница входа просит вернуть на
`http://localhost:3000/auth/callback`, этого адреса нет в списке Redirect URLs проекта,
и Supabase молча отправляет на Site URL — боевой домен. Поэтому все попытки входа
приходили на прод, а локальная база оставалась пустой. Починка — добавить
`http://localhost:3000/**` в Supabase → Authentication → URL Configuration.
Это настройка аккаунта, решение за владельцем.

### Отложено в бэклог (не в этом спринте)
- F5: тест гонок claim vs assign двумя сессиями (~1 ч, нужна вторая сессия в conftest).
- F11: HTTP-слой через TestClient с dependency_overrides — образца в репозитории нет (~2 ч, окупится на следующих фичах).
- DS-01: унификация шапок и лейблов старых модалок (проблема унаследована, не этой ветки).
- R4: merge-ревизия Alembic при слиянии с `codex/invite-only-access` (две головы от 0056).
- R6: откат миграции 0058 удаляет задачи без лида — только с бэкапом.
