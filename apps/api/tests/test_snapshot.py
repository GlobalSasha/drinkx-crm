"""Tests for the AI bulk-update snapshot generator + prompt endpoint
— Sprint 2.1 G8.

Mock-only. SQLAlchemy stubbed at import time; the snapshot helpers are
pure transforms over Lead-like objects so we hand-roll the lead/contact
fixtures with `type(...)` instead of fighting MagicMock for attribute
access.
"""
from __future__ import annotations

import sys
import uuid
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# sqlalchemy stub
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
        "desc", "false", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name):
            return _Callable
    sa.func = _Func()

    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")
    sa_ext = ModuleType("sqlalchemy.ext")
    sa_dialects = ModuleType("sqlalchemy.dialects")

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

    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa_ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa_async
    sys.modules["sqlalchemy.dialects"] = sa_dialects
    sys.modules["sqlalchemy.dialects.postgresql"] = sa_pg
    sys.modules["sqlalchemy.orm"] = sa_orm

    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = ModuleType("asyncpg")


_stub_sqlalchemy()

import app.import_export.snapshot as snapshot_mod  # noqa: E402
import app.import_export.routers as routers_mod  # noqa: E402
from app.import_export.bulk_update_prompt import BULK_UPDATE_PROMPT  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()


def _contact(
    *,
    name="Иван Иванов",
    title="CEO",
    email="ivan@stars.ru",
    phone="",
    role_type="economic_buyer",
    confidence="high",
    verified_status="verified",
):
    return type("ContactStub", (), {
        "name": name,
        "title": title,
        "email": email,
        "phone": phone,
        "role_type": role_type,
        "confidence": confidence,
        "verified_status": verified_status,
    })()


def _lead(
    *,
    company_name="Stars Coffee",
    inn="9705131922",
    segment="horeca",
    city="Москва",
    priority="A",
    fit_score=Decimal("8.5"),
    tags=None,
    ai_data=None,
    contacts=None,
    stage_id=None,
):
    return type("LeadStub", (), {
        "id": uuid.uuid4(),
        "company_name": company_name,
        "inn": inn,
        "segment": segment,
        "city": city,
        "priority": priority,
        "fit_score": fit_score,
        "tags_json": tags if tags is not None else [],
        "ai_data": ai_data,
        "contacts": contacts if contacts is not None else [],
        "stage_id": stage_id or uuid.uuid4(),
        "workspace_id": WS,
    })()


def _stub_session_for(leads):
    """AsyncSession.execute returns the leads on first call, an empty
    stage-lookup result on the second. Mirrors the two SELECTs in
    `generate_snapshot`."""
    db = AsyncMock()

    leads_result = MagicMock()
    leads_scalars = MagicMock()
    leads_scalars.unique.return_value = iter(leads)
    leads_result.scalars = MagicMock(return_value=leads_scalars)

    stage_result = MagicMock()
    stage_result.all = MagicMock(return_value=[])

    db.execute = AsyncMock(side_effect=[leads_result, stage_result])
    return db


# ===========================================================================
# 1. Snapshot includes the basic field set
# ===========================================================================

@pytest.mark.asyncio
async def test_snapshot_includes_basic_fields():
    """Each lead surfaces with company_name, inn, segment, city, stage,
    priority, fit_score, tags, contacts. ID is included so the diff engine
    can match by `match_by: id` if INN is missing on the AI side."""
    lead = _lead()
    db = _stub_session_for([lead])

    out = await snapshot_mod.generate_snapshot(
        db, workspace_id=WS, include_ai_brief=False
    )
    parsed = yaml.safe_load(out.decode("utf-8"))
    assert "leads" in parsed
    assert len(parsed["leads"]) == 1
    item = parsed["leads"][0]

    assert item["company_name"] == "Stars Coffee"
    assert item["inn"] == "9705131922"
    assert item["segment"] == "horeca"
    assert item["city"] == "Москва"
    assert item["priority"] == "A"
    # Decimal coerced to float for YAML safety
    assert isinstance(item["fit_score"], float)
    assert item["fit_score"] == 8.5
    assert "id" in item
    assert "tags" in item
    assert "contacts" in item


