"""Tests for app.import_export.{parsers, mapper, validators} — Sprint 2.1 G2.

Mock-only. parsers + mapper + validators have no DB or network deps —
they're pure functions over bytes / dicts. We stub sqlalchemy at import
time only so the `ImportJobFormat` enum import doesn't drag the
declarative base in (the rest of the import_export package depends on
it via models.py).

`openpyxl` is the only non-stdlib runtime dep; it's a hard requirement
for the XLSX test, so the suite uses pytest.importorskip.
"""
from __future__ import annotations

import io
import json
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports (transitive via models.py)
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

from app.import_export.mapper import (  # noqa: E402
    apply_mapping,
    suggest_mapping,
)
from app.import_export.models import ImportJobFormat  # noqa: E402
from app.import_export.parsers import MAX_ROWS, parse_file  # noqa: E402
from app.import_export.validators import parse_deal_amount, validate_row  # noqa: E402


# ===========================================================================
# Parsers — CSV
# ===========================================================================

def test_parse_csv_semicolon_delimiter():
    """RU-locale Excel / Bitrix24 export → semicolon delimiter."""
    content = (
        "Название;Город;Email\n"
        "Stars Coffee;Москва;hi@stars.ru\n"
        "Surf Coffee;СПб;contact@surf.io\n"
    ).encode("utf-8")

    result = parse_file(content, "leads.csv", ImportJobFormat.csv)
    assert result.error is None
    assert result.headers == ["Название", "Город", "Email"]
    assert len(result.rows) == 2
    assert result.rows[0] == {
        "Название": "Stars Coffee",
        "Город": "Москва",
        "Email": "hi@stars.ru",
    }


def test_parse_csv_comma_delimiter():
    """Native English CSV → comma delimiter."""
    content = (
        "company_name,city,email\n"
        "Acme,SF,sales@acme.io\n"
    ).encode("utf-8")

    result = parse_file(content, "leads.csv", ImportJobFormat.csv)
    assert result.error is None
    assert result.headers == ["company_name", "city", "email"]
    assert result.rows[0]["email"] == "sales@acme.io"


# ===========================================================================
# Parsers — XLSX
# ===========================================================================

def test_parse_xlsx_first_sheet_headers():
    """First sheet, first row = headers; trailing empty header cells dropped."""
    openpyxl = pytest.importorskip("openpyxl")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Название", "Город", "Email"])
    ws.append(["Stars Coffee", "Москва", "hi@stars.ru"])
    ws.append(["Surf Coffee", "СПб", "contact@surf.io"])
    buf = io.BytesIO()
    wb.save(buf)

    result = parse_file(buf.getvalue(), "leads.xlsx", ImportJobFormat.xlsx)
    assert result.error is None
    assert result.headers == ["Название", "Город", "Email"]
    assert len(result.rows) == 2
    assert result.rows[1]["Город"] == "СПб"


# ===========================================================================
# Parsers — JSON
# ===========================================================================

def test_parse_json_list_format():
    """Top-level list of objects."""
    content = json.dumps(
        [
            {"company": "Stars", "email": "x@stars.ru"},
            {"company": "Surf", "email": "y@surf.io"},
        ]
    ).encode("utf-8")

    result = parse_file(content, "leads.json", ImportJobFormat.json)
    assert result.error is None
    assert "company" in result.headers
    assert "email" in result.headers
    assert len(result.rows) == 2


def test_parse_json_leads_key_format():
    """Object with `leads: [...]` key (matches PRD §6.14 snapshot shape)."""
    content = json.dumps(
        {"leads": [{"company": "Stars"}, {"company": "Surf"}]}
    ).encode("utf-8")

    result = parse_file(content, "leads.json", ImportJobFormat.json)
    assert result.error is None
    assert len(result.rows) == 2


# ===========================================================================
# Parsers — YAML
# ===========================================================================

