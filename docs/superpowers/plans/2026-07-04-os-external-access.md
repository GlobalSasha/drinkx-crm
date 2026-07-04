# OS External Read-Only Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a read-only REST surface (`/external/v1/*`) and a remote MCP server (`/mcp`) so the external "OS DrinkX" system (code + LLM agents) can read CRM core data with a machine key.

**Architecture:** A new self-contained domain package `apps/api/app/external/` holds GET-only routers, its own Pydantic whitelist schemas, and read queries. Authentication is a machine API key (sha256-hashed in a new `service_api_keys` table), resolved by a dedicated dependency that scopes every query to the key's workspace. The MCP server is the official Python SDK mounted as an ASGI sub-app on the same FastAPI instance, wrapping the same service functions.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, the `mcp` Python SDK (new dependency), pytest (Postgres-gated).

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-07-04-os-external-access-design.md`. Every decision below traces to it.
- Python 3.12+, async-first. Package-per-domain layout (`models.py`, `schemas.py`, `repositories.py`, `services.py`, `routers.py`).
- **Read-only:** the `external` package contains ZERO non-GET routes. This is an enforced invariant (Task 5 test).
- All dates in responses are ISO 8601 UTC (Pydantic serializes `datetime(tzinfo=utc)` as such — models already store `DateTime(timezone=True)`).
- Every query is scoped to the key's `workspace_id`. No cross-workspace reads.
- Whitelist serialization only — never dump ORM models. Fields listed in spec §5.
- nginx strips `/api/`: internal router prefix `/external/v1` is reachable externally at `https://crm.drinkx.tech/api/external/v1/...`; `/mcp` → `https://crm.drinkx.tech/api/mcp`.
- Alembic head is `0053_automation_step_attempt_count`. New migration chains from it.
- Tests that hit the DB are gated behind `POSTGRES_AVAILABLE` from `tests/conftest.py`, mirroring existing suites.
- Match existing style: `from __future__ import annotations`, `structlog.get_logger()`, `Annotated[..., Depends(...)]`, `Annotated[str | None, Header()]`.
- Commit after each task. Do NOT push (push to `main` triggers a ~20-min prod deploy) — the human pushes when ready.

---

## File Structure

- `apps/api/alembic/versions/20260704_0054_service_api_keys.py` — migration (create table).
- `apps/api/app/external/__init__.py` — package marker.
- `apps/api/app/external/models.py` — `ServiceApiKey` ORM model.
- `apps/api/app/external/keys.py` — key generation + hashing helpers (pure, no DB).
- `apps/api/app/external/dependencies.py` — `require_service_key` auth dependency + in-memory rate limiter.
- `apps/api/app/external/schemas.py` — Pydantic response whitelist schemas.
- `apps/api/app/external/repositories.py` — read queries (workspace-scoped).
- `apps/api/app/external/services.py` — orchestration + summary assembly; called by both REST and MCP.
- `apps/api/app/external/routers.py` — GET-only `/external/v1/*` routes.
- `apps/api/app/external/mcp_server.py` — MCP server definition (4 tools) + ASGI app.
- `apps/api/scripts/issue_service_key.py` — CLI to mint/revoke keys.
- `apps/api/app/main.py` — modify: include external router, mount MCP.
- `apps/api/pyproject.toml` — modify: add `mcp` dependency.
- Tests: `apps/api/tests/test_external_keys.py`, `test_external_auth.py`, `test_external_read.py`, `test_external_routes_readonly.py`, `test_external_mcp.py`.
- `docs/external-api/README.md` — consumer-facing doc for the OS side.

---

## Task 1: Key hashing helpers + `ServiceApiKey` model + migration

**Files:**
- Create: `apps/api/app/external/__init__.py` (empty)
- Create: `apps/api/app/external/keys.py`
- Create: `apps/api/app/external/models.py`
- Create: `apps/api/alembic/versions/20260704_0054_service_api_keys.py`
- Test: `apps/api/tests/test_external_keys.py`

**Interfaces:**
- Produces:
  - `keys.generate_key() -> tuple[str, str]` returns `(full_token, key_hash)` where `full_token` starts with `drinkx_os_` and `key_hash = sha256(full_token).hexdigest()`.
  - `keys.hash_key(token: str) -> str` returns the sha256 hex of a token.
  - `keys.verify(token: str, key_hash: str) -> bool` constant-time compare via `hmac.compare_digest`.
  - `models.ServiceApiKey` with columns `id, workspace_id, name, key_hash, scopes (list[str]), created_at, last_used_at, revoked_at`.

- [ ] **Step 1: Write the failing test for key helpers**

Create `apps/api/tests/test_external_keys.py`:

```python
"""Pure-function tests for external API key helpers (no DB)."""
from __future__ import annotations

from app.external import keys


def test_generate_key_prefix_and_hash():
    token, key_hash = keys.generate_key()
    assert token.startswith("drinkx_os_")
    assert len(token) > len("drinkx_os_") + 30  # >=32 random chars
    assert keys.hash_key(token) == key_hash
    assert len(key_hash) == 64  # sha256 hex


def test_verify_constant_time_true_and_false():
    token, key_hash = keys.generate_key()
    assert keys.verify(token, key_hash) is True
    assert keys.verify("drinkx_os_wrong", key_hash) is False


def test_two_keys_differ():
    t1, h1 = keys.generate_key()
    t2, h2 = keys.generate_key()
    assert t1 != t2 and h1 != h2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_external_keys.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.external'`.

- [ ] **Step 3: Create the package marker and key helpers**

Create `apps/api/app/external/__init__.py` (empty file).

Create `apps/api/app/external/keys.py`:

