# Manager Workload Visibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin/head see each manager's live load — an owner filter on the pipeline, plus a `/team` «Загрузка» tab with a `manager × stage` count+sum table and a «Зависшие» column.

**Architecture:** Reuse existing primitives (`leads.assigned_to/assignment_status/archived_at/stage_id/deal_amount/is_rotting_*`, `stages.is_won/is_lost/position/color`). Extend the `app/team/` domain with one aggregate endpoint. Make the leads list assignee-scoping role-aware (closing a self-scope leak). Frontend adds a pipeline dropdown (admin/head) and a `/team` tab.

**Tech Stack:** FastAPI, SQLAlchemy async (raw `text()` in team domain), Pydantic, pytest (mock-stubbed sqlalchemy); Next.js 15 App Router, TanStack Query, Tailwind.

**Spec:** `docs/superpowers/specs/2026-05-20-manager-workload-design.md`
**Branch:** `docs/manager-workload-spec` (continue on it).

---

## File Structure

**Backend:**
- `apps/api/app/leads/routers.py` — replace `_scope_assigned_to` with a role-aware `_resolve_assignee_scope`; add `all_assignees` query param to `GET /leads`.
- `apps/api/app/team/repositories.py` — add `workload_rows()` (one GROUP BY) + `non_terminal_stages()`.
- `apps/api/app/team/services.py` — add `workload()` assembling the response.
- `apps/api/app/team/schemas.py` — add `WorkloadStageOut`, `WorkloadCellOut`, `WorkloadManagerOut`, `WorkloadOut`.
- `apps/api/app/team/routers.py` — add `GET /team/workload`.

**Frontend:**
- `apps/web/lib/hooks/use-leads.ts` — add `assigned_to` / `all_assignees` to `LeadFilters` + `buildQuery`.
- `apps/web/app/(app)/pipeline/page.tsx` — owner dropdown (admin/head), wired into `useLeads`.
- `apps/web/lib/types.ts` — `Workload`, `WorkloadManager`, `WorkloadStage`, `WorkloadCell` types.
- `apps/web/lib/hooks/use-team-workload.ts` — `useTeamWorkload()` hook.
- `apps/web/components/team/WorkloadTable.tsx` — the table.
- `apps/web/app/(app)/team/page.tsx` — «Активность» / «Загрузка» view toggle.

---

## Task 1: Role-aware assignee scoping on GET /leads

**Files:**
- Modify: `apps/api/app/leads/routers.py`
- Test: `apps/api/tests/test_leads_assignee_scope.py`

Context: `_scope_assigned_to(explicit, user_id, q)` currently returns any explicit `assigned_to` with no role check — a regular manager can read a colleague's leads via `?assigned_to=<id>`. Replace it with a role-aware resolver and add an `all_assignees` flag for the «Все» option. `User.role` is `"admin"` / `"head"` / others (e.g. `"manager"`).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_leads_assignee_scope.py`:

```python
"""Manager workload — role-aware assignee scoping for GET /leads."""
from __future__ import annotations

import uuid

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_scope_admin_all_assignees_returns_none():
    from app.leads.routers import _resolve_assignee_scope
    u = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=True, q=None, user_id=u, role="admin"
    ) is None


def test_scope_head_explicit_returns_that_manager():
    from app.leads.routers import _resolve_assignee_scope
    me, other = uuid.uuid4(), uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=other, all_assignees=False, q=None, user_id=me, role="head"
    ) == other


def test_scope_admin_default_returns_self():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q=None, user_id=me, role="admin"
    ) == me


def test_scope_regular_foreign_id_forced_to_self():
    from app.leads.routers import _resolve_assignee_scope
    me, other = uuid.uuid4(), uuid.uuid4()
    # regular user trying to read a colleague → forced back to self (leak closed)
    assert _resolve_assignee_scope(
        explicit=other, all_assignees=True, q=None, user_id=me, role="manager"
    ) == me


def test_scope_regular_default_returns_self():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q=None, user_id=me, role="manager"
    ) == me


def test_scope_text_search_unchanged_whole_workspace():
    from app.leads.routers import _resolve_assignee_scope
    me = uuid.uuid4()
    # picker carve-out: q present → whole workspace (None), for any role
    assert _resolve_assignee_scope(
        explicit=None, all_assignees=False, q="кофейня", user_id=me, role="manager"
    ) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/bin/pytest tests/test_leads_assignee_scope.py -q`
