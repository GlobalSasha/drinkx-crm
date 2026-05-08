"""Tests for app.pipelines.services + the Sprint 2.2 G4 carryover
in app.forms.services validation — Sprint 2.3 G1.

Mock-only: stubs sqlalchemy at import time so the ORM imports don't
drag the real declarative base in. Patches `app.pipelines.repositories`
at the function name lookup so the service surface is exercised
without a real DB.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub (matches tests/test_webforms.py)
# ---------------------------------------------------------------------------

def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return

    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True
        def __lt__(self, other): return _Callable()
        def __le__(self, other): return _Callable()
        def __gt__(self, other): return _Callable()
        def __ge__(self, other): return _Callable()

    sa = ModuleType("sqlalchemy")
    for name in (
        "Column", "ForeignKey", "Integer", "String", "Text", "JSON",
        "Numeric", "DateTime", "Boolean", "Index", "select", "func",
        "desc", "false", "true", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name): return _Callable
    sa.func = _Func()

    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")
    sa_ext = ModuleType("sqlalchemy.ext")
    sa_dialects = ModuleType("sqlalchemy.dialects")
    sa_exc = ModuleType("sqlalchemy.exc")

    class _Mapped:
        def __class_getitem__(cls, item): return cls

    class _DeclarativeBase:
        metadata = MagicMock()

    sa_orm.DeclarativeBase = _DeclarativeBase
    sa_orm.Mapped = _Mapped
    sa_orm.mapped_column = lambda *a, **kw: _Callable()
    sa_orm.relationship = _Callable()
    sa_orm.selectinload = _Callable()
    sa_orm.joinedload = _Callable()

    sa_pg.UUID = _Callable
    sa_pg.JSON = _Callable
    sa_async.AsyncSession = object
    sa_async.async_sessionmaker = _Callable
    sa_async.create_async_engine = _Callable
    sa_async.AsyncEngine = object

    class _IntegrityError(Exception):
        pass

    sa_exc.IntegrityError = _IntegrityError

    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa_ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa_async
    sys.modules["sqlalchemy.dialects"] = sa_dialects
    sys.modules["sqlalchemy.dialects.postgresql"] = sa_pg
    sys.modules["sqlalchemy.orm"] = sa_orm
    sys.modules["sqlalchemy.exc"] = sa_exc

    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = ModuleType("asyncpg")


_stub_sqlalchemy()

from app.pipelines import services as svc  # noqa: E402

WS = uuid.uuid4()
OTHER_WS = uuid.uuid4()


def _make_pipeline(*, id_=None, workspace_id=WS, name="Продажи"):
    p = MagicMock()
    p.id = id_ or uuid.uuid4()
    p.workspace_id = workspace_id
    p.name = name
    p.type = "sales"
    return p


def _stages_payload(n=3):
    return [
        {
            "name": f"Этап {i}",
            "position": i,
            "color": "#a1a1a6",
            "rot_days": 5,
            "probability": 10 + i * 10,
            "is_won": False,
            "is_lost": False,
            "gate_criteria_json": [],
        }
        for i in range(n)
    ]


# ===========================================================================
# 1. create_pipeline
# ===========================================================================

@pytest.mark.asyncio
async def test_create_pipeline_persists_via_repo():
    """create_pipeline forwards to repositories.create_pipeline with
    the caller's workspace_id + the provided name/type/stages —
    workspace_id is non-negotiable, the service NEVER takes it from
    the payload."""
    db = AsyncMock()
    captured: dict = {}

    async def fake_create(_session, **kwargs):
        captured.update(kwargs)
        return _make_pipeline(name=kwargs["name"])

    with patch("app.pipelines.repositories.create_pipeline", new=fake_create):
        p = await svc.create_pipeline(
            db,
            workspace_id=WS,
            name="Партнёры",
            type_="partner",
            stages=_stages_payload(2),
        )

    assert p.workspace_id == WS
    assert captured["workspace_id"] == WS
    assert captured["name"] == "Партнёры"
    assert captured["type_"] == "partner"
    assert len(captured["stages"]) == 2


# ===========================================================================
# 2. delete_pipeline — refuses with 409 when leads are on it
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_refuses_when_leads_on_pipeline():
    """The defensive guard should raise PipelineHasLeads (router maps
    to 409) when count_leads_on_pipeline > 0. Carries the count so
    the UI can render «Перенесите N лидов в другую воронку» without
    a second round-trip."""
    db = AsyncMock()
    pipeline = _make_pipeline()

    async def fake_get_by_id(_session, **kwargs):
        return pipeline

    async def fake_get_default_pipeline_id(_session, **kwargs):
        return uuid.uuid4()  # NOT this pipeline's id

    async def fake_count_leads(_session, **kwargs):
        return 47

    with patch("app.pipelines.repositories.get_by_id", new=fake_get_by_id), \
         patch(
            "app.pipelines.repositories.get_default_pipeline_id",
            new=fake_get_default_pipeline_id,
         ), \
         patch(
            "app.pipelines.repositories.count_leads_on_pipeline",
            new=fake_count_leads,
         ):
        with pytest.raises(svc.PipelineHasLeads) as ei:
            await svc.delete_pipeline(
                db, pipeline_id=pipeline.id, workspace_id=WS
            )
        assert ei.value.count == 47


# ===========================================================================
# 3. delete_pipeline — refuses when target is the workspace default
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_refuses_when_pipeline_is_default():
    """Deleting the current default would leave the workspace with
    `default_pipeline_id=NULL` — next /pipeline cold-load has nothing
    to land on. Force the admin to set a new default first."""
    db = AsyncMock()
    pipeline = _make_pipeline()

    async def fake_get_by_id(_session, **kwargs):
        return pipeline

    async def fake_get_default_pipeline_id(_session, **kwargs):
        return pipeline.id  # IT IS the default

    with patch("app.pipelines.repositories.get_by_id", new=fake_get_by_id), \
         patch(
            "app.pipelines.repositories.get_default_pipeline_id",
            new=fake_get_default_pipeline_id,
         ):
        with pytest.raises(svc.PipelineIsDefault):
            await svc.delete_pipeline(
                db, pipeline_id=pipeline.id, workspace_id=WS
            )


# ===========================================================================
# 4. delete_pipeline — happy path (no leads, not default)
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_happy_path_calls_hard_delete():
    """When neither guard fires, hard_delete_pipeline is invoked.
    Proof that the guards don't accidentally short-circuit a legitimate
    delete."""
    db = AsyncMock()
    pipeline = _make_pipeline()
    deleted = {"called": False}

    async def fake_get_by_id(_session, **kwargs):
        return pipeline

    async def fake_get_default_pipeline_id(_session, **kwargs):
        return uuid.uuid4()  # different pipeline is the default

    async def fake_count_leads(_session, **kwargs):
        return 0

    async def fake_hard_delete(_session, *, pipeline):
        deleted["called"] = True

    with patch("app.pipelines.repositories.get_by_id", new=fake_get_by_id), \
         patch(
            "app.pipelines.repositories.get_default_pipeline_id",
            new=fake_get_default_pipeline_id,
         ), \
         patch(
            "app.pipelines.repositories.count_leads_on_pipeline",
            new=fake_count_leads,
         ), \
         patch(
            "app.pipelines.repositories.hard_delete_pipeline",
            new=fake_hard_delete,
         ):
        await svc.delete_pipeline(
            db, pipeline_id=pipeline.id, workspace_id=WS
        )
    assert deleted["called"] is True


# ===========================================================================
# 5. set_default_pipeline rejects cross-workspace pipeline (404)
# ===========================================================================

@pytest.mark.asyncio
async def test_set_default_rejects_cross_workspace():
    """A POST /set-default with a pipeline_id that belongs to ANOTHER
    workspace must surface as PipelineNotFound — get-or-404 returns
    None on the workspace mismatch, the service never silently
    succeeds against a foreign workspace's pipeline."""
    db = AsyncMock()

    async def fake_get_by_id(_session, **kwargs):
        return None  # pipeline exists, but not in this workspace

    with patch("app.pipelines.repositories.get_by_id", new=fake_get_by_id):
        with pytest.raises(svc.PipelineNotFound):
            await svc.set_default_pipeline(
                db, pipeline_id=uuid.uuid4(), workspace_id=WS
            )