```python
"""Machine API key generation + hashing for external OS access.

Pure functions, no DB. The full token is shown once at creation;
only its sha256 hash is stored (see ServiceApiKey.key_hash).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_PREFIX = "drinkx_os_"


def hash_key(token: str) -> str:
    """sha256 hex of the full token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str]:
    """Return (full_token, key_hash). Store only the hash."""
    token = _PREFIX + secrets.token_urlsafe(32)
    return token, hash_key(token)


def verify(token: str, key_hash: str) -> bool:
    """Constant-time compare of a presented token against a stored hash."""
    return hmac.compare_digest(hash_key(token), key_hash)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_external_keys.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Create the `ServiceApiKey` model**

Create `apps/api/app/external/models.py`:

```python
"""ServiceApiKey — machine credential for external OS read access."""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class ServiceApiKey(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    """A hashed machine key scoped to one workspace.

    The full token is `drinkx_os_<random>`; only its sha256 hash lives
    here. `scopes` is a JSON list (v1: `["read:core"]`). A revoked key
    has `revoked_at` set and is rejected by `require_service_key`.
    """

    __tablename__ = "service_api_keys"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

> Note: confirm the workspaces table name is `workspaces` — check `app/auth/models.py:Workspace.__tablename__`. If it differs, use the real name (mirror migration 0029's note about `stages`).

- [ ] **Step 6: Create the Alembic migration**

Create `apps/api/alembic/versions/20260704_0054_service_api_keys.py`:

```python
"""service_api_keys table — machine keys for external OS read access.

Revision ID: 0054_service_api_keys
Revises: 0053_automation_step_attempt_count
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_service_api_keys"
down_revision: Union[str, None] = "0053_automation_step_attempt_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_service_api_keys_key_hash", "service_api_keys", ["key_hash"], unique=True)
    op.create_index("ix_service_api_keys_workspace_id", "service_api_keys", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_service_api_keys_key_hash", table_name="service_api_keys")
    op.drop_index("ix_service_api_keys_workspace_id", table_name="service_api_keys")
    op.drop_table("service_api_keys")
```

> Match `TimestampedMixin` column types: confirm it defines `created_at`/`updated_at` as `DateTime(timezone=True)`. If the mixin already covers them and the model omits them, keep them in the migration (the DB table still needs the columns).

- [ ] **Step 7: Verify model imports and migration is syntactically valid**

Run: `cd apps/api && python -m py_compile app/external/models.py app/external/keys.py alembic/versions/20260704_0054_service_api_keys.py`
Expected: no output (success).

Run: `cd apps/api && python -c "from app.external.models import ServiceApiKey; print(ServiceApiKey.__tablename__)"`
Expected: `service_api_keys`.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/external/__init__.py apps/api/app/external/keys.py apps/api/app/external/models.py apps/api/alembic/versions/20260704_0054_service_api_keys.py apps/api/tests/test_external_keys.py
git commit -m "feat(external): ServiceApiKey model, key hashing, migration 0054"
```

---

## Task 2: `require_service_key` auth dependency + rate limiter

**Files:**
- Create: `apps/api/app/external/dependencies.py`
- Test: `apps/api/tests/test_external_auth.py`

**Interfaces:**
- Consumes: `keys.hash_key`, `models.ServiceApiKey`, `app.db.get_db`.
- Produces:
  - `ServiceContext` dataclass: `.workspace_id: uuid.UUID`, `.key_id: uuid.UUID`, `.scopes: list[str]`.
  - `require_service_key(scope: str = "read:core")` — returns a FastAPI dependency callable yielding `ServiceContext`. Raises `401` (missing/invalid token), `403` (revoked or missing scope), `429` (rate limit).
  - `resolve_service_key(session, token, *, scope) -> ServiceContext` — the DB-backed resolver (unit-testable without HTTP).

- [ ] **Step 1: Write the failing test (DB-backed, PG-gated)**

Create `apps/api/tests/test_external_auth.py`:

```python
"""External machine-key auth resolution — DB-backed."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from tests.conftest import POSTGRES_AVAILABLE

from app.external import keys
from app.external.dependencies import resolve_service_key
from app.external.models import ServiceApiKey

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _mk_key(db, workspace, *, scopes=("read:core",), revoked=False):
    token, key_hash = keys.generate_key()
    row = ServiceApiKey(
        workspace_id=workspace.id,
        name="OS test",
        key_hash=key_hash,
        scopes=list(scopes),
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db.add(row)
    await db.flush()
    return token, row


@skip_no_pg
async def test_valid_key_resolves_to_workspace(db, workspace):
    token, row = await _mk_key(db, workspace)
    ctx = await resolve_service_key(db, token, scope="read:core")
    assert ctx.workspace_id == workspace.id
    assert ctx.key_id == row.id


@skip_no_pg
async def test_missing_token_401(db):
    with pytest.raises(HTTPException) as exc:
        await resolve_service_key(db, None, scope="read:core")
    assert exc.value.status_code == 401


@skip_no_pg
async def test_unknown_token_401(db):
    with pytest.raises(HTTPException) as exc:
        await resolve_service_key(db, "drinkx_os_nope", scope="read:core")
    assert exc.value.status_code == 401


@skip_no_pg
async def test_revoked_key_403(db, workspace):
    token, _ = await _mk_key(db, workspace, revoked=True)
    with pytest.raises(HTTPException) as exc:
        await resolve_service_key(db, token, scope="read:core")
    assert exc.value.status_code == 403


@skip_no_pg
async def test_missing_scope_403(db, workspace):
    token, _ = await _mk_key(db, workspace, scopes=("read:other",))
    with pytest.raises(HTTPException) as exc:
        await resolve_service_key(db, token, scope="read:core")
    assert exc.value.status_code == 403


@skip_no_pg
async def test_last_used_at_updated(db, workspace):
    token, row = await _mk_key(db, workspace)
    assert row.last_used_at is None
    await resolve_service_key(db, token, scope="read:core")
    await db.refresh(row)
    assert row.last_used_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_external_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.external.dependencies'` (or all skipped if no PG; if skipped, still proceed — the import error surfaces at collection).

- [ ] **Step 3: Implement the dependency**

Create `apps/api/app/external/dependencies.py`:

```python
"""Auth + rate limiting for the external OS read surface.

A single machine key (Authorization: Bearer drinkx_os_...) is resolved
to a workspace-scoped ServiceContext. No Supabase JWT here.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.external import keys
from app.external.models import ServiceApiKey

log = structlog.get_logger()

_RATE_LIMIT_RPS = 10
_rate_state: dict[uuid.UUID, tuple[float, float]] = {}  # key_id -> (tokens, last_ts)


@dataclass(frozen=True)
class ServiceContext:
    workspace_id: uuid.UUID
    key_id: uuid.UUID
    scopes: list[str]


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _check_rate_limit(key_id: uuid.UUID) -> None:
    """In-memory token bucket, 10 rps per key. Single-replica only."""
    now = time.monotonic()
    tokens, last = _rate_state.get(key_id, (float(_RATE_LIMIT_RPS), now))
    tokens = min(_RATE_LIMIT_RPS, tokens + (now - last) * _RATE_LIMIT_RPS)
    if tokens < 1.0:
        _rate_state[key_id] = (tokens, now)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
    _rate_state[key_id] = (tokens - 1.0, now)


async def resolve_service_key(
    session: AsyncSession, token: str | None, *, scope: str
) -> ServiceContext:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing key")
    row = (
        await session.execute(
            select(ServiceApiKey).where(ServiceApiKey.key_hash == keys.hash_key(token))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid key")
    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="key revoked")
    if scope not in row.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"scope {scope} required")
    _check_rate_limit(row.id)
    row.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return ServiceContext(workspace_id=row.workspace_id, key_id=row.id, scopes=list(row.scopes))


def require_service_key(scope: str = "read:core"):
    async def _dep(
        authorization: Annotated[str | None, Header()] = None,
        session: Annotated[AsyncSession, Depends(get_db)] = None,
    ) -> ServiceContext:
        return await resolve_service_key(session, _extract_bearer(authorization), scope=scope)

    return _dep
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && python -m pytest tests/test_external_auth.py -v`
Expected: PASS (6 tests) if Postgres is available; SKIPPED otherwise. Either is acceptable — no import errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/external/dependencies.py apps/api/tests/test_external_auth.py
git commit -m "feat(external): require_service_key auth dependency + rate limiter"
```

---

## Task 3: CLI to issue/revoke keys

**Files:**
- Create: `apps/api/scripts/issue_service_key.py`

**Interfaces:**
- Consumes: `keys.generate_key`, `models.ServiceApiKey`, the app's async engine/session.
- Produces: a runnable CLI. No code depends on it.

- [ ] **Step 1: Inspect the existing script pattern**

Read `apps/api/scripts/create_test_user.py` to copy its async-session bootstrap (engine creation, `asyncio.run`). Reuse the exact session-construction idiom it uses.

- [ ] **Step 2: Write the CLI**

Create `apps/api/scripts/issue_service_key.py`:

```python
"""Issue or revoke a machine API key for external OS access.

Usage:
    python -m scripts.issue_service_key issue --workspace <uuid> --name "OS DrinkX"
    python -m scripts.issue_service_key revoke --key-id <uuid>
    python -m scripts.issue_service_key list --workspace <uuid>

`issue` prints the full token ONCE — store it in the OS `.env`. The DB
keeps only the sha256 hash.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import get_session_factory
from app.external import keys
from app.external.models import ServiceApiKey


async def _issue(workspace_id: uuid.UUID, name: str) -> None:
    token, key_hash = keys.generate_key()
    async with get_session_factory()() as s:
        row = ServiceApiKey(
            workspace_id=workspace_id, name=name, key_hash=key_hash, scopes=["read:core"]
        )
        s.add(row)
        await s.commit()
        print(f"key_id={row.id}")
    print("TOKEN (store now, shown once):")
    print(token)


async def _revoke(key_id: uuid.UUID) -> None:
    async with get_session_factory()() as s:
        row = (
            await s.execute(select(ServiceApiKey).where(ServiceApiKey.id == key_id))
        ).scalar_one_or_none()
        if row is None:
            print("not found")
            return
        row.revoked_at = datetime.now(timezone.utc)
        await s.commit()
        print(f"revoked {key_id}")


async def _list(workspace_id: uuid.UUID) -> None:
    async with get_session_factory()() as s:
        rows = (
            await s.execute(
                select(ServiceApiKey).where(ServiceApiKey.workspace_id == workspace_id)
            )
        ).scalars().all()
        for r in rows:
            status = "revoked" if r.revoked_at else "active"
            print(f"{r.id}  {status:8}  {r.name}  last_used={r.last_used_at}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("issue"); pi.add_argument("--workspace", required=True); pi.add_argument("--name", required=True)
    pr = sub.add_parser("revoke"); pr.add_argument("--key-id", required=True)
    pl = sub.add_parser("list"); pl.add_argument("--workspace", required=True)
    args = p.parse_args()
    if args.cmd == "issue":
        asyncio.run(_issue(uuid.UUID(args.workspace), args.name))
    elif args.cmd == "revoke":
        asyncio.run(_revoke(uuid.UUID(args.key_id)))
    elif args.cmd == "list":
        asyncio.run(_list(uuid.UUID(args.workspace)))


if __name__ == "__main__":
    main()
```

> Note: `get_session_factory()` returns an `async_sessionmaker` (confirmed in `app/db.py`), so the session context manager is `get_session_factory()()` — the double call is intentional. `create_test_user.py` uses the same engine bootstrap.

- [ ] **Step 3: Verify it compiles and argparse works**

Run: `cd apps/api && python -m py_compile scripts/issue_service_key.py`
Expected: no output.

Run: `cd apps/api && python -m scripts.issue_service_key --help`
Expected: usage text listing `issue`, `revoke`, `list`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/scripts/issue_service_key.py
git commit -m "feat(external): CLI to issue/revoke machine keys"
```

---

## Task 4: External schemas + repositories + services (reads + summaries)

**Files:**
- Create: `apps/api/app/external/schemas.py`
- Create: `apps/api/app/external/repositories.py`
- Create: `apps/api/app/external/services.py`
- Test: `apps/api/tests/test_external_read.py`

**Interfaces:**
- Consumes: `ServiceContext.workspace_id`; ORM models `Lead`, `Company`, `Contact`, `Pipeline`, `Stage`, `LeadStageHistory`, `User`.
- Produces (service functions, all `async`, all taking `session` + `workspace_id`):
  - `list_leads(session, workspace_id, *, pipeline_id=None, stage_id=None, assigned_to=None, updated_since=None, q=None, cursor=None, limit=50) -> LeadPage`
  - `get_lead(session, workspace_id, lead_id) -> LeadOut | None`
  - `lead_summary(session, workspace_id, lead_id) -> LeadSummaryOut | None`
  - `list_companies(session, workspace_id, *, q=None, updated_since=None, cursor=None, limit=50) -> CompanyPage`
  - `get_company(session, workspace_id, company_id) -> CompanyOut | None`
  - `list_contacts(session, workspace_id, *, lead_id=None, company_id=None) -> list[ContactOut]`
  - `list_pipelines(session, workspace_id) -> list[PipelineOut]`
  - `pipeline_summary(session, workspace_id, pipeline_id) -> PipelineSummaryOut | None`
  - `meta(session, workspace_id) -> MetaOut`
- Schemas (Pydantic v2, `model_config = ConfigDict(from_attributes=True)`): `LeadOut, LeadSummaryOut, LeadPage, CompanyOut, CompanyPage, ContactOut, StageOut, PipelineOut, PipelineSummaryOut, StageSummary, MetaOut`. Cursor pagination: `*Page` has `items: list[...]` and `next_cursor: str | None`.

Cursor scheme: opaque base64 of the last row's `updated_at` ISO + `id`. Keep it simple — `cursor = base64(f"{updated_at.isoformat()}|{id}")`; decode to filter `(updated_at, id) < (cursor_updated_at, cursor_id)` under `ORDER BY updated_at DESC, id DESC`.

- [ ] **Step 1: Write the failing service tests (PG-gated)**

Create `apps/api/tests/test_external_read.py`:

```python
"""External read services — DB-backed."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

# Configure ORM mappers (string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.lead_sources.models import LeadSource  # noqa: F401

from app.external import services as svc

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _seed(db, workspace, user):
    from app.pipelines.models import Pipeline, Stage
    from app.leads.models import Lead, LeadStageHistory

    p = Pipeline(workspace_id=workspace.id, name="Sales", type="sales", position=0)
    db.add(p); await db.flush()
    s0 = Stage(pipeline_id=p.id, name="Новые", position=0, color="#ccc", rot_days=14, probability=10)
    s1 = Stage(pipeline_id=p.id, name="В работе", position=1, color="#ccc", rot_days=14, probability=50)
    db.add_all([s0, s1]); await db.flush()

    now = datetime.now(timezone.utc)
    a = Lead(workspace_id=workspace.id, company_name="Alpha", pipeline_id=p.id, stage_id=s1.id,
             assignment_status="assigned", assigned_to=user.id, deal_amount=1000)
    b = Lead(workspace_id=workspace.id, company_name="Beta", pipeline_id=p.id, stage_id=s0.id,
             assignment_status="pool", deal_amount=500)
    db.add_all([a, b]); await db.flush()
    # open stage-history row for Alpha → stage_entered_at
    db.add(LeadStageHistory(lead_id=a.id, stage_id=s1.id, entered_at=now - timedelta(days=3)))
    await db.flush()
    return p, s0, s1, a, b


@skip_no_pg
async def test_list_leads_includes_pool_and_stage_entered_at(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    page = await svc.list_leads(db, workspace.id, limit=50)
    names = {l.company_name for l in page.items}
    assert names == {"Alpha", "Beta"}  # pool lead included, unlike internal list_leads
    alpha = next(l for l in page.items if l.company_name == "Alpha")
    assert alpha.stage_entered_at is not None
    beta = next(l for l in page.items if l.company_name == "Beta")
    assert beta.stage_entered_at is None  # no history row


@skip_no_pg
async def test_list_leads_filters_by_pipeline_and_stage(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    page = await svc.list_leads(db, workspace.id, stage_id=s1.id)
    assert [l.company_name for l in page.items] == ["Alpha"]


@skip_no_pg
async def test_lead_summary_shape(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    summ = await svc.lead_summary(db, workspace.id, a.id)
    assert summ is not None
    assert summ.lead.company_name == "Alpha"
    assert summ.stage_name == "В работе"
    assert summ.days_in_stage is not None and summ.days_in_stage >= 3


@skip_no_pg
async def test_workspace_isolation(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    other_ws = uuid.uuid4()
    assert await svc.get_lead(db, other_ws, a.id) is None


@skip_no_pg
async def test_pipeline_summary_counts_and_amounts(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    summ = await svc.pipeline_summary(db, workspace.id, p.id)
    assert summ is not None
    by_stage = {s.stage_name: s for s in summ.stages}
    assert by_stage["В работе"].lead_count == 1
    assert float(by_stage["В работе"].total_amount) == 1000.0
    assert by_stage["Новые"].lead_count == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_external_read.py -v`
Expected: FAIL at import (`app.external.services` missing) or SKIPPED with no PG — but the collection import of `svc` must resolve, so create the modules next.

- [ ] **Step 3: Write the schemas**

Create `apps/api/app/external/schemas.py`:

```python
"""Whitelist response schemas for the external OS read surface.

Never serialize ORM models directly. Only the fields below leave the
system. Dates are timezone-aware and serialize as ISO 8601 UTC.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LeadOut(_Base):
    id: uuid.UUID
    company_name: str
    segment: str | None = None
    city: str | None = None
    source: str | None = None
    pipeline_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    stage_entered_at: datetime | None = None
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None
    deal_type: str | None = None
    priority: str | None = None
    score: int = 0
    assignment_status: str
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    next_action_at: datetime | None = None
    last_activity_at: datetime | None = None
    won_at: datetime | None = None
    lost_at: datetime | None = None
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime


class LeadPage(_Base):
    items: list[LeadOut]
    next_cursor: str | None = None


class CompanyOut(_Base):
    id: uuid.UUID
    name: str
    inn: str | None = None
    website: str | None = None
    city: str | None = None
    segment: str | None = None
    created_at: datetime
    updated_at: datetime


class CompanyPage(_Base):
    items: list[CompanyOut]
    next_cursor: str | None = None


class ContactOut(_Base):
    id: uuid.UUID
    name: str
    position: str | None = None
    email: str | None = None
    phone: str | None = None
    lead_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class StageOut(_Base):
    id: uuid.UUID
    name: str
    position: int
    probability: int
    is_won: bool
    is_lost: bool
    rot_days: int


class PipelineOut(_Base):
    id: uuid.UUID
    name: str
    position: int
    stages: list[StageOut]


class LeadSummaryOut(BaseModel):
    lead: LeadOut
    company: CompanyOut | None = None
    contacts: list[ContactOut] = []
    stage_name: str | None = None
    stage_probability: int | None = None
    days_in_stage: int | None = None
    is_rotting_stage: bool = False
    is_rotting_next_step: bool = False


class StageSummary(BaseModel):
    stage_id: uuid.UUID
    stage_name: str
    lead_count: int
    total_amount: Decimal
    rotting_count: int


class PipelineSummaryOut(BaseModel):
    pipeline_id: uuid.UUID
    pipeline_name: str
    stages: list[StageSummary]
    total_leads: int
    total_amount: Decimal


class ManagerOut(BaseModel):
    id: uuid.UUID
    name: str


class MetaOut(BaseModel):
    contract_version: str
    stages: list[StageOut]
    managers: list[ManagerOut]
```

> The `tags` field maps from the ORM attribute `tags_json`. Add a validation alias so `from_attributes` picks it up: on `LeadOut`, set `tags` via `model_config = ConfigDict(from_attributes=True, populate_by_name=True)` and declare `tags: list[str] = Field(default=[], validation_alias="tags_json")`. Import `Field` from pydantic. Confirm at implementation time that the alias resolves against the ORM attribute name `tags_json` (see `app/leads/models.py`).

- [ ] **Step 4: Write the repositories**

Create `apps/api/app/external/repositories.py`. Implement workspace-scoped queries. Key points:
- `list_leads_rows(...)`: `select(Lead, LeadStageHistory.entered_at, User.name)` with `outerjoin(LeadStageHistory, and_(LeadStageHistory.lead_id == Lead.id, LeadStageHistory.exited_at.is_(None)))` and `outerjoin(User, User.id == Lead.assigned_to)`; filter `Lead.workspace_id == workspace_id`, `Lead.deleted_at.is_(None)`; apply optional filters; `order_by(Lead.updated_at.desc(), Lead.id.desc())`; cursor filter; `limit(limit + 1)` to detect next page. Return rows so the service can attach `stage_entered_at` and `assigned_to_name` onto the schema.
- `get_lead_row(...)`, `get_company_row(...)`: single-row workspace-scoped.
- `list_contacts_rows(...)`: by `lead_id` or `company_id`.
- `list_pipelines_rows(...)`: pipelines + eager `selectinload(Pipeline.stages)`.
- `pipeline_stage_aggregates(...)`: `select(Stage.id, Stage.name, func.count(Lead.id), func.coalesce(func.sum(Lead.deal_amount), 0), func.sum(case((Lead.is_rotting_stage, 1), else_=0)))` grouped by stage for the pipeline, `outerjoin(Lead)` scoped to workspace + not deleted.
- `list_managers(...)`: `users.repositories.list_for_workspace` may be reused; else `select(User.id, User.name).where(User.workspace_id == workspace_id)`.

```python
"""Workspace-scoped read queries for the external OS surface."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.companies.models import Company
from app.contacts.models import Contact
from app.auth.models import User
from app.leads.models import Lead, LeadStageHistory
from app.pipelines.models import Pipeline, Stage


def encode_cursor(updated_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{updated_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, rid = raw.split("|", 1)
    return datetime.fromisoformat(ts), uuid.UUID(rid)


async def list_leads_rows(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    pipeline_id: uuid.UUID | None,
    stage_id: uuid.UUID | None,
    assigned_to: uuid.UUID | None,
    updated_since: datetime | None,
    q: str | None,
    cursor: str | None,
    limit: int,
):
    stmt = (
        select(Lead, LeadStageHistory.entered_at.label("stage_entered_at"), User.name.label("assigned_to_name"))
        .outerjoin(
            LeadStageHistory,
            and_(LeadStageHistory.lead_id == Lead.id, LeadStageHistory.exited_at.is_(None)),
        )
        .outerjoin(User, User.id == Lead.assigned_to)
        .where(Lead.workspace_id == workspace_id, Lead.deleted_at.is_(None))
    )
    if pipeline_id is not None:
        stmt = stmt.where(Lead.pipeline_id == pipeline_id)
    if stage_id is not None:
        stmt = stmt.where(Lead.stage_id == stage_id)
    if assigned_to is not None:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    if updated_since is not None:
        stmt = stmt.where(Lead.updated_at >= updated_since)
    if q is not None:
        stmt = stmt.where(Lead.company_name.ilike(f"%{q}%"))
    if cursor is not None:
        c_ts, c_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Lead.updated_at, Lead.id) < (c_ts, c_id)  # row-value comparison
        )
    stmt = stmt.order_by(Lead.updated_at.desc(), Lead.id.desc()).limit(limit + 1)
    return list((await db.execute(stmt)).all())


async def get_lead_row(db, workspace_id, lead_id):
    stmt = (
        select(Lead, LeadStageHistory.entered_at.label("stage_entered_at"), User.name.label("assigned_to_name"))
        .outerjoin(
            LeadStageHistory,
            and_(LeadStageHistory.lead_id == Lead.id, LeadStageHistory.exited_at.is_(None)),
        )
        .outerjoin(User, User.id == Lead.assigned_to)
        .where(Lead.id == lead_id, Lead.workspace_id == workspace_id, Lead.deleted_at.is_(None))
    )
    return (await db.execute(stmt)).first()


async def get_company_row(db, workspace_id, company_id):
    stmt = select(Company).where(Company.id == company_id, Company.workspace_id == workspace_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_companies_rows(db, workspace_id, *, q, updated_since, cursor, limit):
    stmt = select(Company).where(Company.workspace_id == workspace_id)
    if q is not None:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    if updated_since is not None:
        stmt = stmt.where(Company.updated_at >= updated_since)
    if cursor is not None:
        c_ts, c_id = decode_cursor(cursor)
        stmt = stmt.where((Company.updated_at, Company.id) < (c_ts, c_id))
    stmt = stmt.order_by(Company.updated_at.desc(), Company.id.desc()).limit(limit + 1)
    return list((await db.execute(stmt)).scalars().all())


async def list_contacts_rows(db, workspace_id, *, lead_id, company_id):
    # Contact carries workspace_id directly (see app/contacts/models.py),
    # so isolation is a plain filter — no join needed.
    stmt = select(Contact).where(Contact.workspace_id == workspace_id)
    if lead_id is not None:
        stmt = stmt.where(Contact.lead_id == lead_id)
    else:
        stmt = stmt.where(Contact.company_id == company_id)
    return list((await db.execute(stmt)).scalars().all())


async def list_pipelines_rows(db, workspace_id):
    stmt = (
        select(Pipeline)
        .where(Pipeline.workspace_id == workspace_id)
        .options(selectinload(Pipeline.stages))
        .order_by(Pipeline.position)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_pipeline_row(db, workspace_id, pipeline_id):
    stmt = (
        select(Pipeline)
        .where(Pipeline.id == pipeline_id, Pipeline.workspace_id == workspace_id)
        .options(selectinload(Pipeline.stages))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def pipeline_stage_aggregates(db, workspace_id, pipeline_id):
    stmt = (
        select(
            Stage.id,
            Stage.name,
            func.count(Lead.id),
            func.coalesce(func.sum(Lead.deal_amount), 0),
            func.coalesce(func.sum(case((Lead.is_rotting_stage, 1), else_=0)), 0),
        )
        .select_from(Stage)
        .outerjoin(
            Lead,
            and_(
                Lead.stage_id == Stage.id,
                Lead.workspace_id == workspace_id,
                Lead.deleted_at.is_(None),
            ),
        )
        .where(Stage.pipeline_id == pipeline_id)
        .group_by(Stage.id, Stage.name, Stage.position)
        .order_by(Stage.position)
    )
    return list((await db.execute(stmt)).all())


async def list_managers(db, workspace_id):
    stmt = select(User.id, User.name).where(User.workspace_id == workspace_id).order_by(User.name)
    return list((await db.execute(stmt)).all())
```

> Confirmed present: `Company.workspace_id`, `Contact.workspace_id`, `Contact.lead_id`, `Contact.company_id`. Still verify `Company.updated_at` (via `TimestampedMixin`) and `Contact.position` at implementation; adjust names if the real schema differs.

- [ ] **Step 5: Write the services**

Create `apps/api/app/external/services.py`:

```python
"""Service layer for the external OS surface. Called by REST + MCP."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.external import repositories as repo
from app.external.schemas import (
    CompanyOut, CompanyPage, ContactOut, LeadOut, LeadPage, LeadSummaryOut,
    ManagerOut, MetaOut, PipelineOut, PipelineSummaryOut, StageOut, StageSummary,
)

CONTRACT_VERSION = "1.0"
_MAX_LIMIT = 100


def _clamp(limit: int) -> int:
    return max(1, min(_MAX_LIMIT, limit))


def _lead_out(lead, stage_entered_at, assigned_to_name) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.stage_entered_at = stage_entered_at
    out.assigned_to_name = assigned_to_name
    return out


async def list_leads(db, workspace_id, *, pipeline_id=None, stage_id=None,
                     assigned_to=None, updated_since=None, q=None, cursor=None, limit=50) -> LeadPage:
    limit = _clamp(limit)
    rows = await repo.list_leads_rows(
        db, workspace_id, pipeline_id=pipeline_id, stage_id=stage_id,
        assigned_to=assigned_to, updated_since=updated_since, q=q, cursor=cursor, limit=limit,
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_lead_out(r[0], r[1], r[2]) for r in rows]
    next_cursor = repo.encode_cursor(rows[-1][0].updated_at, rows[-1][0].id) if has_more and rows else None
    return LeadPage(items=items, next_cursor=next_cursor)


async def get_lead(db, workspace_id, lead_id) -> LeadOut | None:
    row = await repo.get_lead_row(db, workspace_id, lead_id)
    if row is None:
        return None
    return _lead_out(row[0], row[1], row[2])


async def lead_summary(db, workspace_id, lead_id) -> LeadSummaryOut | None:
    row = await repo.get_lead_row(db, workspace_id, lead_id)
    if row is None:
        return None
    lead, stage_entered_at, assigned_to_name = row[0], row[1], row[2]
    lead_out = _lead_out(lead, stage_entered_at, assigned_to_name)

    company = None
    if lead.company_id is not None:
        c = await repo.get_company_row(db, workspace_id, lead.company_id)
        company = CompanyOut.model_validate(c) if c is not None else None

    contacts = [ContactOut.model_validate(c) for c in await repo.list_contacts_rows(
        db, workspace_id, lead_id=lead.id, company_id=None)]

    stage_name = stage_probability = None
    if lead.stage_id is not None:
        pl = None  # find the stage via pipeline rows is overkill; fetch stage directly
    # Fetch the stage row for name/probability:
    from sqlalchemy import select
    from app.pipelines.models import Stage
    if lead.stage_id is not None:
        st = (await db.execute(select(Stage).where(Stage.id == lead.stage_id))).scalar_one_or_none()
        if st is not None:
            stage_name, stage_probability = st.name, st.probability

    days_in_stage = None
    if stage_entered_at is not None:
        days_in_stage = (datetime.now(timezone.utc) - stage_entered_at).days

    return LeadSummaryOut(
        lead=lead_out, company=company, contacts=contacts,
        stage_name=stage_name, stage_probability=stage_probability, days_in_stage=days_in_stage,
        is_rotting_stage=bool(lead.is_rotting_stage), is_rotting_next_step=bool(lead.is_rotting_next_step),
    )


async def list_companies(db, workspace_id, *, q=None, updated_since=None, cursor=None, limit=50) -> CompanyPage:
    limit = _clamp(limit)
    rows = await repo.list_companies_rows(db, workspace_id, q=q, updated_since=updated_since, cursor=cursor, limit=limit)
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [CompanyOut.model_validate(c) for c in rows]
    next_cursor = repo.encode_cursor(rows[-1].updated_at, rows[-1].id) if has_more and rows else None
    return CompanyPage(items=items, next_cursor=next_cursor)


async def get_company(db, workspace_id, company_id) -> CompanyOut | None:
    c = await repo.get_company_row(db, workspace_id, company_id)
    return CompanyOut.model_validate(c) if c is not None else None


async def list_contacts(db, workspace_id, *, lead_id=None, company_id=None) -> list[ContactOut]:
    rows = await repo.list_contacts_rows(db, workspace_id, lead_id=lead_id, company_id=company_id)
    return [ContactOut.model_validate(c) for c in rows]


def _pipeline_out(p) -> PipelineOut:
    return PipelineOut(
        id=p.id, name=p.name, position=p.position,
        stages=[StageOut.model_validate(s) for s in sorted(p.stages, key=lambda s: s.position)],
    )


async def list_pipelines(db, workspace_id) -> list[PipelineOut]:
    return [_pipeline_out(p) for p in await repo.list_pipelines_rows(db, workspace_id)]


async def pipeline_summary(db, workspace_id, pipeline_id) -> PipelineSummaryOut | None:
    p = await repo.get_pipeline_row(db, workspace_id, pipeline_id)
    if p is None:
        return None
    aggs = await repo.pipeline_stage_aggregates(db, workspace_id, pipeline_id)
    stages = [
        StageSummary(stage_id=a[0], stage_name=a[1], lead_count=a[2], total_amount=a[3], rotting_count=a[4])
        for a in aggs
    ]
    return PipelineSummaryOut(
        pipeline_id=p.id, pipeline_name=p.name, stages=stages,
        total_leads=sum(s.lead_count for s in stages),
        total_amount=sum((s.total_amount for s in stages), start=type(stages[0].total_amount)(0)) if stages else 0,
    )


async def meta(db, workspace_id) -> MetaOut:
    pipelines = await repo.list_pipelines_rows(db, workspace_id)
    all_stages = [StageOut.model_validate(s) for p in pipelines for s in p.stages]
    managers = [ManagerOut(id=m[0], name=m[1]) for m in await repo.list_managers(db, workspace_id)]
    return MetaOut(contract_version=CONTRACT_VERSION, stages=all_stages, managers=managers)
```

> Simplify the `lead_summary` stage lookup if a cleaner path exists at implementation (the inline import is intentional to avoid a circular import at module load; keep or hoist as the linter prefers). Ensure `total_amount` sum keeps `Decimal` type.

- [ ] **Step 6: Run the read tests**

Run: `cd apps/api && python -m pytest tests/test_external_read.py -v`
Expected: PASS (5 tests) with Postgres; SKIPPED without. No import/collection errors either way.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/external/schemas.py apps/api/app/external/repositories.py apps/api/app/external/services.py apps/api/tests/test_external_read.py
git commit -m "feat(external): read schemas, repositories, services + summaries"
```

---

## Task 5: `/external/v1` routers + mount + read-only invariant test

**Files:**
- Create: `apps/api/app/external/routers.py`
- Modify: `apps/api/app/main.py` (include the router)
- Test: `apps/api/tests/test_external_routes_readonly.py`

**Interfaces:**
- Consumes: `require_service_key`, all `services.*` functions, all schemas.
- Produces: `router = APIRouter(prefix="/external/v1", tags=["external"])` exported for `main.py`.

- [ ] **Step 1: Write the read-only invariant test (no PG needed)**

Create `apps/api/tests/test_external_routes_readonly.py`:

```python
"""Structural guard: the external surface exposes GET-only routes."""
from __future__ import annotations

from app.external.routers import router


def test_all_external_routes_are_get_only():
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        non_read = methods - {"GET", "HEAD", "OPTIONS"}
        assert not non_read, f"{route.path} exposes {non_read}"


def test_external_prefix():
    assert router.prefix == "/external/v1"


def test_expected_endpoints_present():
    paths = {r.path for r in router.routes}
    for p in [
        "/external/v1/leads",
        "/external/v1/leads/{lead_id}",
        "/external/v1/leads/{lead_id}/summary",
        "/external/v1/companies",
        "/external/v1/companies/{company_id}",
        "/external/v1/contacts",
        "/external/v1/pipelines",
        "/external/v1/pipelines/{pipeline_id}/summary",
        "/external/v1/meta",
    ]:
        assert p in paths, f"missing {p}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_external_routes_readonly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.external.routers'`.

- [ ] **Step 3: Write the routers**

Create `apps/api/app/external/routers.py`:

```python
"""GET-only REST surface for external OS access — /external/v1/*."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.external import services as svc
from app.external.dependencies import ServiceContext, require_service_key
from app.external.schemas import (
    CompanyOut, CompanyPage, ContactOut, LeadOut, LeadPage, LeadSummaryOut,
    MetaOut, PipelineOut, PipelineSummaryOut,
)

router = APIRouter(prefix="/external/v1", tags=["external"])

_Ctx = Annotated[ServiceContext, Depends(require_service_key())]
_Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/leads", response_model=LeadPage)
async def list_leads(
    ctx: _Ctx, db: _Db,
    pipeline_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    updated_since: datetime | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return await svc.list_leads(
        db, ctx.workspace_id, pipeline_id=pipeline_id, stage_id=stage_id,
        assigned_to=assigned_to, updated_since=updated_since, q=q, cursor=cursor, limit=limit,
    )


@router.get("/leads/{lead_id}", response_model=LeadOut)
async def get_lead(ctx: _Ctx, db: _Db, lead_id: uuid.UUID):
    out = await svc.get_lead(db, ctx.workspace_id, lead_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    return out


@router.get("/leads/{lead_id}/summary", response_model=LeadSummaryOut)
async def lead_summary(ctx: _Ctx, db: _Db, lead_id: uuid.UUID):
    out = await svc.lead_summary(db, ctx.workspace_id, lead_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    return out


@router.get("/companies", response_model=CompanyPage)
async def list_companies(
    ctx: _Ctx, db: _Db,
    q: str | None = None,
    updated_since: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return await svc.list_companies(db, ctx.workspace_id, q=q, updated_since=updated_since, cursor=cursor, limit=limit)


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(ctx: _Ctx, db: _Db, company_id: uuid.UUID):
    out = await svc.get_company(db, ctx.workspace_id, company_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    return out


@router.get("/contacts", response_model=list[ContactOut])
async def list_contacts(
    ctx: _Ctx, db: _Db,
    lead_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
):
    if (lead_id is None) == (company_id is None):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exactly one of lead_id or company_id required")
    return await svc.list_contacts(db, ctx.workspace_id, lead_id=lead_id, company_id=company_id)


@router.get("/pipelines", response_model=list[PipelineOut])
async def list_pipelines(ctx: _Ctx, db: _Db):
    return await svc.list_pipelines(db, ctx.workspace_id)


@router.get("/pipelines/{pipeline_id}/summary", response_model=PipelineSummaryOut)
async def pipeline_summary(ctx: _Ctx, db: _Db, pipeline_id: uuid.UUID):
    out = await svc.pipeline_summary(db, ctx.workspace_id, pipeline_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline not found")
    return out


@router.get("/meta", response_model=MetaOut)
async def meta(ctx: _Ctx, db: _Db):
    return await svc.meta(db, ctx.workspace_id)
```

- [ ] **Step 4: Run the invariant test**

Run: `cd apps/api && python -m pytest tests/test_external_routes_readonly.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Mount the router in main.py**

In `apps/api/app/main.py`, alongside the other `include_router` calls (after `base_update_router` block), add:

```python
    from app.external.routers import router as external_router
    app.include_router(external_router)
```

- [ ] **Step 6: Verify the app boots and route is registered**

Run: `cd apps/api && python -c "from app.main import create_app; app = create_app(); paths = [r.path for r in app.routes]; assert '/external/v1/leads' in paths, paths; print('ok')"`
Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/external/routers.py apps/api/app/main.py apps/api/tests/test_external_routes_readonly.py
git commit -m "feat(external): GET-only /external/v1 routers + mount"
```

---

## Task 6: MCP server (`/mcp`) with 4 read-only tools

**Files:**
- Modify: `apps/api/pyproject.toml` (add `mcp` dependency)
- Create: `apps/api/app/external/mcp_server.py`
- Modify: `apps/api/app/main.py` (mount the MCP ASGI app)
- Test: `apps/api/tests/test_external_mcp.py`

**Interfaces:**
- Consumes: `services.*`, `resolve_service_key`, `app.db` session factory.
- Produces: `build_mcp_app()` returning an ASGI app to mount at `/mcp`; tool functions `search_leads`, `get_lead_summary`, `pipeline_overview`, `list_pipelines`.

- [ ] **Step 1: Add the dependency**

In `apps/api/pyproject.toml`, add to the `dependencies` array:

```
    "mcp>=1.2.0",
```

Run: `cd apps/api && pip install 'mcp>=1.2.0'` (or `uv pip install` / the project's installer). Confirm import: `python -c "import mcp; print(mcp.__version__)"`.

> If the environment cannot install `mcp` offline, mark this task `> [BLOCKED]` with the install command needed, and stop — Tasks 1–5 already deliver the full REST surface independently.

- [ ] **Step 2: Write the MCP tool test (structure-level, no live transport)**

Create `apps/api/tests/test_external_mcp.py`:

```python
"""MCP server exposes exactly the 4 read-only tools."""
from __future__ import annotations

import pytest

from app.external.mcp_server import server  # the FastMCP/Server instance


@pytest.mark.asyncio
async def test_four_tools_registered():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"search_leads", "get_lead_summary", "pipeline_overview", "list_pipelines"}
```

> If the installed SDK's introspection API differs (e.g. `server._tool_manager.list_tools()` or a sync accessor), adapt the test to the real API discovered in Step 3. The assertion (exactly these 4 names) is the invariant.

- [ ] **Step 3: Implement the MCP server**

Create `apps/api/app/external/mcp_server.py`. Use the official SDK's `FastMCP` with streamable-HTTP transport. Each tool opens a DB session, resolves the bearer key from the request headers to a `ServiceContext`, calls the matching service function, and returns compact JSON (drop null fields).

```python
"""Remote MCP server for external OS read access.

Mounts at /mcp (streamable HTTP). Auth: the same Bearer machine key as
REST, resolved per-call. All tools are read-only.
"""
from __future__ import annotations

import uuid

from mcp.server.fastmcp import FastMCP

from app.db import get_session_factory  # returns an async_sessionmaker
from app.external import services as svc
from app.external.dependencies import resolve_service_key

server = FastMCP("drinkx-crm")


async def _ctx_from_headers(headers: dict) -> "object":
    from app.external.dependencies import _extract_bearer
    token = _extract_bearer(headers.get("authorization"))
    async with get_session_factory()() as s:
        # resolve_service_key commits last_used_at on its own session
        return await resolve_service_key(s, token, scope="read:core")


@server.tool()
async def search_leads(q: str | None = None, pipeline_id: str | None = None,
                       stage_id: str | None = None, limit: int = 25) -> list[dict]:
    """Search leads by company name / pipeline / stage. Read-only."""
    ctx = await _ctx_from_headers(server.get_context().request_context.request.headers)
    async with get_session_factory()() as s:
        page = await svc.list_leads(
            s, ctx.workspace_id, q=q,
            pipeline_id=uuid.UUID(pipeline_id) if pipeline_id else None,
            stage_id=uuid.UUID(stage_id) if stage_id else None,
            limit=limit,
        )
    return [l.model_dump(exclude_none=True, mode="json") for l in page.items]


@server.tool()
async def get_lead_summary(lead_id: str) -> dict | None:
    """Full picture of one lead (company, contacts, stage, rot flags). Read-only."""
    ctx = await _ctx_from_headers(server.get_context().request_context.request.headers)
    async with get_session_factory()() as s:
        out = await svc.lead_summary(s, ctx.workspace_id, uuid.UUID(lead_id))
    return out.model_dump(exclude_none=True, mode="json") if out else None


@server.tool()
async def pipeline_overview(pipeline_id: str) -> dict | None:
    """Per-stage counts and deal amounts for a pipeline. Read-only."""
    ctx = await _ctx_from_headers(server.get_context().request_context.request.headers)
    async with get_session_factory()() as s:
        out = await svc.pipeline_summary(s, ctx.workspace_id, uuid.UUID(pipeline_id))
    return out.model_dump(exclude_none=True, mode="json") if out else None


@server.tool()
async def list_pipelines() -> list[dict]:
    """List pipelines with their stages. Read-only."""
    ctx = await _ctx_from_headers(server.get_context().request_context.request.headers)
    async with get_session_factory()() as s:
        pls = await svc.list_pipelines(s, ctx.workspace_id)
    return [p.model_dump(exclude_none=True, mode="json") for p in pls]


def build_mcp_app():
    """ASGI app for mounting at /mcp."""
    return server.streamable_http_app()
```

> The exact accessor for request headers inside a tool (`server.get_context()...headers`) depends on the installed SDK version. During implementation, verify against the SDK: if header access from within a tool isn't supported, use the SDK's auth/middleware hook instead (FastMCP supports a custom auth provider). The invariant: every tool call resolves a valid `read:core` key to a workspace before returning data. If the SDK's auth model doesn't fit cleanly, gate the whole `/mcp` mount behind an ASGI middleware that runs `resolve_service_key` on the `Authorization` header and injects `workspace_id` into scope — document whichever path you take in the module docstring.

- [ ] **Step 4: Mount the MCP app in main.py**

In `apps/api/app/main.py`, inside `create_app()` after routers are included, add:

```python
    from app.external.mcp_server import build_mcp_app
    app.mount("/mcp", build_mcp_app())
```

- [ ] **Step 5: Run the MCP test + boot check**

Run: `cd apps/api && python -m pytest tests/test_external_mcp.py -v`
Expected: PASS (1 test) — 4 tools registered.

Run: `cd apps/api && python -c "from app.main import create_app; create_app(); print('boots')"`
Expected: `boots` (app constructs with MCP mounted).

- [ ] **Step 6: Commit**

```bash
git add apps/api/pyproject.toml apps/api/app/external/mcp_server.py apps/api/app/main.py apps/api/tests/test_external_mcp.py
git commit -m "feat(external): remote MCP server at /mcp with 4 read-only tools"
```

---

## Task 7: Consumer README + full-suite verification

**Files:**
- Create: `docs/external-api/README.md`

**Interfaces:** none (documentation + verification).

- [ ] **Step 1: Write the consumer doc**

Create `docs/external-api/README.md` covering, for the OS side:
- Base URL: `https://crm.drinkx.tech/api/external/v1` (REST) and `https://crm.drinkx.tech/api/mcp` (MCP).
- Auth header: `Authorization: Bearer drinkx_os_...`.
- Endpoint table (copy from spec §5) with one `curl` example, e.g.:

```bash
curl -s https://crm.drinkx.tech/api/external/v1/leads?limit=5 \
  -H "Authorization: Bearer $DRINKX_OS_KEY" | jq
```

- Pagination: pass back `next_cursor` as `?cursor=`.
- Incremental pull: `?updated_since=2026-07-01T00:00:00Z`.
- `stage_entered_at` may be `null` (no history since 2026-05-16) — treat null as "unknown", not a date.
- Dates are ISO 8601 UTC.
- MCP tools: `search_leads`, `get_lead_summary`, `pipeline_overview`, `list_pipelines`.
- Rate limit: 10 rps/key → keep the nightly pull sequential.

- [ ] **Step 2: Run the full external test set**

Run: `cd apps/api && python -m pytest tests/test_external_keys.py tests/test_external_auth.py tests/test_external_read.py tests/test_external_routes_readonly.py tests/test_external_mcp.py -v`
Expected: all PASS (PG-gated ones SKIP if no local Postgres — note which).

- [ ] **Step 3: Compile-check all new modules + collect full suite**

Run: `cd apps/api && python -m py_compile app/external/*.py scripts/issue_service_key.py`
Expected: no output.

Run: `cd apps/api && python -m pytest --collect-only -q`
Expected: collection succeeds with no import errors.

- [ ] **Step 4: Commit**

```bash
git add docs/external-api/README.md
git commit -m "docs(external): consumer README for OS integration"
```

---

## Post-implementation (human-gated, not part of automated execution)

- Run the migration against the DB: `alembic upgrade head`.
- Confirm the target workspace id (spec open question); issue the first key:
  `python -m scripts.issue_service_key issue --workspace <id> --name "OS DrinkX"`.
- Hand the token to the OS side out-of-band; store in OS `.env`.
- Push to `main` only when ready for the prod deploy (triggers the ~20-min pipeline).

---

## Self-Review

**Spec coverage:**
- §3 architecture (external package, own auth, GET-only, reuse-read) → Tasks 1–5. ✓
- §4 auth/keys (`service_api_keys`, sha256, constant-time, CLI, revoke) → Tasks 1–3. ✓
- §5 REST contract (all 9 endpoints, whitelist, cursor pagination, `updated_since`, `stage_entered_at`, `won_at`/`lost_at`, ISO UTC, summaries) → Tasks 4–5. ✓
- §6 MCP (4 tools, same key, streamable HTTP) → Task 6. ✓
- §7 errors/rate-limit/audit/versioning → Task 2 (rate limit, 401/403/429), Task 5 (404, 400), `CONTRACT_VERSION` (versioning). Audit logging via structlog is present in the dependency; **gap:** per-request structured access log not explicitly added — acceptable for v1 (FastAPI + Sentry already log), note for follow-up.
- §8 tests (auth matrix, GET-only snapshot, whitelist, summary ≤3 queries, MCP tools/list) → Tasks 2, 4, 5, 6. The "≤3 SQL queries" target is not asserted by a counter test; covered structurally (summary uses get_lead_row + company + contacts + stage = 4 lightweight queries). **Minor deviation from spec's "≤3":** documented here; not worth a query-counting test in v1.
- §5 `stage_entered_at` null semantics + test → Task 4 test `...includes_pool_and_stage_entered_at`. ✓

**Placeholder scan:** No "TBD"/"handle appropriately" left. A few `>` implementation notes ask the engineer to confirm real attribute names (`Company.updated_at`, `Contact.position`, `tags_json` alias, MCP header accessor) — these are verification instructions, not placeholders; each names the exact file to check and the fallback. Session factory (`get_session_factory()`), workspaces tablename (`workspaces`), and `Contact.workspace_id` were pre-verified against the code.

**Type consistency:** `ServiceContext` (workspace_id/key_id/scopes) consistent across Tasks 2/5/6. `resolve_service_key(session, token, *, scope)` signature consistent Tasks 2/6. Service function names identical between Task 4 (defined), Task 5 (called), Task 6 (called). Schema names consistent between schemas.py and routers/services.

**Known deviations, accepted for v1:** (1) audit log is dependency-level not per-request; (2) summary is 4 not ≤3 queries; (3) MCP auth wiring depends on installed SDK — plan gives a fallback ASGI-middleware path.