Expected: FAIL (`_resolve_assignee_scope` not defined / still old `_scope_assigned_to`).

- [ ] **Step 3: Implement the resolver**

In `apps/api/app/leads/routers.py`, replace the existing `_scope_assigned_to` function (lines ~44-65) with:

```python
def _resolve_assignee_scope(
    *,
    explicit: UUID | None,
    all_assignees: bool,
    q: str | None,
    user_id: UUID,
    role: str,
) -> UUID | None:
    """Return the `assigned_to` filter for GET /leads (None = no assignee filter).

    `GET /leads` powers the pipeline kanban, /today widgets, and the
    message-to-lead picker. Scoping rules:

      - Text search (`q`) → whole workspace (None), unchanged: the picker
        must find any colleague's lead by name. (Pre-existing carve-out.)
      - admin/head + all_assignees → whole workspace (None) — the «Все» option.
      - admin/head + explicit id → that manager.
      - admin/head + nothing → self.
      - regular user → ALWAYS self (explicit/all_assignees ignored). This
        closes the prior leak where any user could pass ?assigned_to=<colleague>.
    """
    if q:
        return None
    privileged = role in ("admin", "head")
    if privileged:
        if all_assignees:
            return None
        if explicit is not None:
            return explicit
        return user_id
    return user_id
```

- [ ] **Step 4: Wire it into the endpoint**

In `apps/api/app/leads/routers.py`, in `list_leads` (~line 69): add the `all_assignees` query param and call the new resolver. Add the param after `q`:

```python
    q: str | None = None,
    all_assignees: bool = False,
    form_id: UUID | None = Query(None),
```

And replace the `assigned_to=_scope_assigned_to(assigned_to, user.id, q)` line (~92) with:

```python
        assigned_to=_resolve_assignee_scope(
            explicit=assigned_to,
            all_assignees=all_assignees,
            q=q,
            user_id=user.id,
            role=user.role,
        ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && .venv/bin/pytest tests/test_leads_assignee_scope.py -q`
Expected: PASS (6 passed).

Also confirm no other module imported the old name:
Run: `cd apps/api && grep -rn "_scope_assigned_to" app tests`
Expected: no matches (if any, update them to `_resolve_assignee_scope`).

- [ ] **Step 6: Compile + commit**

Run: `cd apps/api && .venv/bin/python -m py_compile app/leads/routers.py`

```bash
git add apps/api/app/leads/routers.py apps/api/tests/test_leads_assignee_scope.py
git commit -m "feat(leads): T1 — role-aware assignee scoping + all_assignees (close self-scope leak)"
```

---

## Task 2: Workload aggregate endpoint

**Files:**
- Modify: `apps/api/app/team/repositories.py`
- Modify: `apps/api/app/team/services.py`
- Modify: `apps/api/app/team/schemas.py`
- Modify: `apps/api/app/team/routers.py`
- Test: `apps/api/tests/test_team_workload.py`

Context: the team domain uses raw SQL via `text()` (see `kp_sent_per_user`). `users_repo.list_for_workspace(db, workspace_id=...)` returns `(users, total)`; each `User` has `.id/.name/.email/.role`. `require_admin_or_head` gates `/team` routes. Active lead = `assignment_status='assigned' AND archived_at IS NULL AND stage_id IS NOT NULL`, stage not won/lost.

- [ ] **Step 1: Add the repository queries**

Append to `apps/api/app/team/repositories.py`:

