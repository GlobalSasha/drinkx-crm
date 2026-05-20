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


def _fake_engine_factory():
    """Stand-in for _build_task_engine_and_factory: an engine with an
    async dispose() and a factory whose () returns an async-context
    session yielding a MagicMock db."""
    engine = MagicMock()
    engine.dispose = AsyncMock()

    class _FakeSession:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    def factory():
        return _FakeSession()

    return engine, factory


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


@pytest.mark.asyncio
async def test_pool_auto_enrich_batch_enqueues_lightweight():
    """Stale pool leads get a lightweight enrichment enqueued, staggered."""
    from app.enrichment import tasks as t

    lead_ids = [uuid.uuid4(), uuid.uuid4()]
    fake_leads = [MagicMock(id=lid) for lid in lead_ids]

    with patch.object(
        t, "get_pool_leads_needing_enrichment",
        new=AsyncMock(return_value=fake_leads),
    ):
        with patch.object(t, "_enqueue_lightweight_enrich", new=AsyncMock()) as enq:
            with patch.object(t, "_running_run_exists", new=AsyncMock(return_value=False)):
                with patch.object(t, "_build_task_engine_and_factory", new=_fake_engine_factory):
                    out = await t._run_pool_auto_enrich_batch(limit=20)

    assert enq.await_count == 2
    assert out["scheduled"] == 2


@pytest.mark.asyncio
async def test_pool_auto_enrich_skips_lead_with_running_run():
    from app.enrichment import tasks as t

    fake_leads = [MagicMock(id=uuid.uuid4())]
    with patch.object(
        t, "get_pool_leads_needing_enrichment",
        new=AsyncMock(return_value=fake_leads),
    ):
        with patch.object(t, "_enqueue_lightweight_enrich", new=AsyncMock()) as enq:
            with patch.object(t, "_running_run_exists", new=AsyncMock(return_value=True)):
                with patch.object(t, "_build_task_engine_and_factory", new=_fake_engine_factory):
                    out = await t._run_pool_auto_enrich_batch(limit=20)

    enq.assert_not_awaited()
    assert out["scheduled"] == 0
