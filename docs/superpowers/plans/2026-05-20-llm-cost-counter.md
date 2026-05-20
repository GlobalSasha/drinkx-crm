# LLM Cost Counter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give admins a `Settings → Расходы` view of total + per-provider LLM spend, filterable by period (this month / last month / all time).

**Architecture:** A new `app/llm_usage/` domain owns a per-call cost ledger (`llm_usage` table). Every LLM call is recorded best-effort at the single chokepoint `complete_with_fallback`. One admin endpoint aggregates `GROUP BY provider` over a period. The redundant cost columns on `EnrichmentRun` are dropped (single source of truth). Frontend adds an admin-only settings section.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest (mock-stubbed sqlalchemy); Next.js 15 App Router, TanStack Query, Tailwind.

**Design spec:** `docs/superpowers/specs/2026-05-20-llm-cost-counter-design.md`

**Branch:** `docs/sprint-4-0-llm-cost-counter` (already checked out; rename or continue on it).

---

## File Structure

**Backend — new domain `apps/api/app/llm_usage/`:**
- `__init__.py` — empty package marker.
- `models.py` — `LlmUsage` ORM model.
- `service.py` — `record_llm_usage(...)` best-effort recorder + `PROVIDER_ORDER`.
- `repositories.py` — `insert_usage(...)`, `aggregate_by_provider(...)`, `period_bounds(...)`.
- `schemas.py` — `ProviderCostOut`, `LlmCostsOut`.
- `routers.py` — `GET /admin/llm-costs`.

**Backend — modified:**
- `apps/api/app/enrichment/providers/factory.py` — add `workspace_id` param + best-effort record call.
- `apps/api/app/enrichment/providers/base.py` — `complete()` Protocol gets no change (workspace_id lives only in the factory wrapper).
- `apps/api/app/enrichment/orchestrator.py` — pass `workspace_id`; remove cost-column writes.
- `apps/api/app/lead_agent/runner.py` — pass `workspace_id` (2 call sites).
- `apps/api/app/daily_plan/services.py` — pass `workspace_id`.
- `apps/api/app/inbox/message_tasks.py` — pass `workspace_id`.
- `apps/api/app/scheduled/jobs.py` — pass `workspace_id` (inbox suggestion call site).
- `apps/api/app/enrichment/models.py` — drop 3 cost columns from `EnrichmentRun`.
- `apps/api/app/enrichment/api_schemas.py` — drop 3 fields from `EnrichmentRunOut`.
- `apps/api/app/main.py` — register llm_usage router.
- `apps/api/app/scheduled/celery_app.py` — side-effect import of llm_usage models.
- `apps/api/alembic/versions/` — two migrations (create table; drop columns).

**Frontend — modified/created:**
- `apps/web/lib/hooks/use-llm-costs.ts` — new query hook.
- `apps/web/components/settings/CostsSection.tsx` — new section.
- `apps/web/app/(app)/settings/page.tsx` — register `costs` section.
- `apps/web/lib/types.ts` — `LlmCosts` types; drop 3 enrichment cost fields.

---

## Task 1: LlmUsage model + create-table migration

**Files:**
- Create: `apps/api/app/llm_usage/__init__.py`
- Create: `apps/api/app/llm_usage/models.py`
- Create: `apps/api/alembic/versions/20260520_0032_llm_usage_table.py`
- Modify: `apps/api/app/scheduled/celery_app.py` (add side-effect import)
- Test: `apps/api/tests/test_llm_usage_model.py`

- [ ] **Step 1: Create the package marker**

Create `apps/api/app/llm_usage/__init__.py` (empty file).

- [ ] **Step 2: Write the model**

Create `apps/api/app/llm_usage/models.py`:

```python
"""LlmUsage ORM model — one row per LLM call, the single cost ledger."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class LlmUsage(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "llm_usage"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0"), nullable=False
    )
```

`UUIDPrimaryKeyMixin` provides `id`; `TimestampedMixin` provides `created_at` / `updated_at`. Confirm both by reading `apps/api/app/common/models.py` before writing.

- [ ] **Step 3: Write the test (model importable + columns present)**

Create `apps/api/tests/test_llm_usage_model.py`:

```python
"""Sprint 4.0 — LlmUsage model shape."""
from __future__ import annotations

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_llm_usage_table_and_columns():
    from app.llm_usage.models import LlmUsage

    assert LlmUsage.__tablename__ == "llm_usage"
    cols = set(LlmUsage.__table__.columns.keys())
    assert {
        "id", "workspace_id", "task_type", "provider", "model",
        "prompt_tokens", "completion_tokens", "cost_usd", "created_at",
    } <= cols
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && .venv/bin/pytest tests/test_llm_usage_model.py -q`
Expected: PASS (1 passed). If `_stub_sqlalchemy` does not expose `__table__.columns`, fall back to asserting the attributes exist via `hasattr(LlmUsage, "cost_usd")` etc.

