"""Tests for the AI bulk-update parser + diff engine + apply
— Sprint 2.1 G9.

Mock-only. SQLAlchemy stubbed at import time. The diff engine touches
sessions and ORM classes — we mock execute() side-effect lists for
matcher resolution and patch Lead/Contact ORM classes for apply.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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

import app.import_export.adapters.bulk_update as bu_mod  # noqa: E402
import app.import_export.diff_engine as diff_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WS = uuid.uuid4()


def _lead(*, id_=None, company_name="Stars Coffee", inn="9705131922",
          ai_data=None, tags=None, contacts=None, pipeline_id=None,
          stage_id=None):
    return type("LeadStub", (), {
        "id": id_ or uuid.uuid4(),
        "workspace_id": WS,
        "company_name": company_name,
        "inn": inn,
        "ai_data": ai_data,
        "tags_json": tags if tags is not None else [],
        "contacts": contacts if contacts is not None else [],
        "pipeline_id": pipeline_id,
        "stage_id": stage_id,
        "assigned_to": None,
    })()


def _scalars_unique(items):
    """Helper to build the scalars().unique() chain that compute_diff calls."""
    inner = MagicMock()
    inner.unique = MagicMock(return_value=iter(items))
    return inner


def _result_with_leads(items):
    r = MagicMock()
    r.scalars = MagicMock(return_value=_scalars_unique(items))
    return r


# ===========================================================================
# 1. is_bulk_update_yaml — true case
# ===========================================================================

def test_is_bulk_update_yaml_true():
    """File with both `format: drinkx-crm-update` and `updates:` triggers
    auto-detect. Quotes and casing tolerated."""
    payload = b"""format: drinkx-crm-update
version: "1.0"
updates:
  - action: update
    company:
      inn: "1234567890"
"""
    assert bu_mod.is_bulk_update_yaml(payload) is True


# ===========================================================================
# 2. is_bulk_update_yaml — false on regular YAML
# ===========================================================================

def test_is_bulk_update_yaml_false_for_regular_yaml():
    payload = b"""leads:
  - company_name: Stars
    inn: "1234567890"
"""
    assert bu_mod.is_bulk_update_yaml(payload) is False


# ===========================================================================
# 3. parse_bulk_update — drops 'skip' rows
# ===========================================================================

def test_parse_bulk_update_returns_non_skip_items():
    payload = b"""format: drinkx-crm-update
updates:
  - action: update
    company: {inn: "111"}
    fields: {tags: {add: ["x"]}}
  - action: skip
    company: {inn: "222"}
  - action: create
    company: {name: New Co}
"""
    items = bu_mod.parse_bulk_update(payload)
    assert len(items) == 2
    assert items[0]["action"] == "update"
    assert items[1]["action"] == "create"


# ===========================================================================
# 4. parse_bulk_update — drops invalid actions / shapes
# ===========================================================================

def test_parse_bulk_update_filters_invalid_action():
    """Rows with action='delete' or no company info are silently dropped
    so a malformed AI response doesn't poison the diff."""
    payload = b"""format: drinkx-crm-update
updates:
  - action: delete
    company: {inn: "111"}
  - action: update
    company: {}
  - action: update
    company: {inn: "222"}
    fields: {}
"""
    items = bu_mod.parse_bulk_update(payload)
    # Only the third entry survives (the only one with company.inn AND
    # a valid action)
    assert len(items) == 1
    assert items[0]["company"]["inn"] == "222"


# ===========================================================================
# 5. compute_diff — match by INN
# ===========================================================================

@pytest.mark.asyncio
async def test_compute_diff_matches_by_inn():
    """An existing lead with matching INN gets resolved; the diff item
    carries `lead_id` + `match_confidence='exact_inn'`."""
    lead = _lead(inn="1111111111", ai_data={"growth_signals": ["existing"]})
    db = AsyncMock()
    # Three execute calls in compute_diff (inn / name / id batches);
    # we only have inn-keyed updates so only the first returns hits.
    db.execute = AsyncMock(side_effect=[
        _result_with_leads([lead]),  # inn batch
        _result_with_leads([]),      # name batch
        _result_with_leads([]),      # id batch
    ])

    updates = [{
        "action": "update",
        "match_by": "inn",
        "company": {"name": "Stars", "inn": "1111111111"},
        "fields": {"ai_data": {"fit_score": 9}},
    }]
    diff = await diff_mod.compute_diff(db, workspace_id=WS, updates=updates)
    assert len(diff) == 1
    assert diff[0].action == "update"
    assert diff[0].match_confidence == "exact_inn"
    assert diff[0].lead_id == str(lead.id)
    assert diff[0].error is None
    # fit_score change captured
    assert any(c.field == "ai_data.fit_score" for c in diff[0].changes)


# ===========================================================================
# 6. compute_diff — error when not found
# ===========================================================================

@pytest.mark.asyncio
async def test_compute_diff_returns_error_for_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result_with_leads([]),
        _result_with_leads([]),
        _result_with_leads([]),
    ])

    updates = [{
        "action": "update",
        "match_by": "inn",
        "company": {"name": "Ghost", "inn": "9999999999"},
        "fields": {},
    }]
    diff = await diff_mod.compute_diff(db, workspace_id=WS, updates=updates)
    assert len(diff) == 1
    assert diff[0].error is not None
    assert diff[0].lead_id is None
    assert diff[0].match_confidence == "not_found"


