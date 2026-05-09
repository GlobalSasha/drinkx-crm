"""Tests for app.import_export.{exporters,routers,services} export path
— Sprint 2.1 G6.

Mock-only. SQLAlchemy is stubbed at import time so the module-level
ORM imports don't trigger declarative-base setup. The export endpoint
tests use the same harness pattern as Sprint 2.0 inbox tests
(test_inbox_services.py): import the FastAPI route handler directly,
patch service helpers + the Celery dispatch.

`openpyxl` and `pyyaml` are real runtime requirements — pytest.importorskip
keeps the suite collectable in environments where those aren't pinned.
"""
from __future__ import annotations

import io
import json
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports
# ---------------------------------------------------------------------------

def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return

    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getitem__(self, key): return _Callable()
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
        def __getitem__(self, key): return _Callable()

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

import app.import_export.exporters as exporters_mod  # noqa: E402
import app.import_export.routers as routers_mod  # noqa: E402
import app.import_export.services as svc_mod  # noqa: E402
from app.import_export.exporters import (  # noqa: E402
    AI_BRIEF_COLUMN,
    EXPORT_FIELDS,
    export_csv,
    export_json,
    export_md_zip,
    export_xlsx,
    export_yaml,
    leads_to_rows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lead(**overrides):
    """Plain object that mirrors the Lead ORM attribute surface the
    exporters touch. MagicMock would synthesize any attribute access
    which makes assertions slippery."""
    base = {
        "id": uuid.uuid4(),
        "company_name": "Stars Coffee",
        "segment": "HoReCa",
        "city": "Москва",
        "email": "hi@stars.ru",
        "phone": "+7 999 123-45-67",
        "website": "stars.ru",
        "inn": "1234567890",
        "deal_amount": "1500000",
        "priority": "A",
        "deal_type": "enterprise_direct",
        "source": "import",
        "tags_json": ["hot", "vip"],
        "stage_id": uuid.uuid4(),
        "assigned_to": uuid.uuid4(),
        "fit_score": 8.5,
        "created_at": datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
        "ai_data": {"company_profile": "Сеть кофеен с упором на лояльность."},
    }
    base.update(overrides)
    return type("LeadStub", (), base)()


# ===========================================================================
# 1. leads_to_rows — basic field projection
# ===========================================================================

def test_leads_to_rows_basic_fields():
    """Every EXPORT_FIELDS key shows up in the row, with the source value
    (or "" / iso-string for None / datetime). No surprise nesting."""
    lead = _make_lead()
    rows = leads_to_rows([lead])
    assert len(rows) == 1
    row = rows[0]
    assert row["company_name"] == "Stars Coffee"
    assert row["segment"] == "HoReCa"
    assert row["city"] == "Москва"
    assert row["email"] == "hi@stars.ru"
    assert row["fit_score"] == "8.5"
    # All canonical fields present so downstream encoders never KeyError
    for f in EXPORT_FIELDS:
        assert f in row


# ===========================================================================
# 2. tags_json flattening
# ===========================================================================

def test_leads_to_rows_tags_json_flattened():
    """Lead.tags_json is a Python list — encoders need a flat string."""
    lead = _make_lead(tags_json=["hot", "vip"])
    rows = leads_to_rows([lead])
    assert rows[0]["tags_json"] == "hot, vip"


# ===========================================================================
# 3. CSV — UTF-8 BOM
# ===========================================================================

def test_export_csv_has_bom():
    """Excel double-clicks Cyrillic CSVs as garbage without the BOM —
    we always prepend it so the manager doesn't have to hand-import."""
    rows = leads_to_rows([_make_lead()])
    out = export_csv(rows)
    assert out[:3] == b"\xef\xbb\xbf"


# ===========================================================================
# 4. CSV — column headers present
# ===========================================================================

def test_export_csv_column_headers():
    """All canonical fields appear in the header row, regardless of
    whether any row had a value for them."""
    rows = leads_to_rows([_make_lead()])
    out = export_csv(rows).decode("utf-8-sig")
    header_line = out.splitlines()[0]
    for f in EXPORT_FIELDS:
        assert f in header_line


# ===========================================================================
# 5. JSON — valid
# ===========================================================================

def test_export_json_valid_json():
    """json.loads round-trips and yields a list of objects matching
    the rows we passed in."""
    rows = leads_to_rows([_make_lead(), _make_lead(company_name="Surf")])
    out = export_json(rows)
    parsed = json.loads(out.decode("utf-8"))
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[1]["company_name"] == "Surf"


# ===========================================================================
# 6. YAML — valid
# ===========================================================================

def test_export_yaml_valid_yaml():
    """yaml.safe_load reads it back without raising; allow_unicode kept
    Cyrillic intact (Москва survives the round-trip)."""
    yaml_mod = pytest.importorskip("yaml")

    rows = leads_to_rows([_make_lead()])
    out = export_yaml(rows)
    parsed = yaml_mod.safe_load(out.decode("utf-8"))
    assert isinstance(parsed, list)
    assert parsed[0]["city"] == "Москва"


# ===========================================================================
# 7. XLSX — bytes, non-empty
# ===========================================================================

def test_export_xlsx_returns_bytes():
    pytest.importorskip("openpyxl")

    rows = leads_to_rows([_make_lead(), _make_lead(company_name="Surf")])
    out = export_xlsx(rows)
    assert isinstance(out, bytes)
    assert len(out) > 0
    # XLSX is a ZIP under the hood — first two bytes are 'PK'
    assert out[:2] == b"PK"


# ===========================================================================
# 8. MD ZIP — one .md per lead
# ===========================================================================

def test_export_md_zip_contains_md_files():
    """Each lead produces exactly one .md entry inside the ZIP. The
    body carries the AI Brief section so this format is the natural
    'human-readable export with everything'."""
    leads = [
        _make_lead(),
        _make_lead(company_name="Surf Coffee", inn="9876543210"),
    ]
    out = export_md_zip(leads)
    assert isinstance(out, bytes)

    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        names = zf.namelist()
        assert len(names) == len(leads)
        for n in names:
            assert n.endswith(".md")
        # Spot-check a body
        body = zf.read(names[0]).decode("utf-8")
        assert "# " in body  # markdown title present
        assert "AI Brief" in body


# ===========================================================================
# 9. POST /api/export → 202 + status='pending'
# ===========================================================================

@pytest.mark.asyncio
async def test_export_endpoint_returns_202():
    """create_export persists the row, dispatches Celery best-effort,
    and returns the synthetic ExportJobOut with status='pending'."""
    from app.import_export.schemas import ExportRequestIn

    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.workspace_id = uuid.uuid4()

    fake_job = MagicMock()
    fake_job.id = uuid.uuid4()
    fake_job.workspace_id = user.workspace_id
    fake_job.user_id = user.id
    fake_job.status = "pending"
    fake_job.format = "csv"
    fake_job.row_count = None
    fake_job.error = None
    fake_job.created_at = datetime.now(tz=timezone.utc)
    fake_job.finished_at = None

    fake_celery_module = ModuleType("app.scheduled.celery_app")
    fake_celery_module.celery_app = MagicMock()
    fake_celery_module.celery_app.send_task = MagicMock()

    with patch.object(
        svc_mod, "create_export_job", new=AsyncMock(return_value=fake_job)
    ) as create_mock, patch.dict(
        sys.modules, {"app.scheduled.celery_app": fake_celery_module}
    ):
        result = await routers_mod.create_export(
            payload=ExportRequestIn(format="csv", filters={"city": "Москва"}),
            db=db,
            user=user,
        )

    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["workspace_id"] == user.workspace_id
    assert kwargs["format_value"] == "csv"
    assert kwargs["filters"] == {"city": "Москва"}

    fake_celery_module.celery_app.send_task.assert_called_once()
    args, _ = fake_celery_module.celery_app.send_task.call_args
    assert args[0] == "app.scheduled.jobs.run_export"

    assert result.status == "pending"
    assert result.format == "csv"
    assert result.download_url is None  # synthetic field stays None until done


# ===========================================================================
# 10. GET /api/export/{id}/download → 410 when Redis lost the payload
# ===========================================================================

@pytest.mark.asyncio
async def test_download_returns_410_when_redis_expired():
    """job.status='done' but Redis lost the bytes (TTL expired) →
    HTTP 410 (Gone), NOT 500. Manager gets a clear path to retry."""
    from fastapi import HTTPException

    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    user.workspace_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with patch.object(
        svc_mod,
        "fetch_export_payload",
        new=AsyncMock(side_effect=svc_mod.ExportPayloadGone("redis miss")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await routers_mod.download_export(
                job_id=job_id, db=db, user=user
            )

    assert exc_info.value.status_code == 410