- [ ] **Step 5: Write the create-table migration**

First confirm the current head:

Run: `cd apps/api && .venv/bin/alembic heads`
Expected: `0031_lead_needs_review (head)`

Create `apps/api/alembic/versions/20260520_0032_llm_usage_table.py`:

```python
"""llm_usage table

Revision ID: 0032_llm_usage_table
Revises: 0031_lead_needs_review
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_llm_usage_table"
down_revision = "0031_lead_needs_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_llm_usage_workspace_created",
        "llm_usage",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_workspace_created", table_name="llm_usage")
    op.drop_table("llm_usage")
```

Match the exact `id`/timestamp column definitions used by other migrations in this repo (open `20260519_0031_lead_needs_review.py` and the table-creating migration for `enrichment_runs` to confirm `server_default` / timezone conventions). Adjust if they differ.

- [ ] **Step 6: Verify migration graph is linear**

Run: `cd apps/api && .venv/bin/alembic heads`
Expected: `0032_llm_usage_table (head)` — exactly one head. If two heads appear, the `down_revision` is wrong; fix it.

- [ ] **Step 7: Register model for the worker process**

In `apps/api/app/scheduled/celery_app.py`, add to the side-effect import block (after the other `app.X import models as _x` lines, ~line 31):

```python
from app.llm_usage import models as _llm_usage_models  # noqa: F401, E402
```

Rationale: the Celery worker records usage but never imports through `app.main`, so the mapper registry needs this model hydrated here (same reason as the other domains in that block).

- [ ] **Step 8: Compile-check + commit**

Run: `cd apps/api && .venv/bin/python -m py_compile app/llm_usage/models.py alembic/versions/20260520_0032_llm_usage_table.py app/scheduled/celery_app.py`
Expected: no output (success).

```bash
git add apps/api/app/llm_usage/__init__.py apps/api/app/llm_usage/models.py apps/api/alembic/versions/20260520_0032_llm_usage_table.py apps/api/app/scheduled/celery_app.py apps/api/tests/test_llm_usage_model.py
git commit -m "feat(llm-usage): G1 — LlmUsage model + table migration"
```

---

## Task 2: record_llm_usage best-effort service

**Files:**
- Create: `apps/api/app/llm_usage/service.py`
- Create: `apps/api/app/llm_usage/repositories.py` (insert half only; aggregate added in Task 3)
- Test: `apps/api/tests/test_record_llm_usage.py`

- [ ] **Step 1: Write the insert repository function**

Create `apps/api/app/llm_usage/repositories.py`:

```python
"""llm_usage persistence + aggregation."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.llm_usage.models import LlmUsage


def insert_usage(
    db,
    *,
    workspace_id: uuid.UUID,
    task_type: str,
    provider: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    """Stage a usage row on the caller's session — add() ONLY, no flush/commit.

    add() emits no SQL, so it cannot poison the caller's in-flight transaction
    and cannot commit the caller's other pending changes. The row persists when
    the caller commits its own transaction (every LLM call site commits right
    after the call). If the caller rolls back, the telemetry row is dropped too
    — acceptable for best-effort cost tracking.
    """
    db.add(
        LlmUsage(
            workspace_id=workspace_id,
            task_type=task_type,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    )
```

`insert_usage` is intentionally synchronous — `Session.add()` is a sync, no-SQL operation. Do NOT add `flush()`/`commit()`; either would emit SQL on the caller's session and risk interfering with its transaction (e.g. prematurely committing a half-built `EnrichmentRun`, or poisoning it on error). This is loop-safe inside Celery workers (no new engine/session bound to a foreign event loop).

- [ ] **Step 2: Write the best-effort service**

Create `apps/api/app/llm_usage/service.py`:

```python
"""record_llm_usage — best-effort cost telemetry.

Called from the LLM chokepoint (complete_with_fallback) on success.
MUST NOT raise into the LLM path: a telemetry/DB failure logs a warning
and is swallowed so enrichment / Блейк / daily plan still get their result.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog

from app.enrichment.providers.base import CompletionResult
from app.llm_usage.repositories import insert_usage

log = structlog.get_logger()

# Display order for providers in the admin counter (also drives zero-fill).
PROVIDER_ORDER = ["mimo", "anthropic", "gemini", "deepseek"]


async def record_llm_usage(
    db,
    *,
    workspace_id: uuid.UUID | None,
    task_type: str,
    result: CompletionResult,
) -> None:
    if db is None or workspace_id is None:
        log.warning("llm_usage.skip", provider=result.provider, task_type=task_type)
        return
    try:
        insert_usage(  # sync add-only; persists with the caller's transaction
            db,
            workspace_id=workspace_id,
            task_type=task_type,
            provider=result.provider,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cost_usd=Decimal(str(result.cost_usd)),
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break the LLM path
        log.warning("llm_usage.record_failed", error=str(exc), provider=result.provider)
```