# ===========================================================================
# 7. compute_diff — error when ambiguous
# ===========================================================================

@pytest.mark.asyncio
async def test_compute_diff_returns_error_for_ambiguous():
    """Two leads share the same INN — manager has to pick manually
    rather than us guessing wrong."""
    a = _lead(company_name="Stars #1", inn="2222222222")
    b = _lead(company_name="Stars #2", inn="2222222222")
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result_with_leads([a, b]),
        _result_with_leads([]),
        _result_with_leads([]),
    ])

    updates = [{
        "action": "update",
        "match_by": "inn",
        "company": {"name": "Stars", "inn": "2222222222"},
        "fields": {},
    }]
    diff = await diff_mod.compute_diff(db, workspace_id=WS, updates=updates)
    assert len(diff) == 1
    assert diff[0].error is not None
    assert diff[0].match_confidence == "ambiguous"


# ===========================================================================
# 8. compute_diff — action=create when not found
# ===========================================================================

@pytest.mark.asyncio
async def test_compute_diff_create_when_not_found_and_action_create():
    """`action: create` against a non-matching company — emits a
    DiffItem with action='create', lead_id=None, no error."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result_with_leads([]),
        _result_with_leads([]),
        _result_with_leads([]),
    ])

    updates = [{
        "action": "create",
        "match_by": "inn",
        "company": {"name": "New Co", "inn": "3333333333"},
        "fields": {"tags": {"add": ["new"]}},
    }]
    diff = await diff_mod.compute_diff(db, workspace_id=WS, updates=updates)
    assert len(diff) == 1
    assert diff[0].action == "create"
    assert diff[0].lead_id is None
    assert diff[0].error is None


# ===========================================================================
# 9. apply — ai_data.growth_signals merge (add + dedup)
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_diff_update_merges_growth_signals():
    """Existing growth_signals stay, new ones are appended, dupes
    deduped."""
    lead = _lead(ai_data={"growth_signals": ["existing"]})
    item = diff_mod.DiffItem(
        action="update",
        company_name="Stars",
        inn="1",
        lead_id=str(lead.id),
        match_confidence="exact_inn",
        changes=[
            diff_mod.Change(
                field="ai_data.growth_signals",
                op="add",
                value=["existing", "open in Dubai 2026"],
                current_value=["existing"],
            ),
        ],
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=lead)

    ok = await diff_mod.apply_diff_item(
        db, item=item, workspace_id=WS, user_id=uuid.uuid4()
    )
    assert ok is True
    assert lead.ai_data["growth_signals"] == ["existing", "open in Dubai 2026"]


# ===========================================================================
# 10. apply — ai_data.fit_score replace (set op)
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_diff_update_replaces_fit_score():
    """Scalar fields (fit_score, company_profile) use op='set' which
    overwrites the existing value."""
    lead = _lead(ai_data={"fit_score": 6})
    item = diff_mod.DiffItem(
        action="update",
        company_name="Stars",
        inn="1",
        lead_id=str(lead.id),
        match_confidence="exact_inn",
        changes=[
            diff_mod.Change(
                field="ai_data.fit_score",
                op="set",
                value=9,
                current_value=6,
            ),
        ],
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=lead)

    ok = await diff_mod.apply_diff_item(
        db, item=item, workspace_id=WS, user_id=uuid.uuid4()
    )
    assert ok is True
    assert lead.ai_data["fit_score"] == 9


# ===========================================================================
# 11. apply — action=create constructs a Lead
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_diff_create_makes_lead():
    """`action=create` → Lead constructor called with workspace + name +
    inn + assignment_status='pool'. Fields from changes (tags / ai_data)
    are applied against the fresh row."""
    item = diff_mod.DiffItem(
        action="create",
        company_name="New Brewers",
        inn="4444444444",
        lead_id=None,
        match_confidence="not_found",
        changes=[
            diff_mod.Change(field="tags", op="add", value=["import-2026"]),
        ],
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()

    captured: list[dict] = []

    class _LeadSpy:
        def __init__(self, **kw):
            captured.append(kw)
            self.id = uuid.uuid4()
            # Match real Lead defaults — diff engine reads these
            # immediately after construction.
            self.ai_data = None
            self.tags_json = list(kw.get("tags_json") or [])
            self.contacts = []
            for k, v in kw.items():
                setattr(self, k, v)

    fake_pipelines_repo = MagicMock()
    fake_pipelines_repo.get_default_first_stage = AsyncMock(
        return_value=(uuid.uuid4(), uuid.uuid4())
    )
    pipelines_module = ModuleType("app.pipelines")
    repos_module = ModuleType("app.pipelines.repositories")
    repos_module.get_default_first_stage = (
        fake_pipelines_repo.get_default_first_stage
    )
    pipelines_module.repositories = repos_module

    with patch.object(diff_mod, "Lead", _LeadSpy), \
         patch.dict(sys.modules, {
             "app.pipelines": pipelines_module,
             "app.pipelines.repositories": repos_module,
         }):
        ok = await diff_mod.apply_diff_item(
            db, item=item, workspace_id=WS, user_id=uuid.uuid4()
        )

    assert ok is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["workspace_id"] == WS
    assert kw["company_name"] == "New Brewers"
    assert kw["inn"] == "4444444444"
    assert kw["assignment_status"] == "pool"
    assert kw["source"] == "ai_bulk_update"