```python
async def workload_rows(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> list[tuple[uuid.UUID, uuid.UUID, int, float, int]]:
    """Per (assigned_to, stage_id): (count, sum_amount, stuck_count) over
    active assigned leads. Terminal stages are filtered out by the caller."""
    sql = text("""
        SELECT assigned_to,
               stage_id,
               count(*)                                   AS cnt,
               COALESCE(sum(deal_amount), 0)              AS sum_amount,
               sum(CASE WHEN is_rotting_stage OR is_rotting_next_step
                        THEN 1 ELSE 0 END)                AS stuck
        FROM leads
        WHERE workspace_id = :wid
          AND assignment_status = 'assigned'
          AND archived_at IS NULL
          AND stage_id IS NOT NULL
          AND assigned_to IS NOT NULL
        GROUP BY assigned_to, stage_id
    """)
    rows = (await db.execute(sql, {"wid": workspace_id})).all()
    return [
        (r.assigned_to, r.stage_id, int(r.cnt), float(r.sum_amount), int(r.stuck))
        for r in rows
    ]


async def non_terminal_stages(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> list[tuple[uuid.UUID, str, int, str]]:
    """Non won/lost stages for the workspace, ordered by position:
    (id, name, position, color)."""
    sql = text("""
        SELECT s.id, s.name, s.position, s.color
        FROM stages s
        JOIN pipelines p ON p.id = s.pipeline_id
        WHERE p.workspace_id = :wid
          AND s.is_won = false
          AND s.is_lost = false
        ORDER BY s.position, s.name
    """)
    rows = (await db.execute(sql, {"wid": workspace_id})).all()
    return [(r.id, r.name, int(r.position), r.color) for r in rows]
```

- [ ] **Step 2: Add the schemas**

Append to `apps/api/app/team/schemas.py`:

```python
class WorkloadStageOut(BaseModel):
    id: UUID
    name: str
    position: int
    color: str


class WorkloadCellOut(BaseModel):
    count: int
    sum_amount: float


class WorkloadManagerOut(BaseModel):
    user_id: UUID
    name: str
    email: str
    by_stage: dict[str, WorkloadCellOut]  # stage_id (str) → cell
    open_count: int
    pipeline_sum: float
    stuck_count: int


class WorkloadOut(BaseModel):
    stages: list[WorkloadStageOut]
    managers: list[WorkloadManagerOut]
```

Confirm `UUID` and `BaseModel` are already imported at the top of `schemas.py` (from `uuid` and `pydantic`); add the imports if missing.

- [ ] **Step 3: Add the service**

Append to `apps/api/app/team/services.py`:

```python
async def workload(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> dict:
    """Assemble the manager × stage workload table (active assigned leads,
    non-terminal stages only). Managers with no active leads appear as zero
    rows; rows are keyed only to non-terminal stages."""
    users, _total = await users_repo.list_for_workspace(db, workspace_id=workspace_id)
    stages = await repo.non_terminal_stages(db, workspace_id=workspace_id)
    valid_stage_ids = {sid for (sid, _n, _p, _c) in stages}

    rows = await repo.workload_rows(db, workspace_id=workspace_id)

    # assigned_to → { stage_id → (count, sum, stuck) }
    per_user: dict[uuid.UUID, dict[uuid.UUID, tuple[int, float, int]]] = {}
    for assigned_to, stage_id, cnt, sum_amount, stuck in rows:
        if stage_id not in valid_stage_ids:  # drop won/lost
            continue
        per_user.setdefault(assigned_to, {})[stage_id] = (cnt, sum_amount, stuck)

    managers = []
    for u in users:
        cells = per_user.get(u.id, {})
        by_stage = {
            str(sid): {"count": cnt, "sum_amount": s}
            for sid, (cnt, s, _stuck) in cells.items()
        }
        open_count = sum(cnt for (cnt, _s, _st) in cells.values())
        pipeline_sum = sum(s for (_c, s, _st) in cells.values())
        stuck_count = sum(st for (_c, _s, st) in cells.values())
        managers.append({
            "user_id": u.id,
            "name": u.name or u.email,
            "email": u.email,
            "by_stage": by_stage,
            "open_count": open_count,
            "pipeline_sum": pipeline_sum,
            "stuck_count": stuck_count,
        })

    return {
        "stages": [
            {"id": sid, "name": n, "position": p, "color": c}
            for (sid, n, p, c) in stages
        ],
        "managers": managers,
    }
```