# ===========================================================================
# 6. set_default happy path — calls repo.set_default with both ids
# ===========================================================================

@pytest.mark.asyncio
async def test_set_default_happy_path_invokes_repo():
    """When the pipeline is in the workspace, set_default forwards
    BOTH the workspace_id and pipeline_id to the repo helper that
    flips the FK + maintains the legacy is_default boolean."""
    db = AsyncMock()
    pipeline = _make_pipeline()
    captured: dict = {}

    async def fake_get_by_id(_session, **kwargs):
        return pipeline

    async def fake_set_default(_session, **kwargs):
        captured.update(kwargs)

    with patch("app.pipelines.repositories.get_by_id", new=fake_get_by_id), \
         patch(
            "app.pipelines.repositories.set_default",
            new=fake_set_default,
         ):
        result = await svc.set_default_pipeline(
            db, pipeline_id=pipeline.id, workspace_id=WS
        )

    assert result is pipeline
    assert captured["workspace_id"] == WS
    assert captured["pipeline_id"] == pipeline.id


# ===========================================================================
# 7. list_pipelines passes workspace through to the repo
# ===========================================================================

@pytest.mark.asyncio
async def test_list_pipelines_scoped_to_workspace():
    """The service is a pass-through but it MUST scope by the caller's
    workspace — ensures no future caller can omit the scope and silently
    list across the boundary."""
    db = AsyncMock()
    captured: dict = {}

    async def fake_list(_session, **kwargs):
        captured.update(kwargs)
        return []

    with patch(
        "app.pipelines.repositories.list_for_workspace", new=fake_list
    ):
        rows = await svc.list_pipelines(db, workspace_id=WS)

    assert captured["workspace_id"] == WS
    assert rows == []


