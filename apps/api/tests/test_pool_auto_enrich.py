"""Sprint 3.9 G4 — pool auto-enrich selection + batch."""
from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _C:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _C()
    _sa_orm.defer = _C()


@pytest.mark.asyncio
async def test_get_pool_leads_needing_enrichment_returns_rows():
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=lambda: MagicMock(all=lambda: [MagicMock(id=lead_id)])
        )
    )

    rows = await repo.get_pool_leads_needing_enrichment(db, limit=20)

    assert len(rows) == 1
    assert rows[0].id == lead_id
    db.execute.assert_awaited_once()