- [ ] **Step 4: Add the router**

In `apps/api/app/team/routers.py`, add after the existing `get_manager_stats` route:

```python
@router.get("/workload", response_model=WorkloadOut)
async def get_workload(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> WorkloadOut:
    """Admin/head only. Manager × stage load over active assigned leads,
    scoped to the caller's workspace."""
    data = await services.workload(db, workspace_id=user.workspace_id)
    return WorkloadOut(**data)
```

Add `WorkloadOut` to the schema import at the top of `routers.py` (match how `TeamStatsOut` is imported). Confirm `services` is imported as a module (`from app.team import services`) or matches the existing call style — read the file's existing imports and match them exactly (the file already calls `services.team_stats` / `services.manager_stats` or imports those functions; follow whichever pattern is there).

- [ ] **Step 5: Write the test**

Create `apps/api/tests/test_team_workload.py`:

```python
"""Manager workload — aggregate assembly."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_workload_assembles_zero_fills_and_drops_terminal():
    from app.team import services

    s1, s2, terminal = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    u1, u2 = uuid.uuid4(), uuid.uuid4()

    user1 = MagicMock(id=u1, name="Иван", email="ivan@x.io")
    user2 = MagicMock(id=u2, name=None, email="petr@x.io")

    stages = [(s1, "Квалификация", 1, "#0a84ff"), (s2, "КП", 4, "#ff9f0a")]
    # u1 has leads in s1 (2, 100, 1 stuck) and a terminal-stage row that must be dropped
    rows = [
        (u1, s1, 2, 100.0, 1),
        (u1, terminal, 5, 999.0, 0),  # terminal → dropped
        (u1, s2, 1, 50.0, 0),
    ]

    with patch("app.team.services.users_repo.list_for_workspace",
               new=AsyncMock(return_value=([user1, user2], 2))):
        with patch("app.team.services.repo.non_terminal_stages",
                   new=AsyncMock(return_value=stages)):
            with patch("app.team.services.repo.workload_rows",
                       new=AsyncMock(return_value=rows)):
                out = await services.workload(MagicMock(), workspace_id=uuid.uuid4())

    assert [s["name"] for s in out["stages"]] == ["Квалификация", "КП"]
    by_id = {m["user_id"]: m for m in out["managers"]}

    m1 = by_id[u1]
    assert m1["by_stage"][str(s1)] == {"count": 2, "sum_amount": 100.0}
    assert str(terminal) not in m1["by_stage"]      # terminal dropped
    assert m1["open_count"] == 3                      # 2 + 1 (terminal excluded)
    assert m1["pipeline_sum"] == 150.0
    assert m1["stuck_count"] == 1

    m2 = by_id[u2]
    assert m2["name"] == "petr@x.io"                  # name=None → email fallback
    assert m2["by_stage"] == {}                       # zero row
    assert m2["open_count"] == 0 and m2["stuck_count"] == 0
```

- [ ] **Step 6: Run test + compile**

Run: `cd apps/api && .venv/bin/pytest tests/test_team_workload.py -q`
Expected: PASS (1 passed). If the `MagicMock` `User` objects break `u.name or u.email` (because `MagicMock().name` is special — `name` is a reserved MagicMock kwarg), construct the fakes with `user1 = MagicMock(id=u1, email="ivan@x.io"); user1.name = "Иван"` instead of passing `name=` to the constructor. Apply the same to `user2` (`user2.name = None`). Adjust the test accordingly.

Run: `cd apps/api && .venv/bin/python -m py_compile app/team/repositories.py app/team/services.py app/team/schemas.py app/team/routers.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/team/repositories.py apps/api/app/team/services.py apps/api/app/team/schemas.py apps/api/app/team/routers.py apps/api/tests/test_team_workload.py
git commit -m "feat(team): T2 — GET /team/workload (manager × stage load + stuck count)"
```

---

## Task 3: Frontend leads hook — assignee params

**Files:**
- Modify: `apps/web/lib/hooks/use-leads.ts`

Context: `LeadFilters` + `buildQuery` (lines 17-48) drive `useLeads`. Add the two new params so the pipeline page can pass them.

