"""Tests for the Telegram channel — Sprint 3.4 G2.

Pure unit tests: httpx.AsyncClient is patched; the AsyncSession is a
mock. No Postgres / no network.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.inbox.adapters.telegram as tg_mod
import app.inbox.message_services as msg_svc
from app.inbox.adapters.telegram import TelegramAdapter, TelegramSendError
from app.inbox.schemas import OutboundMessage

# Trigger ORM mapper configuration — Lead has string-referenced
# relationships that must be importable before any `select(InboxMessage)`.
from app.contacts.models import Contact  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.activity.models import Activity  # noqa: F401


WS = uuid.uuid4()


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    return r


# ===========================================================================
# 1. parse_webhook — direct DM (`message`)
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_direct_message():
    raw = {
        "update_id": 100,
        "message": {
            "message_id": 42,
            "chat": {"id": 555000, "type": "private"},
            "from": {"id": 555000, "first_name": "Андрей"},
            "text": "Здравствуйте, я по поводу пилота",
            "date": 1715000000,
        },
    }
    adapter = TelegramAdapter(bot_token="fake")
    payload = await adapter.parse_webhook(raw)

    assert payload.channel == "telegram"
    assert payload.direction == "inbound"
    assert payload.external_id == "tg_42"
    assert payload.sender_id == "555000"
    assert payload.body == "Здравствуйте, я по поводу пилота"


# ===========================================================================
# 2. parse_webhook — Telegram Business proxy (`business_message`)
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_business_message():
    raw = {
        "update_id": 101,
        "business_message": {
            "message_id": 99,
            "business_connection_id": "biz_abc",
            "chat": {"id": 777111, "type": "private"},
            "from": {"id": 777111},
            "text": "Сколько стоит станция?",
        },
    }
    adapter = TelegramAdapter(bot_token="fake")
    payload = await adapter.parse_webhook(raw)

    assert payload.external_id == "tg_99"
    assert payload.sender_id == "777111"
    assert payload.body == "Сколько стоит станция?"


# ===========================================================================
# 3. parse_webhook — missing text → empty body, no crash
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_tolerates_missing_text():
    raw = {
        "update_id": 102,
        "message": {
            "message_id": 7,
            "chat": {"id": 1, "type": "private"},
            "sticker": {"file_id": "x"},
        },
    }
    adapter = TelegramAdapter(bot_token="fake")
    payload = await adapter.parse_webhook(raw)

    assert payload.external_id == "tg_7"
    assert payload.sender_id == "1"
    assert payload.body == ""


# ===========================================================================
# 4. send — happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_adapter_send_posts_to_bot_api_and_returns_external_id():
    adapter = TelegramAdapter(bot_token="TKN")

    captured: dict = {}

    class _Resp:
        status_code = 200
        content = b"{}"
        text = "{}"

        def json(self):
            return {"ok": True, "result": {"message_id": 555}}

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    with patch.object(tg_mod.httpx, "AsyncClient", _Client):
        ext_id = await adapter.send(
            OutboundMessage(
                channel="telegram",
                recipient_id="123",
                body="Привет",
            )
        )

    assert ext_id == "tg_555"
    assert captured["url"].endswith("/botTKN/sendMessage")
    assert captured["json"] == {"chat_id": "123", "text": "Привет"}


# ===========================================================================
# 5. send — no bot token → TelegramSendError without hitting the network
# ===========================================================================

@pytest.mark.asyncio
async def test_adapter_send_without_token_raises():
    adapter = TelegramAdapter(bot_token="")
    with pytest.raises(TelegramSendError) as exc:
        await adapter.send(
            OutboundMessage(
                channel="telegram", recipient_id="123", body="x"
            )
        )
    assert "not_configured" in str(exc.value)


# ===========================================================================
# 6. send — non-200 → TelegramSendError tagged with the status
# ===========================================================================

@pytest.mark.asyncio
async def test_adapter_send_bad_status_raises():
    adapter = TelegramAdapter(bot_token="TKN")

    class _Resp:
        status_code = 400
        content = b'{"description":"chat not found"}'
        text = '{"description":"chat not found"}'

        def json(self):
            return {"ok": False, "description": "chat not found"}

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, *_a, **_kw):
            return _Resp()

    with patch.object(tg_mod.httpx, "AsyncClient", _Client):
        with pytest.raises(TelegramSendError) as exc:
            await adapter.send(
                OutboundMessage(
                    channel="telegram", recipient_id="999", body="x"
                )
            )
    assert "telegram_status_400" in str(exc.value)


# ===========================================================================
# 7. message_services.send — happy path, writes InboxMessage + Activity
# ===========================================================================

@pytest.mark.asyncio
async def test_send_service_persists_outbound_and_activity():
    db = _make_db()
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.tg_chat_id = "555000"

    db.execute.side_effect = [_scalar_result(lead)]

    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    fake_adapter = MagicMock()
    fake_adapter.send = AsyncMock(return_value="tg_999")

    with patch.object(msg_svc, "_get_adapter", lambda ch: fake_adapter):
        out = await msg_svc.send(
            db,
            workspace_id=WS,
            lead_id=lead.id,
            channel="telegram",
            body="ответ",
            manager_user_id=uuid.uuid4(),
        )

    # 1 InboxMessage + 1 Activity added
    assert len(added) == 2
    msg_row, act_row = added
    assert msg_row.direction == "outbound"
    assert msg_row.external_id == "tg_999"
    assert msg_row.sender_id == "555000"
    assert msg_row.channel == "telegram"
    assert act_row.type == "tg"
    assert act_row.channel == "telegram"
    assert act_row.direction == "outbound"
    assert act_row.to_identifier == "555000"
    assert out is msg_row
    db.commit.assert_awaited()


# ===========================================================================
# 8. message_services.send — lead has no tg_chat_id → BadRequest
# ===========================================================================

@pytest.mark.asyncio
async def test_send_service_rejects_when_no_recipient():
    db = _make_db()
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.tg_chat_id = None

    db.execute.side_effect = [_scalar_result(lead)]

    with pytest.raises(msg_svc.InboxMessageBadRequest) as exc:
        await msg_svc.send(
            db,
            workspace_id=WS,
            lead_id=lead.id,
            channel="telegram",
            body="x",
        )
    assert "recipient_not_set:telegram" in str(exc.value)
    db.commit.assert_not_called()


# ===========================================================================
# 9. message_services.send — adapter failure → InboxSendError
# ===========================================================================

@pytest.mark.asyncio
async def test_send_service_wraps_adapter_errors():
    db = _make_db()
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.tg_chat_id = "555"

    db.execute.side_effect = [_scalar_result(lead)]

    fake_adapter = MagicMock()
    fake_adapter.send = AsyncMock(
        side_effect=TelegramSendError("telegram_status_400")
    )

    with patch.object(msg_svc, "_get_adapter", lambda ch: fake_adapter):
        with pytest.raises(msg_svc.InboxSendError) as exc:
            await msg_svc.send(
                db,
                workspace_id=WS,
                lead_id=lead.id,
                channel="telegram",
                body="x",
            )
    assert "telegram_status_400" in str(exc.value)


# ===========================================================================
# 10. receive — matched inbound writes Activity AND schedules agent refresh
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_matched_inbound_writes_activity_and_kicks_agent():
    from app.inbox.schemas import WebhookPayload

    db = _make_db()
    target_lead_id = uuid.uuid4()

    # 1: dedup → none; 2: match by tg_chat_id → hit
    db.execute.side_effect = [
        _scalar_result(None),
        _scalar_result(target_lead_id),
    ]

    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    refresh_calls: list[tuple] = []

    def _fake_refresh(lead_id, *, countdown):
        refresh_calls.append((lead_id, countdown))

    payload = WebhookPayload(
        channel="telegram",
        direction="inbound",
        external_id="tg_77",
        sender_id="555000",
        body="привет",
    )

    with patch.object(msg_svc, "_enqueue_lead_agent_refresh", _fake_refresh):
        msg, created = await msg_svc.receive(
            db, workspace_id=WS, payload=payload
        )

    assert created is True
    # 1 InboxMessage + 1 Activity
    assert len(added) == 2
    inbox_row, act_row = added
    assert inbox_row.lead_id == target_lead_id
    assert inbox_row.direction == "inbound"
    assert act_row.lead_id == target_lead_id
    assert act_row.channel == "telegram"
    assert act_row.direction == "inbound"
    # Lead Agent refresh scheduled with the spec's 15-min countdown
    assert refresh_calls == [(target_lead_id, 900)]


# ===========================================================================
# 11. receive — unmatched inbound does NOT write Activity / refresh agent
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_unmatched_skips_activity_and_agent():
    from app.inbox.schemas import WebhookPayload

    db = _make_db()
    db.execute.side_effect = [
        _scalar_result(None),   # dedup
        _scalar_result(None),   # tg_chat_id lookup → miss
        MagicMock(all=MagicMock(return_value=[])),  # phone enum → empty
    ]

    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    refresh_calls: list[tuple] = []

    def _fake_refresh(*a, **kw):
        refresh_calls.append((a, kw))

    payload = WebhookPayload(
        channel="telegram",
        direction="inbound",
        external_id="tg_88",
        sender_id="555000",
        body="cold inbound",
    )

    with patch.object(msg_svc, "_enqueue_lead_agent_refresh", _fake_refresh):
        msg, created = await msg_svc.receive(
            db, workspace_id=WS, payload=payload
        )

    assert created is True
    # Only the InboxMessage row — no Activity, no refresh
    assert len(added) == 1
    assert added[0].lead_id is None
    assert refresh_calls == []