# ===========================================================================
# 2. Snapshot includes ai_brief when requested
# ===========================================================================

@pytest.mark.asyncio
async def test_snapshot_includes_ai_brief_when_requested():
    lead = _lead(
        ai_data={
            "company_profile": "Сеть кофеен, 50+ точек.",
            "growth_signals": ["Новая точка в Дубае"],
            "risk_signals": [],
            "next_steps": ["Связаться с CEO"],
            # extra noise we don't want in the snapshot
            "urgency": "high",
            "sources_used": ["brave"],
        }
    )
    db = _stub_session_for([lead])

    out = await snapshot_mod.generate_snapshot(
        db, workspace_id=WS, include_ai_brief=True
    )
    parsed = yaml.safe_load(out.decode("utf-8"))
    item = parsed["leads"][0]

    assert "ai_brief" in item
    brief = item["ai_brief"]
    assert brief["company_profile"] == "Сеть кофеен, 50+ точек."
    assert brief["growth_signals"] == ["Новая точка в Дубае"]
    assert brief["next_steps"] == ["Связаться с CEO"]
    # urgency / sources_used are deliberately stripped — external LLM
    # doesn't need our internal scoring metadata
    assert "urgency" not in brief
    assert "sources_used" not in brief


# ===========================================================================
# 3. Snapshot omits ai_brief when not requested
# ===========================================================================

@pytest.mark.asyncio
async def test_snapshot_excludes_ai_brief_when_not_requested():
    lead = _lead(
        ai_data={"company_profile": "should not appear"},
    )
    db = _stub_session_for([lead])

    out = await snapshot_mod.generate_snapshot(
        db, workspace_id=WS, include_ai_brief=False
    )
    parsed = yaml.safe_load(out.decode("utf-8"))
    assert "ai_brief" not in parsed["leads"][0]


# ===========================================================================
# 4. Snapshot only includes verified contacts
# ===========================================================================

@pytest.mark.asyncio
async def test_snapshot_only_includes_verified_contacts():
    """High-confidence verified contact passes the filter; low-confidence
    one (the spec's `confidence=0.1` shape, mapped to our enum 'low')
    is dropped."""
    good = _contact(
        name="Мария Иванова",
        confidence="high",
        verified_status="verified",
    )
    bad = _contact(
        name="Случайный человек",
        confidence="low",
        verified_status="to_verify",
    )
    lead = _lead(contacts=[good, bad])
    db = _stub_session_for([lead])

    out = await snapshot_mod.generate_snapshot(
        db, workspace_id=WS, include_ai_brief=False
    )
    parsed = yaml.safe_load(out.decode("utf-8"))
    contacts = parsed["leads"][0]["contacts"]
    names = [c["name"] for c in contacts]
    assert "Мария Иванова" in names
    assert "Случайный человек" not in names
    assert len(contacts) == 1


# ===========================================================================
# 5. Output is valid YAML
# ===========================================================================

@pytest.mark.asyncio
async def test_snapshot_valid_yaml():
    """yaml.safe_load roundtrips without exceptions and yields a dict
    with the expected top-level shape."""
    lead = _lead()
    db = _stub_session_for([lead])

    out = await snapshot_mod.generate_snapshot(
        db, workspace_id=WS, include_ai_brief=True
    )
    parsed = yaml.safe_load(out.decode("utf-8"))
    assert isinstance(parsed, dict)
    assert "leads" in parsed
    assert isinstance(parsed["leads"], list)


# ===========================================================================
# 6. Prompt endpoint
# ===========================================================================

@pytest.mark.asyncio
async def test_bulk_update_prompt_endpoint_returns_string():
    """GET /api/export/bulk-update-prompt returns the canonical prompt
    in a JSON envelope. Length sanity-check ensures we didn't ship an
    accidentally-empty constant."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.workspace_id = WS

    result = await routers_mod.get_bulk_update_prompt(user=user)
    assert isinstance(result, dict)
    assert "prompt" in result
    assert isinstance(result["prompt"], str)
    assert len(result["prompt"]) > 100
    assert result["prompt"] == BULK_UPDATE_PROMPT
