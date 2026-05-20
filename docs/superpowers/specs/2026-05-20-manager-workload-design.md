# Manager Workload Visibility — Design

**Date:** 2026-05-20
**Status:** Approved (design)
**Goal:** Let an admin / head see what each manager currently has in progress — their live pipeline, current load per stage, and stuck deals — in a few seconds.

---

## Problem

Today a head of sales cannot see another manager's *current* book of work:

- `/pipeline` is hard-scoped to the current user (`_scope_assigned_to`, `apps/api/app/leads/routers.py:44`) with no UI to view a colleague's board.
- `/team` shows only *activity counters over a period* (KP sent, leads taken from pool, leads moved, tasks done) — not live load or stuck deals.

Research across 8 CRMs (Salesforce, HubSpot, Pipedrive, amoCRM, Bitrix24, Zoho, Close, Salesflare) shows the de-facto minimal set for a sales lead is: (1) an **owner filter on the pipeline**, (2) a **summary table `manager × stage × count/sum`**, (3) a **stuck-deals signal**. This feature delivers all three, reusing primitives we already have.

## Existing primitives (no new tracking needed)

- `leads.assigned_to`, `assignment_status` (`pool` / `assigned` / ...), `archived_at`, `stage_id`, `deal_amount`, `last_activity_at`.
- `leads.is_rotting_stage` / `leads.is_rotting_next_step` — persisted booleans (index `ix_leads_rotting`), maintained from each stage's `rot_days`, already consumed by the daily-plan scorer. **These are the definition of "stuck" — we reuse them, not a parallel threshold.**
- `stages`: `position`, `is_won`, `is_lost`, `probability`, `rot_days`, `name`, `color`.
- `GET /leads?assigned_to=<id>` already filters by manager (explicit value overrides self-scope).
- `app/team/` domain exists, gated by `require_admin_or_head`, with `GET /team/stats` + `GET /team/{id}/stats`.

## Shared definitions

- **Access:** the pipeline owner filter and the `/team` «Загрузка» tab are visible only to `admin` / `head` (`require_admin_or_head`). Regular managers see nothing new and keep their self-scoped view.
- **"In progress" (active lead):** `assignment_status = 'assigned'` AND `archived_at IS NULL` AND `stage_id IS NOT NULL` AND the stage is neither `is_won` nor `is_lost`.
- **"Stuck" (Зависшие):** `is_rotting_stage OR is_rotting_next_step`. UI label everywhere: **«Зависшие»** (singular «Зависло»).
- **Money display:** `deal_amount` rendered as `₽` (existing leads use RUB formatting on the lead card). Cells show count + sum.

---

## Screen 1 — Owner filter on the pipeline

Admin/head get a dropdown on `/pipeline`:

- **«Мои»** (default) — unchanged: no `assigned_to` sent → backend scopes to self.
- **‹each manager›** — sends `GET /leads?assigned_to=<id>`.
- **«Все»** — sends `GET /leads?all_assignees=true` → whole-workspace pipeline.

Regular managers do not see the dropdown and keep the self-scoped board.

### Backend change (`apps/api/app/leads/routers.py`)

Add `all_assignees: bool = False` query param to `GET /leads`. New scoping logic (replaces / wraps `_scope_assigned_to`), evaluated against the caller's role:

| Caller | `all_assignees` | explicit `assigned_to` | Result |
|---|---|---|---|
| admin/head | true | — | no assignee filter (whole workspace) |
| admin/head | false | `X` | filter to `X` |
| admin/head | false | none | self (current behavior) |
| regular | (any) | `X` (≠ self) | **self** (ignore — closes current leak) |
| regular | (any) | none | self |

**Security fix (in scope):** today `_scope_assigned_to` returns any explicit `assigned_to` with no role check, so a regular manager can already pass `?assigned_to=<colleague>` and read a colleague's leads. The new logic only honors an explicit `assigned_to ≠ self` or `all_assignees=true` for admin/head; otherwise it forces self-scope.