`record_llm_usage` stays `async` (the chokepoint awaits it and a future implementation may need IO), but it neither flushes nor commits — it only stages the row via the sync `insert_usage`. No `rollback` is needed because no SQL is emitted here.

- [ ] **Step 3: Write the tests**

Create `apps/api/tests/test_record_llm_usage.py`:

```python
"""Sprint 4.0 — record_llm_usage best-effort behaviour."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def _result():
    from app.enrichment.providers.base import CompletionResult
    return CompletionResult(
        text="x", model="mimo-flash", provider="mimo",
        prompt_tokens=100, completion_tokens=50, cost_usd=0.0012,
    )


@pytest.mark.asyncio
async def test_record_llm_usage_stages_row_no_commit():
    from app.llm_usage import service

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    ws = uuid.uuid4()
    await service.record_llm_usage(
        db, workspace_id=ws, task_type="research_synthesis", result=_result()
    )

    db.add.assert_called_once()        # row staged on the caller's session
    db.commit.assert_not_called()      # MUST NOT commit the caller's transaction


@pytest.mark.asyncio
async def test_record_llm_usage_swallows_add_error():
    from app.llm_usage import service

    db = MagicMock()
    db.add = MagicMock(side_effect=RuntimeError("session poisoned"))

    # Must NOT raise — telemetry failure cannot break the LLM path.
    await service.record_llm_usage(
        db, workspace_id=uuid.uuid4(), task_type="sales_coach", result=_result()
    )


@pytest.mark.asyncio
async def test_record_llm_usage_no_workspace_is_noop():
    from app.llm_usage import service

    db = MagicMock()
    db.add = MagicMock()
    await service.record_llm_usage(
        db, workspace_id=None, task_type="prefilter", result=_result()
    )
    db.add.assert_not_called()
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && .venv/bin/pytest tests/test_record_llm_usage.py -q`
Expected: PASS (3 passed). If `_stub_sqlalchemy` lacks `AsyncSession`, the imports still work because the service annotates `db` untyped — verify import succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/llm_usage/service.py apps/api/app/llm_usage/repositories.py apps/api/tests/test_record_llm_usage.py
git commit -m "feat(llm-usage): G2 — best-effort record_llm_usage service"
```

---

## Task 3: Period bounds + aggregate-by-provider query

**Files:**
- Modify: `apps/api/app/llm_usage/repositories.py` (add `period_bounds` + `aggregate_by_provider`)
- Test: `apps/api/tests/test_llm_cost_aggregate.py`

- [ ] **Step 1: Write the period_bounds + aggregate functions**

Append to `apps/api/app/llm_usage/repositories.py`:

```python
import datetime as _dt
from typing import Literal

from sqlalchemy import func, select

Period = Literal["this_month", "last_month", "all"]


def period_bounds(
    period: Period, *, now: _dt.datetime | None = None
) -> tuple[_dt.datetime | None, _dt.datetime | None]:
    """Return [start, end) UTC bounds for a period. `all` → (None, None)."""
    now = now or _dt.datetime.now(tz=_dt.timezone.utc)
    if period == "all":
        return None, None
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "this_month":
        # next month start
        if month_start.month == 12:
            nxt = month_start.replace(year=month_start.year + 1, month=1)
        else:
            nxt = month_start.replace(month=month_start.month + 1)
        return month_start, nxt
    # last_month
    if month_start.month == 1:
        prev = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev = month_start.replace(month=month_start.month - 1)
    return prev, month_start


async def aggregate_by_provider(
    db,
    *,
    workspace_id,
    start: _dt.datetime | None,
    end: _dt.datetime | None,
) -> list[tuple[str, float, int]]:
    """Return [(provider, total_cost_usd, call_count), ...] for the window."""
    stmt = select(
        LlmUsage.provider,
        func.coalesce(func.sum(LlmUsage.cost_usd), 0),
        func.count(LlmUsage.id),
    ).where(LlmUsage.workspace_id == workspace_id)
    if start is not None:
        stmt = stmt.where(LlmUsage.created_at >= start)
    if end is not None:
        stmt = stmt.where(LlmUsage.created_at < end)
    stmt = stmt.group_by(LlmUsage.provider)

    res = await db.execute(stmt)
    return [(row[0], float(row[1]), int(row[2])) for row in res.all()]
```

- [ ] **Step 2: Write the tests**

Create `apps/api/tests/test_llm_cost_aggregate.py`:

```python
"""Sprint 4.0 — period bounds + provider aggregation."""
from __future__ import annotations

import datetime as _dt
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_period_bounds_this_month():
    from app.llm_usage.repositories import period_bounds

    now = _dt.datetime(2026, 5, 20, 9, 0, tzinfo=_dt.timezone.utc)
    start, end = period_bounds("this_month", now=now)
    assert start == _dt.datetime(2026, 5, 1, tzinfo=_dt.timezone.utc)
    assert end == _dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc)