- [ ] **Step 1: Extend LeadFilters**

In `apps/web/lib/hooks/use-leads.ts`, add to the `LeadFilters` interface (after `form_id`):

```typescript
  // Manager workload: admin/head can scope the board to one manager
  // (assigned_to) or the whole workspace (all_assignees).
  assigned_to?: string;
  all_assignees?: boolean;
```

- [ ] **Step 2: Extend buildQuery**

In the same file, in `buildQuery`, add (before the `page` line):

```typescript
  if (filters.assigned_to) p.set("assigned_to", filters.assigned_to);
  if (filters.all_assignees) p.set("all_assignees", "true");
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/web && npm run typecheck`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/hooks/use-leads.ts
git commit -m "feat(pipeline): T3 — assigned_to / all_assignees params on useLeads"
```

---

## Task 4: Pipeline owner dropdown (admin/head)

**Files:**
- Modify: `apps/web/app/(app)/pipeline/page.tsx`
- (Read-only reference) `apps/web/lib/hooks/use-users.ts` for the workspace user list.

Context: the pipeline page already has `meQuery = useMe()` and calls `useLeads({ pipeline_id, q, page_size })` (~line 60). Add a dropdown (admin/head only) that selects the assignee scope and feeds `assigned_to` / `all_assignees` into `useLeads`. Use `useUsers()` (already used elsewhere, e.g. `DealAndAITab.tsx`) to list managers.

- [ ] **Step 1: Add owner-scope state + the dropdown**

In `apps/web/app/(app)/pipeline/page.tsx`:

1. Import `useUsers`:
   ```typescript
   import { useUsers } from "@/lib/hooks/use-users";
   ```
2. Inside the component, derive admin/head and add state:
   ```typescript
   const isPrivileged =
     meQuery.data?.role === "admin" || meQuery.data?.role === "head";
   const usersQuery = useUsers();
   // "" = Мои (self/default), "all" = Все, otherwise a user id
   const [ownerScope, setOwnerScope] = useState<string>("");
   ```
   (Add `useState` to the existing `react` import if not present.)
3. Translate `ownerScope` into the `useLeads` params and pass them into the existing `useLeads({...})` call:
   ```typescript
   const leadsQuery = useLeads({
     pipeline_id: activePipelineId ?? undefined,
     q: filters.q || undefined,
     assigned_to:
       isPrivileged && ownerScope && ownerScope !== "all" ? ownerScope : undefined,
     all_assignees: isPrivileged && ownerScope === "all" ? true : undefined,
     page_size: 200,
   });
   ```
4. Render the dropdown near the pipeline header (only when `isPrivileged`). Match the existing select/dropdown styling on the page (find an existing `<select>` or filter control and mirror its classes):
   ```tsx
   {isPrivileged && (
     <select
       value={ownerScope}
       onChange={(e) => setOwnerScope(e.target.value)}
       className="<match existing select classes on this page>"
     >
       <option value="">Мои</option>
       <option value="all">Все</option>
       {(usersQuery.data?.items ?? []).map((u) => (
         <option key={u.id} value={u.id}>
           {u.name || u.email}
         </option>
       ))}
     </select>
   )}
   ```
   `useUsers()` returns `UserListOut` whose `items[]` have `id`, `name`, `email` (confirmed in `lib/types.ts` — `UserOut.name: string`). Place the control where the page's other header filters live — read the JSX to find the filter row and match it.

- [ ] **Step 2: Deep-link support (read ?assigned_to= from URL)**

The `/team` workload table links to `/pipeline?assigned_to=<id>`. Initialize `ownerScope` from the query param so the link lands on that manager's board. The page already uses `useSearchParams` (it reads `stageParam`). Add:

```typescript
   const assignedParam = params?.get("assigned_to") ?? null;
   useEffect(() => {
     if (assignedParam && isPrivileged) setOwnerScope(assignedParam);
   }, [assignedParam, isPrivileged]);
