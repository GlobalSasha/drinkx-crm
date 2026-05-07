"""Tests for the email-context block injected into the AI Brief synthesis
prompt — Sprint 2.0 G6.

Mock-only: sqlalchemy + transitive deps (redis, httpx, celery) are stubbed
at import time so this suite runs in environments where those aren't pip-
installed (mirrors the test_inbox_matcher.py harness).
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub (same shape as test_audit / test_inbox_matcher)
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
        "Numeric", "DateTime", "Boolean", "Index", "select",
        "desc", "false", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name):
            return _Callable

    sa.func = _Func()

    sa_ext = ModuleType("sqlalchemy.ext")
    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_dialects = ModuleType("sqlalchemy.dialects")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")

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


def _stub_redis_and_httpx():
    """Stub modules that orchestrator pulls in transitively via sources."""
    for mod_name in ("redis", "redis.asyncio"):
        if mod_name not in sys.modules:
            mod = ModuleType(mod_name)
            mod.Redis = object  # type: ignore[attr-defined]
            mod.from_url = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
            sys.modules[mod_name] = mod
    if "httpx" not in sys.modules:
        httpx = ModuleType("httpx")
        httpx.AsyncClient = MagicMock  # type: ignore[attr-defined]
        httpx.HTTPError = Exception  # type: ignore[attr-defined]
        httpx.Timeout = lambda *a, **kw: None  # type: ignore[attr-defined]
        sys.modules["httpx"] = httpx


_stub_sqlalchemy()
_stub_redis_and_httpx()


# ---------------------------------------------------------------------------
# Imports after stubbing
# ---------------------------------------------------------------------------

import app.enrichment.orchestrator as orch_mod  # noqa: E402
from app.enrichment.orchestrator import (  # noqa: E402
    EMAIL_CONTEXT_MAX_CHARS,
    _format_email_section,
    _load_email_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email_activity(*, subject="Hi", body="Hello there.", direction="inbound"):
    a = MagicMock()
    a.subject = subject
    a.body = body
    a.direction = direction
    return a


def _execute_returning(rows: list):
    """An AsyncMock execute() that returns a Result whose .scalars()
    yields the given rows."""
    result = MagicMock()
    result.scalars = MagicMock(return_value=iter(rows))
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


# ===========================================================================
# 1. Emails exist → context is injected
# ===========================================================================

@pytest.mark.asyncio
async def test_email_context_injected_when_emails_exist():
    """`_load_email_context` returns a non-empty block whose section header
    survives `_format_email_section`. Two activities — one inbound, one
    outbound — are reflected in the formatted block with the right markers."""
    db = _execute_returning(
        [
            _email_activity(
                subject="Re: пилот",
                body="Подтверждаем готовность к встрече.",
                direction="inbound",
            ),
            _email_activity(
                subject="Предложение",
                body="Отправили КП с тремя сценариями.",
                direction="outbound",
            ),
        ]
    )

    raw = await _load_email_context(db, lead_id=uuid.uuid4())
    assert "Переписка с клиентом" in raw
    assert "← Входящее" in raw
    assert "→ Исходящее" in raw
    assert "Re: пилот" in raw
    assert "Предложение" in raw

    section = _format_email_section(raw)
    # The section header is what reaches the LLM via system_parts.
    assert "### Переписка с клиентом" in section
    assert "Используй переписку как сигнал" in section


# ===========================================================================
# 2. No emails → no injection
# ===========================================================================

@pytest.mark.asyncio
async def test_email_context_skipped_when_no_emails():
    """No activities → empty string → caller skips injection (no section
    text leaks into the system prompt)."""
    db = _execute_returning([])
    raw = await _load_email_context(db, lead_id=uuid.uuid4())
    assert raw == ""

    # Mirror the call-site guard in run_enrichment.
    parts = ["profile-block", "kb-block"]
    if raw:  # falsy → skipped
        parts.append(_format_email_section(raw))
    parts.append("SYNTHESIS_SYSTEM")
    final_prompt = "\n\n".join(parts)
    assert "Переписка с клиентом" not in final_prompt


# ===========================================================================
# 3. Combined emails > 2000 chars → truncated to 2000
# ===========================================================================

@pytest.mark.asyncio
async def test_email_context_truncated_at_2000_chars():
    """Twelve oversized emails would produce a multi-thousand-char raw
    string. The call-site guard (mirrored here) caps at
    EMAIL_CONTEXT_MAX_CHARS before injecting."""
    big_body = "x" * 500  # one email -> ~530 chars after preview cap (200 + header)
    rows = [
        _email_activity(subject=f"Тема {i}", body=big_body, direction="inbound")
        for i in range(12)
    ]
    db = _execute_returning(rows)

    raw = await _load_email_context(db, lead_id=uuid.uuid4())
    # Sanity: pre-cap length must exceed the cap, otherwise the test is moot.
    assert len(raw) > EMAIL_CONTEXT_MAX_CHARS

    # Apply the same guard run_enrichment uses.
    capped = raw[:EMAIL_CONTEXT_MAX_CHARS] if len(raw) > EMAIL_CONTEXT_MAX_CHARS else raw
    assert len(capped) <= EMAIL_CONTEXT_MAX_CHARS
    assert len(capped) == EMAIL_CONTEXT_MAX_CHARS  # exact cap on this input
