# Execution Status

APPROVE PLAN получен 2026-09-09 («да по всем» чекбоксам). Source of truth — DAG в `03-council-synthesis.md`.

Лейны: Codex и Grok CLI сегодня зависают (600 с без прогресса, дважды) → исполнители на Claude (`fast-worker`), оркестратор перепроверяет каждый дифф и сам перезапускает verification.

## Волна W1 — бэкенд-правки, общие файлы, гарды

| ID | Status | Agent | Changed files | Validation | Notes |
|---|---|---|---|---|---|
| B1 | in_progress | fast-worker | `apps/api/app/leads/{schemas,services,repositories,routers}.py`, `activity/services.py`, tests | полный `pytest` на Postgres | `mode`, `only_pool`, assignee=actor для manager, strip, лид из корзины, без self-notify |
| C0 | validated | оркестратор | `apps/web/lib/types.ts`, `lib/tasks.ts`, `lib/hooks/use-tasks.ts` | `npx tsc --noEmit` = 4 известные ошибки | `mode`/`only_pool` в типах, `keepPreviousData`, `enabled` |
| W0 | in_progress | fast-worker | `components/ui/UserSelect.tsx`, `lib/api-error.ts` + тесты | `vitest run`, `tsc` | после C0 |
| F0 | in_progress | fast-worker | `use-my-tasks.ts`, `TaskTable.tsx`, `TaskReminders.tsx` | `tsc` → 3 ошибки только в `tasks/page.tsx` | после C0 |

## Волна W2 — G2 ∥ G4
pending.

## Волна W3 — верификация
pending.