```

Place this near the existing `stageParam` `useEffect`. Confirm the `useSearchParams` hook variable name on the page (likely `params`/`searchParams`) and match it.

- [ ] **Step 3: Typecheck + build**

Run: `cd apps/web && npm run typecheck && npm run lint`
Expected: typecheck 0 errors; lint at/below baseline.

Run: `cd apps/web && pnpm build`
Expected: succeeds (the page uses `useSearchParams` inside an existing Suspense boundary — do not break it; if the build complains about Suspense, the existing boundary should already cover it — verify your additions stay inside it).

- [ ] **Step 4: Commit**

```bash
git add "apps/web/app/(app)/pipeline/page.tsx"
git commit -m "feat(pipeline): T4 — owner-scope dropdown (Мои / менеджер / Все) for admin/head"
```

---

## Task 5: /team «Загрузка» tab + workload table

**Files:**
- Modify: `apps/web/lib/types.ts`
- Create: `apps/web/lib/hooks/use-team-workload.ts`
- Create: `apps/web/components/team/WorkloadTable.tsx`
- Modify: `apps/web/app/(app)/team/page.tsx`

Context: `/team` is admin/head-gated and renders `useTeamStats(period)`. Add a view toggle «Активность» (existing) ↔ «Загрузка» (new table). The table links rows to `/pipeline?assigned_to=<id>`.

- [ ] **Step 1: Types**

In `apps/web/lib/types.ts`, add:

```typescript
export interface WorkloadStage {
  id: string;
  name: string;
  position: number;
  color: string;
}

export interface WorkloadCell {
  count: number;
  sum_amount: number;
}

export interface WorkloadManager {
  user_id: string;
  name: string;
  email: string;
  by_stage: Record<string, WorkloadCell>;
  open_count: number;
  pipeline_sum: number;
  stuck_count: number;
}

export interface Workload {
  stages: WorkloadStage[];
  managers: WorkloadManager[];
}
```

- [ ] **Step 2: Hook**

Create `apps/web/lib/hooks/use-team-workload.ts`:

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Workload } from "@/lib/types";

/** GET /api/team/workload — manager × stage load. Admin/head only at the backend. */
export function useTeamWorkload() {
  return useQuery<Workload>({
    queryKey: ["team-workload"],
    queryFn: () => api.get<Workload>("/team/workload"),
    staleTime: 60_000,
  });
}
```

- [ ] **Step 3: WorkloadTable component**

Create `apps/web/components/team/WorkloadTable.tsx`:

