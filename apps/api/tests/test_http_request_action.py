"""Tests for plan 017 — generic `http_request` automation action (ADR-022).

Mock-only — same sqlalchemy stub pattern as test_automation_multistep.py /
test_automation_channel_visibility.py. Covers:

  1. A valid external URL → POST fired with a valid `X-DrinkX-Signature`
     header, signed over the exact body bytes sent.
  2. An internal/blocked URL → NOT fetched at all (the critical SSRF
     assertion — `route.called is False`, mirroring
     tests/test_web_fetch_ssrf.py), and the step raises so the caller
     records it `failed`.
  3. A redirect to a blocked host is rejected — the second hop is never
     followed.
  4. A timeout raises (no crash) so the caller records the step `failed`.
  5. `_validate_action_config` rejects an `http_request` config missing
     `url`, and rejects an unsupported HTTP method.
  6. `create_automation` accepts a valid `http_request` step (CRUD-level
     wiring, not just the pure validator).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx


# ---------------------------------------------------------------------------
# sqlalchemy stub — same as test_automation_multistep.py / test_automation_
# channel_visibility.py.
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
        "desc", "false", "true", "UniqueConstraint", "text", "nullslast",
        "nullsfirst", "asc", "or_", "and_", "update", "delete", "cast",
        "literal", "Date",
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

    class _IntegrityError(Exception):
        pass

    class _OperationalError(Exception):
        pass

    sa_exc.IntegrityError = _IntegrityError
    sa_exc.OperationalError = _OperationalError

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

from app.automation_builder import services as svc  # noqa: E402

WS = uuid.uuid4()
LEAD_ID = uuid.uuid4()
AUTOMATION_ID = uuid.uuid4()


def _make_lead(**kw):
    lead = MagicMock()
    lead.id = kw.get("id", LEAD_ID)
    lead.workspace_id = kw.get("workspace_id", WS)
    lead.priority = "A"
    lead.score = 75
    lead.deal_type = "enterprise_direct"
    lead.stage_id = uuid.uuid4()
    lead.pipeline_id = uuid.uuid4()
    lead.source = None
    lead.assignment_status = "pool"
    lead.company_name = kw.get("company_name", "Acme Corp")
    lead.city = "Moscow"
    lead.email = None
    lead.phone = None
    lead.website = None
    lead.segment = None
    lead.next_step = None
    lead.blocker = None
    return lead


# ===========================================================================
# 1. Valid external URL → POST fired with a valid signature over the
#    exact body sent.
# ===========================================================================

@pytest.mark.asyncio
async def test_http_request_fires_signed_post_to_allowed_url(monkeypatch):
    monkeypatch.setattr(
        "app.automation_builder.services.is_safe_fetch_url", lambda url: True
    )
    lead = _make_lead()
    config = {
        "method": "POST",
        "url": "https://example.com/webhook",
        "body_template": "hello {{lead.company_name}}",
    }

    captured_request = {}

    with respx.mock:
        route = respx.post("https://example.com/webhook").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        await svc._http_request_action(
            AsyncMock(),
            lead=lead,
            config=config,
            automation_id_str=str(AUTOMATION_ID),
        )
        assert route.called is True
        sent_request = route.calls.last.request
        captured_request["body"] = sent_request.content
        captured_request["signature"] = sent_request.headers.get(
            "x-drinkx-signature"
        )

    # Signature header is present and correctly computed over the exact
    # bytes that were sent (secret is empty string in test config, same
    # as dev default).
    assert captured_request["signature"] is not None
    expected = "sha256=" + hmac.new(
        b"", captured_request["body"], hashlib.sha256
    ).hexdigest()
    assert captured_request["signature"] == expected

    # Body carries the rendered template + lead/automation identifiers.
    sent_payload = json.loads(captured_request["body"])
    assert sent_payload["event"] == "automation.http_request"
    assert sent_payload["data"]["lead_id"] == str(lead.id)
    assert sent_payload["data"]["automation_id"] == str(AUTOMATION_ID)
    assert sent_payload["data"]["body"] == "hello Acme Corp"


# ===========================================================================
# 2. Internal/blocked URL → never fetched, raises so the step fails.
# ===========================================================================

@pytest.mark.asyncio
async def test_http_request_blocks_internal_url_without_request(monkeypatch):
    # Force the SSRF guard to reject — mirrors
    # test_web_fetch_ssrf.py::test_web_fetch_blocks_internal_url_without_request.
    monkeypatch.setattr(
        "app.automation_builder.services.is_safe_fetch_url", lambda url: False
    )
    lead = _make_lead()
    config = {
        "method": "POST",
        "url": "http://169.254.169.254/latest/meta-data/",
    }

    with respx.mock:
        route = respx.post("http://169.254.169.254/latest/meta-data/").mock(
            return_value=httpx.Response(200, text="SECRET")
        )
        with pytest.raises(svc.HttpRequestBlocked):
            await svc._http_request_action(
                AsyncMock(),
                lead=lead,
                config=config,
                automation_id_str=str(AUTOMATION_ID),
            )
        assert route.called is False, "blocked URL must never be requested"


# ===========================================================================
# 3. Redirect to a blocked host is rejected — second hop never followed.
# ===========================================================================

@pytest.mark.asyncio
async def test_http_request_blocks_redirect_to_internal_host(monkeypatch):
    # First hop looks public; the redirect target does not.
    def _fake_is_safe(url: str) -> bool:
        return "169.254.169.254" not in url

    monkeypatch.setattr(
        "app.automation_builder.services.is_safe_fetch_url", _fake_is_safe
    )
    lead = _make_lead()
    config = {"method": "POST", "url": "https://example.com/redirect"}

    with respx.mock:
        first_hop = respx.post("https://example.com/redirect").mock(
            return_value=httpx.Response(
                302,
                headers={
                    "location": "http://169.254.169.254/latest/meta-data/"
                },
            )
        )
        second_hop = respx.post(
            "http://169.254.169.254/latest/meta-data/"
        ).mock(return_value=httpx.Response(200, text="SECRET"))

        with pytest.raises(svc.HttpRequestBlocked):
            await svc._http_request_action(
                AsyncMock(),
                lead=lead,
                config=config,
                automation_id_str=str(AUTOMATION_ID),
            )
        assert first_hop.called is True
        assert second_hop.called is False, (
            "redirect to a blocked host must never be followed"
        )


# ===========================================================================
# 4. Timeout raises, no crash.
# ===========================================================================

@pytest.mark.asyncio
async def test_http_request_timeout_raises_cleanly(monkeypatch):
    monkeypatch.setattr(
        "app.automation_builder.services.is_safe_fetch_url", lambda url: True
    )
    lead = _make_lead()
    config = {"method": "POST", "url": "https://example.com/slow"}

    with respx.mock:
        respx.post("https://example.com/slow").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with pytest.raises(httpx.TimeoutException):
            await svc._http_request_action(
                AsyncMock(),
                lead=lead,
                config=config,
                automation_id_str=str(AUTOMATION_ID),
            )


# ===========================================================================
# 5. Non-2xx response is a failure too.
# ===========================================================================

@pytest.mark.asyncio
async def test_http_request_non_2xx_raises(monkeypatch):
    monkeypatch.setattr(
        "app.automation_builder.services.is_safe_fetch_url", lambda url: True
    )
    lead = _make_lead()
    config = {"method": "POST", "url": "https://example.com/webhook"}

    with respx.mock:
        respx.post("https://example.com/webhook").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(ValueError):
            await svc._http_request_action(
                AsyncMock(),
                lead=lead,
                config=config,
                automation_id_str=str(AUTOMATION_ID),
            )


# ===========================================================================
# 6. _validate_action_config: missing url / bad method.
# ===========================================================================

def test_validate_action_config_rejects_missing_url():
    with pytest.raises(svc.InvalidActionConfig):
        svc._validate_action_config("http_request", {})


def test_validate_action_config_rejects_bad_method():
    with pytest.raises(svc.InvalidActionConfig):
        svc._validate_action_config(
            "http_request",
            {"url": "https://example.com/x", "method": "TRACE"},
        )


def test_validate_action_config_accepts_valid_http_request():
    # Should not raise.
    svc._validate_action_config(
        "http_request", {"url": "https://example.com/x", "method": "POST"}
    )


# ===========================================================================
# 7. create_automation accepts an http_request step (CRUD-level wiring).
# ===========================================================================

@pytest.mark.asyncio
async def test_create_automation_accepts_http_request_step():
    created = {}

    async def fake_create(_db, **kw):
        created.update(kw)
        m = MagicMock()
        m.id = uuid.uuid4()
        return m

    db = AsyncMock()

    with patch(
        "app.automation_builder.repositories.create", new=fake_create
    ):
        await svc.create_automation(
            db,
            workspace_id=WS,
            created_by=None,
            name="Notify Slack",
            trigger="stage_change",
            trigger_config_json=None,
            condition_json=None,
            action_type="http_request",
            action_config_json={
                "url": "https://hooks.example.com/slack",
                "method": "POST",
            },
        )

    assert created["action_type"] == "http_request"
    assert created["action_config_json"]["url"] == "https://hooks.example.com/slack"