def test_parse_yaml_list_format():
    yaml_text = """
- company: Stars
  email: x@stars.ru
- company: Surf
  email: y@surf.io
"""
    result = parse_file(yaml_text.encode("utf-8"), "leads.yaml", ImportJobFormat.yaml)
    assert result.error is None
    assert len(result.rows) == 2
    assert result.rows[0]["company"] == "Stars"


# ===========================================================================
# Parsers — limits
# ===========================================================================

def test_parse_exceeds_max_rows_returns_error():
    """5001 rows → ParseResult.error, not silent truncation."""
    rows = [{"company": f"R{i}"} for i in range(MAX_ROWS + 1)]
    content = json.dumps(rows).encode("utf-8")

    result = parse_file(content, "huge.json", ImportJobFormat.json)
    assert result.error is not None
    assert "too many rows" in result.error.lower()


# ===========================================================================
# Mapper
# ===========================================================================

def test_suggest_mapping_exact_match():
    """Header exactly matches a canonical key → confidence 1.0."""
    result = suggest_mapping(["company_name", "city"])
    assert result["company_name"] == "company_name"
    assert result["city"] == "city"


def test_suggest_mapping_alias_match():
    """RU alias (`почта` → email, `название` → company_name)."""
    result = suggest_mapping(["Название", "Почта", "Телефон"])
    assert result["Название"] == "company_name"
    assert result["Почта"] == "email"
    assert result["Телефон"] == "phone"


def test_suggest_mapping_conflict_resolved_by_confidence():
    """Two headers chase the same field → higher confidence wins, the
    other becomes None. 'company' (exact alias 1.0) beats 'Companies info'
    (substring 0.6)."""
    result = suggest_mapping(["company", "Companies info"])
    assert result["company"] == "company_name"
    assert result["Companies info"] is None


def test_suggest_mapping_unknown_column_returns_none():
    """Header that doesn't match any alias above the 0.6 threshold."""
    result = suggest_mapping(["random_xyz"])
    assert result["random_xyz"] is None


def test_apply_mapping_drops_unmapped_columns():
    rows = [
        {"Название": "Stars", "RandomCol": "ignore me", "Город": "Москва"},
        {"Название": "Surf", "RandomCol": "drop", "Город": "СПб"},
    ]
    mapping = {"Название": "company_name", "RandomCol": None, "Город": "city"}
    out = apply_mapping(rows, mapping)
    assert out == [
        {"company_name": "Stars", "city": "Москва"},
        {"company_name": "Surf", "city": "СПб"},
    ]


# ===========================================================================
# Validators
# ===========================================================================

def test_validate_row_missing_company_name():
    errors = validate_row({"company_name": "", "email": "ok@ok.io"})
    assert any("company_name" in e for e in errors)


def test_validate_row_invalid_email():
    errors = validate_row({"company_name": "X", "email": "not-an-email"})
    assert any("email" in e for e in errors)


def test_validate_row_invalid_inn_length():
    """ИНН must be 10 or 12 digits (legal-entity vs sole-proprietor)."""
    errors = validate_row({"company_name": "X", "inn": "12345"})
    assert any("inn" in e for e in errors)
    # 10-digit passes
    assert not any("inn" in e for e in validate_row(
        {"company_name": "X", "inn": "1234567890"}
    ))
    # 12-digit passes
    assert not any("inn" in e for e in validate_row(
        {"company_name": "X", "inn": "123456789012"}
    ))


def test_validate_row_deal_amount_strips_currency():
    """parse_deal_amount handles RU `1 500 000 ₽` and EN `$2,500.00`."""
    assert parse_deal_amount("1 500 000 ₽") == 1500000.0
    assert parse_deal_amount("$2500.00") == 2500.0
    assert parse_deal_amount("not a number") is None
    # Validator passes when amount parses OK
    assert validate_row({
        "company_name": "X",
        "deal_amount": "1 500 000 ₽",
    }) == []
    # Validator errors when amount can't parse
    errors = validate_row({"company_name": "X", "deal_amount": "abc"})
    assert any("deal_amount" in e for e in errors)