```tsx
"use client";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { useTeamWorkload } from "@/lib/hooks/use-team-workload";

function fmtSum(n: number): string {
  if (!n) return "—";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " ₽";
}

export function WorkloadTable() {
  const { data, isLoading, isError } = useTeamWorkload();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }
  if (isError || !data) {
    return <div className="text-sm text-muted-2 py-10">Не удалось загрузить данные.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-black/5 bg-white">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-black/5 text-left text-xs text-muted-2">
            <th className="px-4 py-3 font-semibold sticky left-0 bg-white">Менеджер</th>
            {data.stages.map((s) => (
              <th key={s.id} className="px-3 py-3 font-semibold whitespace-nowrap">
                {s.name}
              </th>
            ))}
            <th className="px-3 py-3 font-semibold">Итого</th>
            <th className="px-3 py-3 font-semibold">Зависшие</th>
          </tr>
        </thead>
        <tbody>
          {data.managers.map((m) => (
            <tr key={m.user_id} className="border-b border-black/5 hover:bg-black/[0.02]">
              <td className="px-4 py-3 font-medium sticky left-0 bg-white">
                <Link
                  href={`/pipeline?assigned_to=${m.user_id}`}
                  className="hover:underline text-brand-accent-text"
                >
                  {m.name}
                </Link>
              </td>
              {data.stages.map((s) => {
                const cell = m.by_stage[s.id];
                return (
                  <td key={s.id} className="px-3 py-3 whitespace-nowrap">
                    {cell ? (
                      <>
                        <span className="font-semibold">{cell.count}</span>
                        <span className="text-xs text-muted-2 ml-1">
                          {fmtSum(cell.sum_amount)}
                        </span>
                      </>
                    ) : (
                      <span className="text-muted-3">—</span>
                    )}
                  </td>
                );
              })}
              <td className="px-3 py-3 whitespace-nowrap">
                <span className="font-semibold">{m.open_count}</span>
                <span className="text-xs text-muted-2 ml-1">{fmtSum(m.pipeline_sum)}</span>
              </td>
              <td className="px-3 py-3">
                {m.stuck_count > 0 ? (
                  <Link
                    href={`/pipeline?assigned_to=${m.user_id}`}
                    className="font-semibold text-warning hover:underline"
                  >
                    {m.stuck_count}
                  </Link>
                ) : (
                  <span className="text-muted-3">0</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

Verify the tokens `text-muted-2`, `text-muted-3`, `text-brand-accent-text`, `text-warning` exist (the `/team` page and `CostsSection` use these). If `text-warning` isn't a real token, use the codebase's amber/orange accent (grep `tailwind.config.ts` / existing components for the warning color) — match an existing usage.

- [ ] **Step 4: View toggle on /team**

In `apps/web/app/(app)/team/page.tsx`:

1. Import the table + add a view state:
   ```typescript
   import { WorkloadTable } from "@/components/team/WorkloadTable";
   ```
   ```typescript
   const [view, setView] = useState<"activity" | "workload">("activity");
   ```
2. Render a toggle near the existing period control (mirror the existing period-toggle markup on the page):
   ```tsx
   <div className="inline-flex rounded-xl bg-black/5 p-1">
     <button
       type="button"
       onClick={() => setView("activity")}
       className={"px-3 py-1.5 text-sm font-semibold rounded-lg transition-colors " +
         (view === "activity" ? "bg-white text-ink shadow-sm" : "text-muted-2")}
     >
       Активность
     </button>
     <button
       type="button"
       onClick={() => setView("workload")}
       className={"px-3 py-1.5 text-sm font-semibold rounded-lg transition-colors " +
         (view === "workload" ? "bg-white text-ink shadow-sm" : "text-muted-2")}
     >
       Загрузка
     </button>
   </div>
   ```
3. Gate the existing stats content behind `view === "activity"` and render `<WorkloadTable />` when `view === "workload"`. The period control is only meaningful for «Активность» — hide or disable it when `view === "workload"` (workload is "now", not period-based). Read the page to place this cleanly without disturbing the admin/head guard already at the top.

- [ ] **Step 5: Typecheck, lint, build**

Run: `cd apps/web && npm run typecheck && npm run lint`
Expected: typecheck 0 errors; lint at/below baseline.

Run: `cd apps/web && pnpm build`
Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/hooks/use-team-workload.ts apps/web/components/team/WorkloadTable.tsx "apps/web/app/(app)/team/page.tsx"
git commit -m "feat(team): T5 — «Загрузка» tab with manager × stage workload table"
```

---

## Final verification (after all tasks)

- [ ] **Backend slice:** `cd apps/api && .venv/bin/pytest tests/test_leads_assignee_scope.py tests/test_team_workload.py tests/test_webforms.py -q` → all pass.
- [ ] **Frontend:** `cd apps/web && npm run typecheck && pnpm build` → green.
- [ ] **Dispatch a final whole-branch code review**, then `superpowers:finishing-a-development-branch` to open the PR. Post-deploy smoke (needs admin): `/team` → «Загрузка» shows counts/sums/«Зависшие»; click a manager → their `/pipeline` board; pipeline dropdown «Мои/‹менеджер›/Все» switches the board; confirm a regular (non-admin) user cannot widen scope via `?assigned_to=`.

## Notes for the implementer

- **No DB migration** — the feature reads existing columns only.
- **Raw SQL in the team domain is the established pattern** (`text()` + dict params) — follow it; don't introduce ORM selects there.
- **`MagicMock(name=...)` footgun:** `name` is reserved by MagicMock; set `mock.name = ...` after construction in tests.
- **Role values** are `"admin"` / `"head"` / `"manager"` (others). The `_resolve_assignee_scope` privileged set is exactly `{"admin", "head"}`.
- Keep the `q` text-search carve-out untouched — it powers the message-to-lead picker.