def test_period_bounds_last_month_january_wraps():
    from app.llm_usage.repositories import period_bounds

    now = _dt.datetime(2026, 1, 10, tzinfo=_dt.timezone.utc)
    start, end = period_bounds("last_month", now=now)
    assert start == _dt.datetime(2025, 12, 1, tzinfo=_dt.timezone.utc)
    assert end == _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)


def test_period_bounds_all_is_unbounded():
    from app.llm_usage.repositories import period_bounds

    assert period_bounds("all") == (None, None)


@pytest.mark.asyncio
async def test_aggregate_by_provider_maps_rows():
    from app.llm_usage import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=lambda: [("mimo", 40.2, 980), ("anthropic", 5.1, 42)])
    )
    rows = await repo.aggregate_by_provider(
        db, workspace_id=uuid.uuid4(), start=None, end=None
    )
    assert rows == [("mimo", 40.2, 980), ("anthropic", 5.1, 42)]
    db.execute.assert_awaited_once()
```

- [ ] **Step 3: Run tests**

Run: `cd apps/api && .venv/bin/pytest tests/test_llm_cost_aggregate.py -q`
Expected: PASS (4 passed).

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/llm_usage/repositories.py apps/api/tests/test_llm_cost_aggregate.py
git commit -m "feat(llm-usage): G3 — period bounds + aggregate-by-provider query"
```

---

## Task 4: Schemas + admin endpoint

**Files:**
- Create: `apps/api/app/llm_usage/schemas.py`
- Create: `apps/api/app/llm_usage/routers.py`
- Modify: `apps/api/app/main.py` (register router)
- Test: `apps/api/tests/test_llm_costs_endpoint.py`

- [ ] **Step 1: Write the schemas**

Create `apps/api/app/llm_usage/schemas.py`:

```python
"""llm_usage API schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ProviderCostOut(BaseModel):
    provider: str
    cost_usd: float
    calls: int


class LlmCostsOut(BaseModel):
    period: str
    total_usd: float
    by_provider: list[ProviderCostOut]
```

- [ ] **Step 2: Write a service helper that zero-fills + totals**

Append to `apps/api/app/llm_usage/service.py`:

```python
from app.llm_usage.repositories import Period, aggregate_by_provider, period_bounds
from app.llm_usage.schemas import LlmCostsOut, ProviderCostOut


async def get_costs(db, *, workspace_id, period: Period) -> LlmCostsOut:
    start, end = period_bounds(period)
    rows = await aggregate_by_provider(db, workspace_id=workspace_id, start=start, end=end)
    found = {provider: (cost, calls) for provider, cost, calls in rows}
    by_provider = [
        ProviderCostOut(
            provider=p,
            cost_usd=round(found.get(p, (0.0, 0))[0], 6),
            calls=found.get(p, (0.0, 0))[1],
        )
        for p in PROVIDER_ORDER
    ]
    # Include any provider seen in data but not in PROVIDER_ORDER (defensive).
    for p, (cost, calls) in found.items():
        if p not in PROVIDER_ORDER:
            by_provider.append(ProviderCostOut(provider=p, cost_usd=round(cost, 6), calls=calls))
    total = round(sum(c.cost_usd for c in by_provider), 6)
    return LlmCostsOut(period=period, total_usd=total, by_provider=by_provider)
```

Note: this introduces a module-level import of `app.llm_usage.schemas` and `repositories` into `service.py`. Move the existing top-of-file imports together; `service.py` already imports `repositories.insert_usage`, so consolidate to one import line.

- [ ] **Step 3: Write the router**

Create `apps/api/app/llm_usage/routers.py`:

```python
"""Admin LLM cost counter — read-only."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.models import User
from app.db import get_db
from app.llm_usage.schemas import LlmCostsOut
from app.llm_usage.service import get_costs

router = APIRouter(prefix="/admin/llm-costs", tags=["admin"])


@router.get("", response_model=LlmCostsOut)
async def llm_costs(
    period: Literal["this_month", "last_month", "all"] = "this_month",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> LlmCostsOut:
    """Admin-only. Scoped to the caller's workspace (not user-supplied)."""
    return await get_costs(db, workspace_id=user.workspace_id, period=period)
```

Confirm `require_admin` is importable from `app.auth.dependencies` (it is used by `app/audit/routers.py`).

- [ ] **Step 4: Register the router in main**

In `apps/api/app/main.py`, after the audit router registration (~line 125), add:

```python
    from app.llm_usage.routers import router as llm_costs_router
    app.include_router(llm_costs_router)
```

- [ ] **Step 5: Write the endpoint logic test**

Create `apps/api/tests/test_llm_costs_endpoint.py`:

