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
| `vitest run` (web) | validated | 12 файлов, 51 тест |
| `tsc --noEmit` | validated | 0 ошибок |
| `eslint .` | validated | 0 ошибок, 90 старых предупреждений |
| `pytest` (api, Postgres) | validated | 966 passed |
| `pnpm build` | in_progress | — |
| Ручной прогон (head / manager) | blocked | тест-аккаунт Supabase не существует; нужен вход пользователя через Google в панели браузера |