# ===========================================================================
# 8-9. Forms.services target validation — Sprint 2.2 G4 carryover
# ===========================================================================

@pytest.mark.asyncio
async def test_form_create_rejects_cross_workspace_pipeline():
    """create_form must raise WebFormInvalidTarget when
    target_pipeline_id belongs to a different workspace. Without this
    guard a malicious admin could craft a form whose submissions
    spill across workspaces."""
    from app.forms import services as forms_svc

    # Stub out the Pipeline import path used by _validate_target.
    pipelines_models = ModuleType("app.pipelines.models")
    pipelines_models.Pipeline = MagicMock()
    sys.modules.setdefault("app.pipelines.models", pipelines_models)

    db = AsyncMock()

    # session.execute returns a result with scalar_one_or_none → None
    # (pipeline NOT in this workspace).
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=fake_result)

    with pytest.raises(forms_svc.WebFormInvalidTarget):
        await forms_svc._validate_target(
            db,
            workspace_id=WS,
            target_pipeline_id=uuid.uuid4(),
            target_stage_id=None,
        )


@pytest.mark.asyncio
async def test_form_create_rejects_stage_not_in_pipeline():
    """A target_stage_id that belongs to a DIFFERENT pipeline
    (even within the same workspace) is also rejected. Stops a manager
    from accidentally pointing the form at a stage that won't be
    rendered as part of the chosen pipeline's board."""
    from app.forms import services as forms_svc

    db = AsyncMock()

    # Pipeline check passes — return a pipeline-id from scalar_one_or_none.
    pipeline_id = uuid.uuid4()
    pipeline_result = MagicMock()
    pipeline_result.scalar_one_or_none = MagicMock(return_value=pipeline_id)
    db.execute = AsyncMock(return_value=pipeline_result)

    async def fake_stage_belongs(_session, **kwargs):
        return False

    with patch(
        "app.pipelines.repositories.stage_belongs_to_pipeline",
        new=fake_stage_belongs,
    ):
        with pytest.raises(forms_svc.WebFormInvalidTarget):
            await forms_svc._validate_target(
                db,
                workspace_id=WS,
                target_pipeline_id=pipeline_id,
                target_stage_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_form_create_no_target_skips_validation():
    """When BOTH target fields are None the validator must short-
    circuit — the public submit endpoint will fall back to
    `get_default_first_stage`. Otherwise we'd 400-fail every form
    that opts to use the default."""
    from app.forms import services as forms_svc

    db = AsyncMock()
    db.execute = AsyncMock()

    # Should simply return without raising or hitting the DB.
    await forms_svc._validate_target(
        db,
        workspace_id=WS,
        target_pipeline_id=None,
        target_stage_id=None,
    )
    assert db.execute.await_count == 0