```python
"""Sprint 4.0 — get_costs zero-fills providers and totals."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_get_costs_zero_fills_and_totals():
    from app.llm_usage import service

    with patch.object(
        service, "aggregate_by_provider",
        new=AsyncMock(return_value=[("mimo", 40.2, 980), ("anthropic", 5.1, 42)]),
    ):
        out = await service.get_costs(object(), workspace_id=uuid.uuid4(), period="all")

    providers = {p.provider: p for p in out.by_provider}
    assert providers["mimo"].cost_usd == 40.2
    assert providers["gemini"].cost_usd == 0.0  # zero-filled
    assert providers["deepseek"].calls == 0
    assert out.total_usd == round(40.2 + 5.1, 6)
    assert out.period == "all"
```

- [ ] **Step 6: Run tests + collection check**

Run: `cd apps/api && .venv/bin/pytest tests/test_llm_costs_endpoint.py -q && .venv/bin/python -m py_compile app/llm_usage/routers.py app/main.py`
Expected: PASS (1 passed), no compile output.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/llm_usage/schemas.py apps/api/app/llm_usage/routers.py apps/api/app/llm_usage/service.py apps/api/app/main.py apps/api/tests/test_llm_costs_endpoint.py
git commit -m "feat(llm-usage): G4 — admin GET /admin/llm-costs endpoint"
```

---

## Task 5: Wire recording into the chokepoint + all call sites

**Files:**
- Modify: `apps/api/app/enrichment/providers/factory.py`
- Modify: `apps/api/app/enrichment/orchestrator.py` (2 call sites)
- Modify: `apps/api/app/lead_agent/runner.py` (2 call sites)
- Modify: `apps/api/app/daily_plan/services.py` (1 call site)
- Modify: `apps/api/app/inbox/message_tasks.py` (1 call site)
- Modify: `apps/api/app/scheduled/jobs.py` (1 call site)
- Test: `apps/api/tests/test_factory_records_usage.py`

- [ ] **Step 1: Add workspace_id + db params and recording to the factory**

In `apps/api/app/enrichment/providers/factory.py`, change the `complete_with_fallback` signature and add a record call on success.

Add params (keep all existing params):

```python
async def complete_with_fallback(
    *,
    system: str,
    user: str,
    task_type: TaskType,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_seconds: float = 30.0,
    chain: list[str] | None = None,
    db=None,
    workspace_id=None,
) -> CompletionResult:
```

Inside the success branch, immediately before `return result` (currently ~line 82), insert:

```python
            if db is not None and workspace_id is not None:
                # Lazy import avoids a providers↔llm_usage circular import.
                from app.llm_usage.service import record_llm_usage

                await record_llm_usage(
                    db, workspace_id=workspace_id, task_type=task_type.value, result=result
                )
            return result
