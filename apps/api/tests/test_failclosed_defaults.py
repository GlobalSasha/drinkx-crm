"""Tests for fail-closed security defaults — plan 013 / B10.

Two paths that used to default to *open* now fail closed in production:

  1. Auth stub mode (`app.auth.jwt._is_stub_mode` / `verify_token`) —
     stub identity is only ever returned outside production; in
     production with no Supabase env configured, auth raises a loud
     500 instead of silently authenticating as the dev stub user.
  2. Mango phone webhook (`app.inbox.webhooks.phone_webhook`) — an
     unset `mango_api_salt` is only tolerated outside production; in
     production it now returns 503 instead of accepting unsigned
     payloads.

Pure unit tests: `get_settings` is mocked, no Postgres / no network.
Pattern matches tests/test_auth_bootstrap.py (patch.object(..., "get_settings", ...)).
"""
from __future__ import annotations

import hashlib
import json as json_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.auth.jwt as jwt_mod
import app.inbox.webhooks as webhooks_mod

# Trigger ORM mapper configuration — Lead has string-referenced
# relationships that must be importable before any `select(Workspace)`.
# Same pattern as tests/test_inbox_phone.py + tests/test_inbox_telegram.py.
from app.contacts.models import Contact  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.activity.models import Activity  # noqa: F401


def _fake_settings(**overrides):
    s = MagicMock()
    s.app_env = "development"
    s.supabase_jwt_secret = ""
    s.supabase_url = ""
    s.mango_api_salt = ""
    s.mango_api_key = "KEY"
    s.default_workspace_id = ""
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ===========================================================================
# Auth stub mode
# ===========================================================================


@pytest.mark.asyncio
async def test_dev_env_no_supabase_env_returns_stub_identity():
    """app_env='development' + no Supabase env → stub identity, no token check."""
    fake_settings = _fake_settings(app_env="development")
    with patch.object(jwt_mod, "get_settings", return_value=fake_settings):
        claims = await jwt_mod.verify_token(None)

    assert claims.is_stub is True
    assert claims.sub == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_production_env_no_supabase_env_raises_no_stub_identity():
    """app_env='production' + no Supabase env → raises, stub identity NEVER returned."""
    fake_settings = _fake_settings(app_env="production")
    with patch.object(jwt_mod, "get_settings", return_value=fake_settings):
        with pytest.raises(HTTPException) as exc:
            await jwt_mod.verify_token("some-token")

    assert exc.value.status_code == 500


def test_is_stub_mode_false_when_supabase_configured_even_in_dev():
    """Sanity: with Supabase env present, stub mode is off regardless of app_env."""
    fake_settings = _fake_settings(
        app_env="development", supabase_jwt_secret="secret"
    )
    with patch.object(jwt_mod, "get_settings", return_value=fake_settings):
        assert jwt_mod._is_stub_mode() is False


# ===========================================================================
# Mango phone webhook
# ===========================================================================


class _FakeForm:
    """Minimal stand-in for starlette's FormData: supports .get and .items()."""

    def __init__(self, data: dict[str, str]):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def items(self):
        return self._data.items()


class _FakeRequest:
    def __init__(self, form_data: dict[str, str]):
        self._form = _FakeForm(form_data)

    async def form(self):
        return self._form


def _make_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_mango_production_no_salt_returns_503():
    """Mango: production + no salt configured → 503, unsigned payload rejected."""
    fake_settings = _fake_settings(app_env="production", mango_api_salt="")
    request = _FakeRequest({"json": json_mod.dumps({"event": "call_end"})})
    db = _make_db()

    with patch.object(webhooks_mod, "get_settings", return_value=fake_settings):
        with pytest.raises(HTTPException) as exc:
            await webhooks_mod.phone_webhook(request, db)

    assert exc.value.status_code == 503
    assert exc.value.detail == "phone_webhook_not_configured"


@pytest.mark.asyncio
async def test_mango_development_no_salt_accepts_unsigned():
    """Mango: development + no salt configured → accepted (dev-only leniency)."""
    fake_settings = _fake_settings(app_env="development", mango_api_salt="")
    request = _FakeRequest(
        {"json": json_mod.dumps({"event": "missed_call", "call_id": "1", "direction": "in", "from": "1"})}
    )
    db = _make_db()
    db.execute.side_effect = [MagicMock(scalar_one_or_none=MagicMock(return_value=None))]

    with patch.object(webhooks_mod, "get_settings", return_value=fake_settings):
        result = await webhooks_mod.phone_webhook(request, db)

    assert result == {"status": "ignored"}


@pytest.mark.asyncio
async def test_mango_any_env_salt_set_bad_sign_returns_401():
    """Mango: salt configured + bad/missing sign → 401, regardless of app_env."""
    fake_settings = _fake_settings(app_env="production", mango_api_salt="SALT")
    request = _FakeRequest(
        {
            "json": json_mod.dumps({"event": "call_end"}),
            "sign": "not-the-real-signature",
        }
    )
    db = _make_db()

    with patch.object(webhooks_mod, "get_settings", return_value=fake_settings):
        with pytest.raises(HTTPException) as exc:
            await webhooks_mod.phone_webhook(request, db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_sign"


@pytest.mark.asyncio
async def test_mango_any_env_salt_set_correct_sign_accepted():
    """Mango: salt configured + correct sign → accepted (not rejected)."""
    json_field = json_mod.dumps({"event": "missed_call", "call_id": "1", "direction": "in", "from": "1"})
    api_key = "KEY"
    api_salt = "SALT"
    expected_sign = hashlib.sha256(
        f"{api_key}{json_field}{api_salt}".encode("utf-8")
    ).hexdigest()

    fake_settings = _fake_settings(
        app_env="production", mango_api_salt=api_salt, mango_api_key=api_key
    )
    request = _FakeRequest({"json": json_field, "sign": expected_sign})
    db = _make_db()
    db.execute.side_effect = [MagicMock(scalar_one_or_none=MagicMock(return_value=None))]

    with patch.object(webhooks_mod, "get_settings", return_value=fake_settings):
        result = await webhooks_mod.phone_webhook(request, db)

    assert result == {"status": "ignored"}
