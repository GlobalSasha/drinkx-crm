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