**Text-search exception unchanged:** the current rule "`q` present → whole-workspace scope" (used by the message-to-lead picker so any colleague's lead is findable by name) stays exactly as-is. This is an intentional, pre-existing carve-out for the picker and is out of scope for this change — we only alter the no-`q` assignee path. The picker reads name/company for matching, not the kanban board.

The kanban itself is unchanged — it renders whatever `GET /leads` returns. The dropdown is the only new UI, gated on `role ∈ {admin, head}` via `useMe()`.

---

## Screens 2 + 3 — «Загрузка» tab on /team

### Backend — `GET /team/workload`

New endpoint in `app/team/` (gated `require_admin_or_head`, scoped to the caller's workspace). One aggregate pass:

```sql
SELECT assigned_to, stage_id,
       COUNT(*)                                                          AS cnt,
       COALESCE(SUM(deal_amount), 0)                                     AS sum_amount,
       SUM(CASE WHEN is_rotting_stage OR is_rotting_next_step THEN 1 ELSE 0 END) AS stuck
FROM leads
WHERE workspace_id = :ws
  AND assignment_status = 'assigned'
  AND archived_at IS NULL
  AND stage_id IS NOT NULL
GROUP BY assigned_to, stage_id;
```

Terminal stages (`is_won` / `is_lost`) are excluded during assembly (join `stages`, drop won/lost). In Python: per manager build `{stage_id → {count, sum}}`, the per-manager totals (`open_count`, `pipeline_sum`, `stuck_count`), join users (name/email/role) and the non-terminal stage list (id/name/position/color, ordered by `position`). Managers with no active leads appear as a zero row. Rows where `assigned_to IS NULL` (active-but-unassigned, should be rare) are omitted from the table.

Response:

```jsonc
{
  "stages": [ { "id": "...", "name": "Квалификация", "position": 1, "color": "#0a84ff" }, ... ],
  "managers": [
    {
      "user_id": "...",
      "name": "Иван Иванов",
      "email": "ivan@...",
      "by_stage": { "<stage_id>": { "count": 4, "sum_amount": 1200000 }, ... },
      "open_count": 12,
      "pipeline_sum": 3400000,
      "stuck_count": 3
    }
  ]
}
```

### Frontend — `/team`

Add a view toggle at the top of `/team`: **«Активность»** (the existing per-period stats) ↔ **«Загрузка»** (the new table). Default keeps «Активность» so nothing changes for current users until they switch.

«Загрузка» table:
- Rows = managers; columns = non-terminal stages (in `position` order).
- Each stage cell: count (primary) + sum (secondary, muted). Zero cells muted.
- Trailing columns: **«Итого»** (open_count + pipeline_sum) and **«Зависшие»** (stuck_count, highlighted when > 0).
- Click a manager row → navigate to `/pipeline?assigned_to=<user_id>` (opens that manager's board via Screen 1).
- Click the «Зависшие» cell → same destination (`/pipeline?assigned_to=<user_id>`); MVP does not add a separate rotting filter on the pipeline.
- Loading / empty states consistent with the existing `/team` stats view.

---

## Architecture & files

**Backend (`apps/api/app/team/` — extend existing domain):**
- `repositories.py` — add `aggregate_workload(db, *, workspace_id)` returning the grouped rows; a helper to fetch non-terminal stages ordered by position; user lookup (reuse existing team user query if present).
- `services.py` — add `get_workload(db, *, workspace_id)` assembling the response (zero-fill managers, drop terminal stages, compute totals).
- `schemas.py` — add `WorkloadStageOut`, `WorkloadManagerOut`, `WorkloadOut`.
- `routers.py` — add `GET /team/workload` (`require_admin_or_head`).

**Backend (`apps/api/app/leads/routers.py`):**
- Add `all_assignees: bool = False` param + role-aware scoping replacing the bare `_scope_assigned_to` honoring of explicit ids.

**Frontend (`apps/web`):**
- `lib/types.ts` — `Workload`, `WorkloadManager`, `WorkloadStage` types.
- `lib/hooks/use-team-workload.ts` — `useTeamWorkload()` query hook (`GET /team/workload`).
- `app/(app)/team/page.tsx` — add the «Активность» / «Загрузка» toggle + render the workload table (or a `components/team/WorkloadTable.tsx` if the page grows unwieldy).
- `app/(app)/pipeline/...` — add the owner-filter dropdown (admin/head only), wiring `assigned_to` / `all_assignees` into the existing `useLeads`-style fetch.
- `lib/hooks/use-leads.ts` — thread the new `assigned_to` / `all_assignees` params into the leads query.

## Error handling

- `GET /team/workload`: admin/head only (403 otherwise via `require_admin_or_head`); always scoped to the caller's workspace (never a user-supplied workspace). No deal_amount → counted, sum contribution 0.
- Pipeline filter: a regular user passing `assigned_to`/`all_assignees` is silently scoped to self (no error, no leak).
- Frontend: dropdown hidden for non-admins; if the workload query fails, show the same error affordance as the stats view.

## Testing

Backend (mock-stubbed sqlalchemy pattern, per `tests/test_webforms.py`):
- `aggregate_workload` returns grouped rows; `get_workload` zero-fills managers, drops won/lost stages, computes `open_count` / `pipeline_sum` / `stuck_count`, orders stages by position.
- Scoping logic: admin/head + `all_assignees` → no filter; admin/head + explicit id → that id; regular + foreign id → self; none → self. (Table-driven test on the scoping helper.)
- `GET /team/workload` 403 for a regular user (gating).

Frontend: typecheck + lint + `pnpm build` (the `/team` page and `/pipeline` touch App-Router rendering). Manual: as admin, open `/team` → «Загрузка», verify counts/sums/«Зависшие»; click a row → lands on that manager's `/pipeline`; switch the pipeline dropdown across «Мои / ‹менеджер› / Все».

## Out of scope (YAGNI)

- Swimlanes by manager on the kanban.
- A dedicated rotting filter on the pipeline (clicking «Зависшие» just opens the manager's board).
- Weighted forecast (`sum × probability`) — `probability` exists but the table shows count + raw sum only.
- A separate `/workload` route — it lives as a tab on `/team`.
- Per-manager activity drill-down beyond what `/team/{id}/stats` already provides.

## Decisions resolved

1. Cell metric: **count + sum** (not count-only, not weighted forecast).
2. Placement: **new «Загрузка» tab on /team**; stuck deals are a **column** in that table, not a separate page.
3. Pipeline filter access: **admin/head only**, options **Мои / ‹менеджер› / Все**.
4. "Stuck" definition: reuse existing **`is_rotting_stage` / `is_rotting_next_step`**.
5. Label: **«Зависшие»** (chosen over «Протухло» / «Без активности» / «Требуют внимания»).
6. Security: close the existing `assigned_to` leak for regular users as part of the scoping change.
