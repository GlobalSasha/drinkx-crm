"""Tests for app.import_export.adapters.bitrix24 — Sprint 2.1 G4.

Mock-only. SQLAlchemy is stubbed at import time (transitive via
parsers → models). Adapter functions themselves are pure (no DB,
no network), so the heavy stub burden is just to let `models.py`
import its enum without hitting the declarative base.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports (transitive via parsers.py → models.py)
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

from app.import_export.adapters.bitrix24 import (  # noqa: E402
    apply_bitrix24_mapping,
    is_bitrix24,
    parse_bitrix24,
)


# ===========================================================================
# is_bitrix24
# ===========================================================================

def test_is_bitrix24_returns_true_for_known_headers():
    """Mix of mapped + ignored Bitrix24-native columns → True. The export
    shape we want to recognise even when the manager hasn't checked the
    fancy columns."""
    headers = ["ID", "Название", "Телефон", "EMAIL", "Сумма", "Стадия"]
    assert is_bitrix24(headers) is True


def test_is_bitrix24_returns_false_for_generic_headers():
    """Native English / non-Bitrix24 CSV → False. None of these match
    the Bitrix24 catalog, so the upload routes to generic suggest_mapping."""
    headers = ["Company", "Phone", "Revenue", "Region"]
    assert is_bitrix24(headers) is False


def test_is_bitrix24_threshold_requires_3_matches():
    """Single Bitrix24-shaped header doesn't flip the auto-detect — that
    would over-claim ownership of generic Russian CSVs that happen to
    have one column called «Название»."""
    headers = ["Название", "XYZ", "ABC"]
    assert is_bitrix24(headers) is False


# ===========================================================================
# apply_bitrix24_mapping
# ===========================================================================

def test_apply_bitrix24_mapping_known_fields():
    """Direct hits in BITRIX24_FIELD_MAP → canonical Lead field keys."""
    mapping = apply_bitrix24_mapping(["Название", "Телефон", "EMAIL"])
    assert mapping["Название"] == "company_name"
    assert mapping["Телефон"] == "phone"
    assert mapping["EMAIL"] == "email"


def test_apply_bitrix24_mapping_ignored_fields_return_none():
    """Bitrix24-native bookkeeping columns we deliberately don't import
    — every one returns None (no fall-through to fuzzy mapper)."""
    mapping = apply_bitrix24_mapping(["ID", "Ответственный", "Стадия"])
    assert mapping == {"ID": None, "Ответственный": None, "Стадия": None}


def test_apply_bitrix24_mapping_unknown_falls_back_to_suggest():
    """«Сайт компании» isn't an exact key in BITRIX24_FIELD_MAP, but the
    generic mapper has it as an alias of `website` — fallback should
    catch it. This is the path workspaces hit when they renamed
    columns at export time."""
    mapping = apply_bitrix24_mapping(["Сайт компании"])
    assert mapping["Сайт компании"] == "website"


# ===========================================================================
# parse_bitrix24
# ===========================================================================

_BITRIX_HEADERS = "ID;Название;Телефон;EMAIL;Сумма;Стадия"
_BITRIX_ROW = "1;Stars Coffee;+7 999 123-45-67;hi@stars.ru;250000;Новая"


def test_parse_bitrix24_utf8():
    """UTF-8 export — the modern default. Headers + first row land
    decoded with no error."""
    csv = (_BITRIX_HEADERS + "\n" + _BITRIX_ROW + "\n").encode("utf-8")
    result = parse_bitrix24(csv)
    assert result.error is None
    assert "Название" in result.headers
    assert "EMAIL" in result.headers
    assert len(result.rows) == 1
    assert result.rows[0]["Название"] == "Stars Coffee"


def test_parse_bitrix24_cp1251():
    """CP1251 export — older Bitrix24 / Windows-Excel default. The same
    Cyrillic headers must come through correctly without UnicodeError."""
    csv = (_BITRIX_HEADERS + "\n" + _BITRIX_ROW + "\n").encode("cp1251")
    result = parse_bitrix24(csv)
    assert result.error is None
    assert "Название" in result.headers
    assert result.rows[0]["Название"] == "Stars Coffee"


# ===========================================================================
# End-to-end: parse → is_bitrix24 → apply_bitrix24_mapping
# ===========================================================================

def test_parse_bitrix24_auto_detected_in_upload():
    """The full chain that the upload router runs when a CSV arrives
    without `?format=bitrix24`: parse → is_bitrix24 → apply mapping.
    Verifies that diff_json.suggested_mapping ends up with canonical
    keys for the recognised columns and None for the bookkeeping ones."""
    csv = (_BITRIX_HEADERS + "\n" + _BITRIX_ROW + "\n").encode("utf-8")

    parsed = parse_bitrix24(csv)
    assert parsed.error is None
    assert is_bitrix24(parsed.headers) is True

    mapping = apply_bitrix24_mapping(parsed.headers)
    assert mapping["Название"] == "company_name"
    assert mapping["Телефон"] == "phone"
    assert mapping["EMAIL"] == "email"
    assert mapping["Сумма"] == "deal_amount"
    assert mapping["ID"] is None
    assert mapping["Стадия"] is None
