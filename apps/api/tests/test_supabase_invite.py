"""Отправка приглашения через Supabase — регрессия на адрес эндпоинта.

11.09.2026: в коде стоял `/auth/v1/admin/invite_user_by_email` — это имя
метода JS-SDK, а не HTTP-путь. GoTrue отвечал «404 page not found», каждое
приглашение падало с 502, и за всё время invite-only не создалось ни одной
строки в `user_invites`. Тест ниже падает, если адрес снова уедет.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.users import supabase_admin as sa
from app.users.supabase_admin import InviteOutcome, SupabaseInviteError

SETTINGS = SimpleNamespace(
    supabase_url="https://project.supabase.co",
    supabase_secret_key="service-role-key",
)


class _Response:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Записывает запросы и отдаёт заранее заданные ответы по порядку."""

    def __init__(self, responses: list[_Response]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, *, headers=None, json=None):
        self.calls.append((url, json or {}))
        return self._responses.pop(0)


def _run(responses: list[_Response], email="newhire@drinkx.tech"):
    client = _FakeClient(responses)
    with patch.object(sa, "get_settings", lambda: SETTINGS), patch.object(
        sa.httpx, "AsyncClient", lambda **_kw: client
    ):
        import asyncio

        outcome = asyncio.run(sa.send_invite_email(email=email))
    return outcome, client


def test_invite_hits_the_real_gotrue_endpoint():
    outcome, client = _run([_Response(200, "{}")])

    assert outcome is InviteOutcome.INVITED
    url, body = client.calls[0]
    assert url == "https://project.supabase.co/auth/v1/invite"
    assert "admin/invite_user_by_email" not in url, (
        "это имя метода JS-SDK, GoTrue отдаёт на него 404"
    )
    assert body == {"email": "newhire@drinkx.tech"}


def test_existing_account_gets_a_sign_in_link_instead():
    """Человек уже пробовал войти до приглашения — аккаунт в Supabase есть.
    Это не отказ: доступ даёт строка user_invites, а ему шлём ссылку для входа."""
    outcome, client = _run([
        _Response(422, '{"error_code":"email_exists","msg":"..."}'),
        _Response(200, "{}"),
    ])

    assert outcome is InviteOutcome.SIGN_IN_LINK
    assert len(client.calls) == 2
    assert client.calls[1][0] == "https://project.supabase.co/auth/v1/otp"
    assert client.calls[1][1]["should_create_user"] is False


def test_existing_account_still_succeeds_when_the_link_fails():
    """Ссылка не ушла — приглашение всё равно состоялось, человек зайдёт сам."""
    outcome, _client = _run([
        _Response(422, '{"error_code":"email_exists"}'),
        _Response(500, "boom"),
    ])

    assert outcome is InviteOutcome.NOT_SENT


def test_legacy_already_registered_wording_is_recognised():
    """Старые версии GoTrue писали текстом, без error_code."""
    outcome, _client = _run([
        _Response(422, '{"msg":"Email address has already been registered"}'),
        _Response(200, "{}"),
    ])

    assert outcome is InviteOutcome.SIGN_IN_LINK


def test_real_upstream_failure_still_raises():
    """404 или 500 на самом приглашении — это поломка, а не особый случай."""
    with pytest.raises(SupabaseInviteError):
        _run([_Response(404, "404 page not found")])


def test_stub_mode_without_a_key():
    empty = SimpleNamespace(supabase_url="", supabase_secret_key="")
    with patch.object(sa, "get_settings", lambda: empty):
        import asyncio

        assert asyncio.run(sa.send_invite_email(email="x@y.io")) is InviteOutcome.INVITED