```

Recording is gated on both `db` and `workspace_id` being supplied so call sites that cannot supply a session degrade to "no telemetry" rather than crashing — consistent with best-effort.

- [ ] **Step 2: Write the factory test**

Create `apps/api/tests/test_factory_records_usage.py`:

```python
"""Sprint 4.0 — complete_with_fallback records usage on success."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_factory_records_usage_on_success():
    from app.enrichment.providers import factory
    from app.enrichment.providers.base import CompletionResult, TaskType

    result = CompletionResult(
        text="ok", model="mimo-flash", provider="mimo",
        prompt_tokens=10, completion_tokens=5, cost_usd=0.0003,
    )
    fake_provider = MagicMock()
    fake_provider.complete = AsyncMock(return_value=result)

    db = MagicMock()
    ws = uuid.uuid4()

    with patch.object(factory, "get_llm_provider", return_value=fake_provider):
        with patch("app.llm_usage.service.record_llm_usage", new=AsyncMock()) as rec:
            out = await factory.complete_with_fallback(
                system="s", user="u", task_type=TaskType.research_synthesis,
                chain=["mimo"], db=db, workspace_id=ws,
            )

    assert out is result
    rec.assert_awaited_once()
    _, kwargs = rec.call_args
    assert kwargs["workspace_id"] == ws
    assert kwargs["task_type"] == "research_synthesis"


@pytest.mark.asyncio
async def test_factory_skips_recording_without_db():
    from app.enrichment.providers import factory
    from app.enrichment.providers.base import CompletionResult, TaskType

    result = CompletionResult(text="ok", model="m", provider="mimo")
    fake_provider = MagicMock()
    fake_provider.complete = AsyncMock(return_value=result)

    with patch.object(factory, "get_llm_provider", return_value=fake_provider):
        with patch("app.llm_usage.service.record_llm_usage", new=AsyncMock()) as rec:
            await factory.complete_with_fallback(
                system="s", user="u", task_type=TaskType.prefilter, chain=["mimo"],
            )
    rec.assert_not_awaited()
```

- [ ] **Step 3: Run the factory test**

Run: `cd apps/api && .venv/bin/pytest tests/test_factory_records_usage.py -q`
Expected: PASS (2 passed).

- [ ] **Step 4: Pass db + workspace_id at the enrichment orchestrator call sites**

In `apps/api/app/enrichment/orchestrator.py`, both `complete_with_fallback(...)` calls (~line 390 contact extraction, ~line 748 synthesis). The orchestrator already has the DB session (it writes `run`) and the `lead`. Add to each call:

```python
            db=db,
            workspace_id=lead.workspace_id,
```

Confirm the local variable names by reading the enclosing function: the session is the same one used to mutate `run` (search upward for `async def` and the session parameter name — likely `db`), and `lead.workspace_id` is already referenced elsewhere (e.g. `add_to_daily_spend(lead.workspace_id, ...)` at line 873).

- [ ] **Step 5: Pass db + workspace_id at the lead_agent runner call sites**

In `apps/api/app/lead_agent/runner.py`, both `complete_with_fallback(...)` calls (~line 83, ~line 170). Read each enclosing function signature for the session variable and the `lead`. Add:

```python
            db=db,
            workspace_id=lead.workspace_id,
```

If a function does not receive a session, pass only what is available; if neither `db` nor a workspace is in scope, leave that call site unwired (recording is optional) and note it in the commit message. Do NOT fabricate a session.

- [ ] **Step 6: Pass db + workspace_id at the daily_plan call site**

In `apps/api/app/daily_plan/services.py` (~line 245), inside the per-lead loop. `lead = scored_item.lead` is in scope. Add:

```python
                    db=db,
                    workspace_id=lead.workspace_id,
```

Confirm the session variable name in the enclosing function (search upward for `async def ... db`).

- [ ] **Step 7: Pass db + workspace_id at the inbox call sites**

In `apps/api/app/inbox/message_tasks.py` (~line 139) and `apps/api/app/scheduled/jobs.py` (~line 287). Read each function for the session + the workspace source (an inbox message / email account row carries `workspace_id`). Add `db=<session>, workspace_id=<workspace>` where both are in scope. If the workspace is not readily in scope at one of these sites, leave it unwired and note it — the prefilter cost is tiny and best-effort.

- [ ] **Step 8: Compile-check all touched call sites**

Run: `cd apps/api && .venv/bin/python -m py_compile app/enrichment/providers/factory.py app/enrichment/orchestrator.py app/lead_agent/runner.py app/daily_plan/services.py app/inbox/message_tasks.py app/scheduled/jobs.py`
Expected: no output.

- [ ] **Step 9: Run the broad backend slice to catch regressions**

Run: `cd apps/api && .venv/bin/pytest tests/test_factory_records_usage.py tests/test_record_llm_usage.py tests/test_llm_cost_aggregate.py tests/test_llm_costs_endpoint.py tests/test_webforms.py -q`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add apps/api/app/enrichment/providers/factory.py apps/api/app/enrichment/orchestrator.py apps/api/app/lead_agent/runner.py apps/api/app/daily_plan/services.py apps/api/app/inbox/message_tasks.py apps/api/app/scheduled/jobs.py apps/api/tests/test_factory_records_usage.py
git commit -m "feat(llm-usage): G5 — record every LLM call at the chokepoint"
```

---

## Task 6: Drop redundant cost columns from EnrichmentRun

**Files:**
- Modify: `apps/api/app/enrichment/orchestrator.py` (remove 3 writes)
- Modify: `apps/api/app/enrichment/models.py` (remove 3 columns)
- Modify: `apps/api/app/enrichment/api_schemas.py` (remove 3 fields)
- Modify: `apps/web/lib/types.ts` (remove 3 fields)
- Create: `apps/api/alembic/versions/20260520_0033_drop_enrichment_cost_cols.py`

- [ ] **Step 1: Remove the cost writes in the orchestrator**

In `apps/api/app/enrichment/orchestrator.py`, delete these three lines (currently ~809–811):

```python
        run.prompt_tokens = completion.prompt_tokens
        run.completion_tokens = completion.completion_tokens
        run.cost_usd = Decimal(str(round(completion.cost_usd, 4)))
```

Keep `run.provider = completion.provider` and `run.model = completion.model`. If `Decimal` becomes an unused import after this, remove the `from decimal import Decimal` import too (check first — it may be used elsewhere in the file).

- [ ] **Step 2: Remove the columns from the model**

In `apps/api/app/enrichment/models.py`, delete the three column definitions:

```python
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"), nullable=False)
```

If `Numeric`, `Integer`, or `Decimal` imports become unused, remove them (check the rest of the file first).

- [ ] **Step 3: Remove the fields from the API schema**

In `apps/api/app/enrichment/api_schemas.py`, delete from `EnrichmentRunOut` (lines 19–21):

```python
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
```

Remove the `Decimal` import if now unused.

- [ ] **Step 4: Remove the fields from the frontend type**

In `apps/web/lib/types.ts`, delete (lines 438–440):

```typescript
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number; // Decimal serialized as string by pydantic; coerce on read
```

Then grep the web app to ensure nothing reads them:

Run: `cd apps/web && grep -rn "prompt_tokens\|completion_tokens\|\.cost_usd" lib components app | grep -iv "llm" || echo "no remaining references"`
Expected: `no remaining references` (the Lead Card uses only `run.provider`).

- [ ] **Step 5: Write the drop-columns migration**

Create `apps/api/alembic/versions/20260520_0033_drop_enrichment_cost_cols.py`:

```python
"""drop redundant cost columns from enrichment_runs

