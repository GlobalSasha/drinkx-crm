"""Sprint 3.6 G1 — LeadOut source/UTM enrichment tests.

Mirrors the mock-stubbed sqlalchemy pattern from test_webforms.py so the
test suite doesn't pull the declarative base. Covers:
  - `parse_form_slug_from_source` returns the slug or None
  - `resolve_form_for_source` returns (id, name) for a known slug, None
    for an unknown one
  - `latest_form_utm_for_lead` returns the most recent
    `form_submission` Activity's payload_json['utm'] or None
  - batched helpers `_resolve_forms_batch` and `_latest_utms_batch`
"""
from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# Reuse the sqlalchemy stub helper from test_webforms.py
from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

# `repositories.py` imports `defer` from `sqlalchemy.orm`; the shared
# stub doesn't include it (it was added after test_webforms.py shipped).
# Patch it here so we don't need to touch test_webforms.py.
_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _Callable:  # minimal duplicate of the stub's _Callable
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return type(self)()
        def __getattr__(self, name): return type(self)()
    _sa_orm.defer = _Callable()


def test_parse_form_slug_from_source_prefix():
    from app.leads import repositories as repo

    assert repo.parse_form_slug_from_source("form:horeca-msk") == "horeca-msk"
    assert repo.parse_form_slug_from_source("form:") is None
    assert repo.parse_form_slug_from_source(None) is None
    assert repo.parse_form_slug_from_source("manual") is None
    assert repo.parse_form_slug_from_source("import_csv") is None


@pytest.mark.asyncio
async def test_resolve_form_for_source_returns_id_and_name():
    from app.leads import repositories as repo

    form_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        first=lambda: (form_id, "HoReCa МСК"),
    )

    out = await repo.resolve_form_for_source(db, "form:horeca-msk")

    assert out == (form_id, "HoReCa МСК")


@pytest.mark.asyncio
async def test_resolve_form_for_source_returns_none_for_non_form_source():
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock()
    out = await repo.resolve_form_for_source(db, "manual")

    assert out is None
    db.execute.assert_not_awaited()  # short-circuit, no DB hit


@pytest.mark.asyncio
async def test_latest_form_utm_for_lead_returns_dict():
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        scalar_one_or_none=lambda: {
            "utm": {"utm_source": "vk", "utm_campaign": "horeca-q3"}
        },
    )

    out = await repo.latest_form_utm_for_lead(db, lead_id)

    assert out == {"utm_source": "vk", "utm_campaign": "horeca-q3"}


@pytest.mark.asyncio
async def test_latest_form_utm_for_lead_returns_none_when_no_activity():
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        scalar_one_or_none=lambda: None,
    )

    out = await repo.latest_form_utm_for_lead(db, lead_id)

    assert out is None


def test_lead_out_schema_has_new_fields():
    """Sanity: LeadOut and LeadListItemOut both declare source_form_id,
    source_form_name, and latest_utm so list endpoints don't silently
    strip the values."""
    from app.leads.schemas import LeadListItemOut, LeadOut

    for schema_cls in (LeadOut, LeadListItemOut):
        fields = schema_cls.model_fields
        assert "source_form_id" in fields, f"{schema_cls.__name__} missing source_form_id"
        assert "source_form_name" in fields, f"{schema_cls.__name__} missing source_form_name"
        assert "latest_utm" in fields, f"{schema_cls.__name__} missing latest_utm"


@pytest.mark.asyncio
async def test_resolve_forms_batch_returns_map():
    """Batched form resolver returns {slug: (id, name)} for matching rows."""
    from app.leads import repositories as repo

    form_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        all=lambda: [("horeca-msk", form_id, "HoReCa МСК")],
    )

    result = await repo._resolve_forms_batch(db, ["horeca-msk"])

    assert result == {"horeca-msk": (form_id, "HoReCa МСК")}


@pytest.mark.asyncio
async def test_resolve_forms_batch_empty_slugs_skips_db():
    """Batched form resolver short-circuits on empty slug list."""
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock()

    result = await repo._resolve_forms_batch(db, [])

    assert result == {}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_latest_utms_batch_returns_map():
    """Batched UTM fetcher returns {lead_id: utm_dict} for matching rows."""
    from app.leads import repositories as repo

    lead_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock(
        all=lambda: [(lead_id, {"utm": {"utm_source": "vk", "utm_campaign": "q3"}})],
    )

    result = await repo._latest_utms_batch(db, [lead_id])

    assert result == {lead_id: {"utm_source": "vk", "utm_campaign": "q3"}}


@pytest.mark.asyncio
async def test_latest_utms_batch_empty_ids_skips_db():
    """Batched UTM fetcher short-circuits on empty lead_id list."""
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock()

    result = await repo._latest_utms_batch(db, [])

    assert result == {}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_leads_form_id_filter_short_circuits_for_unknown_form():
    """If form_id is given but doesn't resolve to a slug, list_leads
    returns empty without querying leads — saves a useless full scan."""
    from app.leads import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock()
    # First call: slug lookup → returns None (form deleted)
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    rows, total = await repo.list_leads(
        db,
        workspace_id=uuid.uuid4(),
        form_id=uuid.uuid4(),
    )

    assert rows == []
    assert total == 0