Revision ID: 0033_drop_enrichment_cost_cols
Revises: 0032_llm_usage_table
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_drop_enrichment_cost_cols"
down_revision = "0032_llm_usage_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("enrichment_runs", "prompt_tokens")
    op.drop_column("enrichment_runs", "completion_tokens")
    op.drop_column("enrichment_runs", "cost_usd")


def downgrade() -> None:
    op.add_column("enrichment_runs",
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=False, server_default="0"))
    op.add_column("enrichment_runs",
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("enrichment_runs",
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"))
```

- [ ] **Step 6: Verify single head + compile**

Run: `cd apps/api && .venv/bin/alembic heads`
Expected: `0033_drop_enrichment_cost_cols (head)` — one head.

Run: `cd apps/api && .venv/bin/python -m py_compile app/enrichment/orchestrator.py app/enrichment/models.py app/enrichment/api_schemas.py alembic/versions/20260520_0033_drop_enrichment_cost_cols.py`
Expected: no output.

- [ ] **Step 7: Run the enrichment-related test slice**

Run: `cd apps/api && .venv/bin/pytest tests/ -q -k "enrichment or webforms or llm" `
Expected: PASS (no test asserts on the removed fields; if one does, update it to drop those assertions).

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/enrichment/orchestrator.py apps/api/app/enrichment/models.py apps/api/app/enrichment/api_schemas.py apps/web/lib/types.ts apps/api/alembic/versions/20260520_0033_drop_enrichment_cost_cols.py
git commit -m "refactor(enrichment): G6 — drop redundant cost columns (llm_usage is source of truth)"
```

---

## Task 7: Frontend — Settings → Расходы section

**Files:**
- Create: `apps/web/lib/hooks/use-llm-costs.ts`
- Create: `apps/web/components/settings/CostsSection.tsx`
- Modify: `apps/web/lib/types.ts` (add LlmCosts types)
- Modify: `apps/web/app/(app)/settings/page.tsx` (register section)

- [ ] **Step 1: Add the response types**

In `apps/web/lib/types.ts`, add:

```typescript
export interface ProviderCost {
  provider: string;
  cost_usd: number;
  calls: number;
}

export interface LlmCosts {
  period: "this_month" | "last_month" | "all";
  total_usd: number;
  by_provider: ProviderCost[];
}
```

- [ ] **Step 2: Write the query hook**

Create `apps/web/lib/hooks/use-llm-costs.ts`:

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { LlmCosts } from "@/lib/types";

export type CostPeriod = "this_month" | "last_month" | "all";

export function useLlmCosts(period: CostPeriod) {
  return useQuery({
    queryKey: ["llm-costs", period],
    queryFn: () => api.get<LlmCosts>(`/admin/llm-costs?period=${period}`),
    staleTime: 60_000,
  });
}
```

- [ ] **Step 3: Write the section component**

Create `apps/web/components/settings/CostsSection.tsx`:

```tsx
"use client";
// CostsSection — Sprint 4.0. Admin-only LLM spend counter.
import { useState } from "react";
import { Coins, Loader2, ShieldAlert } from "lucide-react";

import { useMe } from "@/lib/hooks/use-me";
import { useLlmCosts, type CostPeriod } from "@/lib/hooks/use-llm-costs";

const PROVIDER_LABELS: Record<string, string> = {
  mimo: "MiMo",
  anthropic: "Anthropic Claude",
  gemini: "Google Gemini",
  deepseek: "DeepSeek",
};

const PERIODS: { key: CostPeriod; label: string }[] = [
  { key: "this_month", label: "Этот месяц" },
  { key: "last_month", label: "Прошлый месяц" },
  { key: "all", label: "Всё время" },
];

function fmt(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

export function CostsSection() {
  const { data: me } = useMe();
  const [period, setPeriod] = useState<CostPeriod>("this_month");
  const { data, isLoading } = useLlmCosts(period);

  if (me && me.role !== "admin") {
    return (
      <div className="flex items-center gap-2 text-muted">
        <ShieldAlert size={16} /> Раздел доступен только администратору.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Coins size={18} className="text-brand-accent" />
        <h2 className="text-lg font-bold">Расходы на AI</h2>
      </div>

      {/* Period toggle */}
      <div className="inline-flex rounded-xl bg-black/5 p-1">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => setPeriod(p.key)}
            className={
              "px-3 py-1.5 text-sm font-semibold rounded-lg transition-colors " +
              (period === p.key ? "bg-white text-ink shadow-sm" : "text-muted")
            }
          >
            {p.label}
          </button>
        ))}
      </div>

      {isLoading || !data ? (
        <div className="flex items-center gap-2 text-muted">
          <Loader2 size={16} className="animate-spin" /> Загрузка…
        </div>
      ) : (
        <>
          <div>
            <div className="text-sm text-muted">Всего на AI</div>
            <div className="text-3xl font-bold tracking-tight">{fmt(data.total_usd)}</div>
          </div>

          <ul className="divide-y divide-black/5 rounded-2xl border border-brand-border">
            {data.by_provider.map((p) => (
              <li
                key={p.provider}
                className={
                  "flex items-center justify-between px-4 py-3 " +
                  (p.cost_usd === 0 ? "text-muted" : "")
                }
              >
                <span className="font-semibold">
                  {PROVIDER_LABELS[p.provider] ?? p.provider}
                </span>
                <span className="flex items-center gap-3">
                  <span className="text-sm text-muted">{p.calls} выз.</span>
                  <span className="font-mono">{fmt(p.cost_usd)}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
```

Confirm the `me.role` field name and the `text-muted` / `border-brand-border` / `bg-brand-accent` tokens exist by reading `apps/web/components/settings/AISection.tsx` (it uses the same gating + tokens). Adjust class names to match.

- [ ] **Step 4: Register the section in the settings page**

In `apps/web/app/(app)/settings/page.tsx`:

1. Add to the `SectionKey` union: `| "costs"`.
2. Import the icon and component at the top:
   ```tsx
   import { Coins } from "lucide-react"; // add to the existing lucide-react import group
   import { CostsSection } from "@/components/settings/CostsSection";
   ```
3. Add to the `SECTIONS` array (after `"ai"`):
   ```tsx
   { key: "costs", label: "Расходы", icon: <Coins size={15} />, ready: true },
   ```
4. Add to the render switch (after the `ai` line ~199):
   ```tsx
   {active === "costs" && <CostsSection />}
   ```

- [ ] **Step 5: Typecheck, lint, build**

Run: `cd apps/web && npm run typecheck && npm run lint`
Expected: typecheck clean; lint at or below the existing baseline (~21 warnings, 0 errors).

Run: `cd apps/web && pnpm build`
Expected: build succeeds (a new settings section touches App-Router rendering, so the full build per the repo's pre-PR checklist is mandatory).

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/hooks/use-llm-costs.ts apps/web/components/settings/CostsSection.tsx apps/web/lib/types.ts "apps/web/app/(app)/settings/page.tsx"
git commit -m "feat(settings): G7 — admin Расходы (LLM cost) section"
```

---

## Final verification (after all tasks)

- [ ] **Backend test slice green:**

Run: `cd apps/api && .venv/bin/pytest tests/test_llm_usage_model.py tests/test_record_llm_usage.py tests/test_llm_cost_aggregate.py tests/test_llm_costs_endpoint.py tests/test_factory_records_usage.py tests/test_webforms.py -q`
Expected: all PASS.

- [ ] **Migration graph linear, single head:**

Run: `cd apps/api && .venv/bin/alembic heads`
Expected: `0033_drop_enrichment_cost_cols (head)` — exactly one head.

- [ ] **Frontend build green:** `cd apps/web && pnpm build` succeeds.

- [ ] **Dispatch a final code-reviewer** over the whole branch, then use `superpowers:finishing-a-development-branch` to open the PR (mirror the gate-by-gate recap format of Sprint 3.6/3.7/3.9 PRs). Post-deploy smoke (needs prod auth — leave for the user): log in as admin → Settings → Расходы → toggle periods; trigger one enrichment and confirm a new `llm_usage` row + the figure increments.

---

## Notes for the implementer

- **Migration revision ids are slug-style, not timestamp-prefixed.** A timestamp-prefixed `revision=` crash-looped the API in Sprint 3.7. Always `grep "^revision =" ` the latest existing migration and run `alembic heads` before committing a migration.
- **Recording is best-effort and transaction-neutral by design.** `record_llm_usage` stages the row with `db.add()` only — no `flush`/`commit`/`rollback` — so it never commits the caller's half-built changes (e.g. an in-progress `EnrichmentRun`) and never poisons the caller's transaction. The `try/except` is load-bearing — do not "clean it up" into a narrower except, and do not add a `flush()`/`commit()` "to make sure it saves". The row persists when the caller commits.
- **Do not open an independent DB session for recording.** LLM calls run inside Celery tasks that build their own per-invocation engine bound to the task's event loop; a new session from the global engine could fail with cross-event-loop errors. Reuse the caller's session (add-only).
- **Do not re-add a pricing table.** `CompletionResult.cost_usd` is authoritative; providers compute it.
- **If a call site has no session/workspace in scope,** leave it unwired rather than fabricating a session, and call it out in the commit message. Prefilter/inbox costs are negligible.
```
