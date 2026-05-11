"""Tests for the Mango / phone channel — Sprint 3.4 G4.

Pure unit tests: httpx.AsyncClient is patched, the AsyncSession is a
mock. No Postgres / no network.
"""
from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.inbox.adapters.phone as phone_mod
import app.inbox.message_services as msg_svc
from app.inbox.adapters.phone import (
    MangoCallError,
    PhoneAdapter,
    compute_sign,
)

# Trigger ORM mapper configuration — Lead has string-referenced
# relationships that must be importable before any `select(Lead)`.
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
# 1. parse_webhook — inbound answered call → status='answered' + Russian body
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_inbound_answered_call():
    raw = {
        "event": "call_end",
        "call_id": "call-aaa-111",
        "direction": "in",
        "from": "+7 (916) 123-45-67",
        "to": "+74950000000",
        "call_duration": "252",
        "recording_url": "https://mango.example/rec.mp3",
    }
    adapter = PhoneAdapter(api_key="K", api_salt="S")
    payload = await adapter.parse_webhook(raw)

    assert payload.channel == "phone"
    assert payload.direction == "inbound"
    assert payload.external_id == "call-aaa-111"
    assert payload.sender_id == "+7 (916) 123-45-67"
    assert payload.call_status == "answered"
    assert payload.call_duration == 252
    assert payload.media_url == "https://mango.example/rec.mp3"
    # 4 min 12 s → "4:12"
    assert "4:12" in payload.body
    assert payload.body.startswith("Входящий")


# ===========================================================================
# 2. parse_webhook — missed call → status='missed', no transcription trigger
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_missed_call():
    raw = {
        "event": "missed_call",
        "call_id": "call-miss-1",
        "direction": "in",
        "from": "9991112233",
        "call_duration": "0",
    }
    adapter = PhoneAdapter(api_key="K", api_salt="S")
    payload = await adapter.parse_webhook(raw)

    assert payload.call_status == "missed"
    assert payload.call_duration is None
    assert payload.body == "Пропущенный звонок"
    assert not payload.media_url


# ===========================================================================
# 3. parse_webhook — outbound (from_employee → uses `to` as sender_id)
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_outbound_call():
    raw = {
        "event": "call_end",
        "call_id": "call-out-9",
        "direction": "from_employee",
        "from": "101",            # manager's internal extension
        "to": "79161234567",      # the lead
        "call_duration": "120",
        "recording_url": "https://mango.example/out.mp3",
    }
    adapter = PhoneAdapter(api_key="K", api_salt="S")
    payload = await adapter.parse_webhook(raw)

    assert payload.direction == "outbound"
    assert payload.sender_id == "79161234567"
    assert payload.body.startswith("Исходящий")


# ===========================================================================
# 4. parse_webhook — duration only, no event field → infer answered/missed
# ===========================================================================

@pytest.mark.asyncio
async def test_parse_webhook_infers_status_from_duration():
    answered = await PhoneAdapter(api_key="K", api_salt="S").parse_webhook(
        {"call_id": "1", "direction": "in", "from": "1", "call_duration": "5"}
    )
    missed = await PhoneAdapter(api_key="K", api_salt="S").parse_webhook(
        {"call_id": "2", "direction": "in", "from": "1", "call_duration": ""}
    )
    assert answered.call_status == "answered"
    assert missed.call_status == "missed"


# ===========================================================================
# 5. compute_sign — pinned to Mango's documented formula
# ===========================================================================

def test_compute_sign_matches_spec_formula():
    api_key = "KEY"
    json_body = '{"command_id":"c1"}'
    api_salt = "SALT"
    expected = hashlib.sha256(
        f"{api_key}{json_body}{api_salt}".encode("utf-8")
    ).hexdigest()
    assert compute_sign(api_key, json_body, api_salt) == expected


# ===========================================================================
# 6. initiate_call — happy path: signs payload and POSTs to /callback
# ===========================================================================

@pytest.mark.asyncio
async def test_initiate_call_signs_payload_and_posts():
    adapter = PhoneAdapter(
        api_key="KEY", api_salt="SALT", api_base="https://mango.test"
    )

    captured: dict = {}

    class _Resp:
        status_code = 200
        content = b'{"status":"dialing"}'
        text = '{"status":"dialing"}'

        def json(self):
            return {"status": "dialing"}

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, data):
            captured["url"] = url
            captured["data"] = dict(data)
            return _Resp()

    with patch.object(phone_mod.httpx, "AsyncClient", _Client):
        result = await adapter.initiate_call(
            from_extension="101", to_number="79161234567"
        )

    assert result == {"status": "dialing"}
    assert captured["url"] == "https://mango.test/vpbx/commands/callback"
    sent = captured["data"]
    assert sent["vpbx_api_key"] == "KEY"
    # sign covers exactly the json body
    expected = hashlib.sha256(
        f"KEY{sent['json']}SALT".encode("utf-8")
    ).hexdigest()
    assert sent["sign"] == expected
    # the json payload itself contains the lead's number
    assert "79161234567" in sent["json"]
    assert "101" in sent["json"]


# ===========================================================================
# 7. initiate_call — missing config → MangoCallError, no network call
# ===========================================================================

@pytest.mark.asyncio
async def test_initiate_call_without_config_raises():
    adapter = PhoneAdapter(api_key="", api_salt="")
    with pytest.raises(MangoCallError) as exc:
        await adapter.initiate_call(from_extension="101", to_number="123")
    assert "not_configured" in str(exc.value)


# ===========================================================================
# 8. initiate_call — non-200 → MangoCallError tagged with the status
# ===========================================================================

@pytest.mark.asyncio
async def test_initiate_call_bad_status_raises():
    adapter = PhoneAdapter(api_key="K", api_salt="S")

    class _Resp:
        status_code = 401
        content = b'{"error":"auth"}'
        text = '{"error":"auth"}'

        def json(self):
            return {"error": "auth"}

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, *_a, **_kw):
            return _Resp()

    with patch.object(phone_mod.httpx, "AsyncClient", _Client):
        with pytest.raises(MangoCallError) as exc:
            await adapter.initiate_call(
                from_extension="101", to_number="123"
            )
    assert "mango_status_401" in str(exc.value)


# ===========================================================================
# 9. place_call — happy path: returns Mango response, no DB write
# ===========================================================================

@pytest.mark.asyncio
async def test_place_call_returns_mango_response_and_does_not_write():
    db = _make_db()
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.phone = "+7 (916) 555-12-34"

    db.execute.side_effect = [_scalar_result(lead)]

    fake_adapter = MagicMock()
    fake_adapter.initiate_call = AsyncMock(return_value={"status": "dialing"})

    class _FakePhone:
        def __init__(self): pass
        initiate_call = fake_adapter.initiate_call

    with patch.object(phone_mod, "PhoneAdapter", _FakePhone):
        result = await msg_svc.place_call(
            db,
            workspace_id=WS,
            lead_id=lead.id,
            from_extension="101",
            manager_user_id=uuid.uuid4(),
        )

    assert result == {"status": "dialing"}
    # Click-to-call must NOT write to inbox_messages — canonical record
    # arrives via the call_end webhook.
    db.add.assert_not_called()
    db.commit.assert_not_called()


# ===========================================================================
# 10. place_call — lead has no phone → BadRequest
# ===========================================================================

@pytest.mark.asyncio
async def test_place_call_rejects_when_lead_has_no_phone():
    db = _make_db()
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.phone = None
    db.execute.side_effect = [_scalar_result(lead)]

    with pytest.raises(msg_svc.InboxMessageBadRequest) as exc:
        await msg_svc.place_call(
            db,
            workspace_id=WS,
            lead_id=lead.id,
            from_extension="101",
        )
    assert "recipient_not_set:phone" in str(exc.value)


# ===========================================================================
# 11. place_call — Mango failure → InboxSendError
# ===========================================================================

@pytest.mark.asyncio
async def test_place_call_wraps_mango_errors():
    db = _make_db()
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.phone = "79161234567"
    db.execute.side_effect = [_scalar_result(lead)]

    fake_initiate = AsyncMock(side_effect=MangoCallError("mango_status_500"))

    class _FakePhone:
        def __init__(self): pass
        initiate_call = fake_initiate

    with patch.object(phone_mod, "PhoneAdapter", _FakePhone):
        with pytest.raises(msg_svc.InboxSendError) as exc:
            await msg_svc.place_call(
                db,
                workspace_id=WS,
                lead_id=lead.id,
                from_extension="101",
            )
    assert "mango_status_500" in str(exc.value)


# ===========================================================================
# 12. receive — phone answered + media_url → dispatches transcribe with 30s delay
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_answered_call_with_recording_dispatches_transcribe():
    from app.inbox.schemas import WebhookPayload

    db = _make_db()
    # dedup miss, phone fallback miss (Lead with this number does not exist)
    db.execute.side_effect = [
        _scalar_result(None),
        MagicMock(all=MagicMock(return_value=[])),
    ]

    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    transcribe_calls: list[tuple] = []

    def _fake_transcribe(message_id, *, countdown):
        transcribe_calls.append((message_id, countdown))

    payload = WebhookPayload(
        channel="phone",
        direction="inbound",
        external_id="call-ok-1",
        sender_id="79161234567",
        body="Входящий звонок, 4:12",
        media_url="https://mango.example/rec.mp3",
        call_duration=252,
        call_status="answered",
    )

    with patch.object(msg_svc, "_enqueue_transcribe", _fake_transcribe):
        msg, created = await msg_svc.receive(
            db, workspace_id=WS, payload=payload
        )

    assert created is True
    assert len(transcribe_calls) == 1
    # countdown=30 per the spec — gives Mango time to finalize the file
    _, countdown = transcribe_calls[0]
    assert countdown == 30


# ===========================================================================
# 13. receive — missed call → NO transcribe dispatch
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_missed_call_does_not_dispatch_transcribe():
    from app.inbox.schemas import WebhookPayload

    db = _make_db()
    db.execute.side_effect = [
        _scalar_result(None),
        MagicMock(all=MagicMock(return_value=[])),
    ]
    db.add = MagicMock()

    transcribe_calls: list[tuple] = []

    def _fake_transcribe(message_id, *, countdown):
        transcribe_calls.append((message_id, countdown))

    payload = WebhookPayload(
        channel="phone",
        direction="inbound",
        external_id="call-miss-2",
        sender_id="79161234567",
        body="Пропущенный звонок",
        media_url=None,
        call_status="missed",
    )

    with patch.object(msg_svc, "_enqueue_transcribe", _fake_transcribe):
        await msg_svc.receive(db, workspace_id=WS, payload=payload)

    assert transcribe_calls == []


# ===========================================================================
# 14. receive — answered call WITHOUT recording_url → NO transcribe dispatch
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_answered_call_without_recording_skips_transcribe():
    from app.inbox.schemas import WebhookPayload

    db = _make_db()
    db.execute.side_effect = [
        _scalar_result(None),
        MagicMock(all=MagicMock(return_value=[])),
    ]
    db.add = MagicMock()

    transcribe_calls: list[tuple] = []

    def _fake_transcribe(*a, **kw):
        transcribe_calls.append((a, kw))

    payload = WebhookPayload(
        channel="phone",
        direction="inbound",
        external_id="call-norec-3",
        sender_id="79161234567",
        body="Входящий звонок, 0:30",
        media_url=None,                # recording not available (yet?)
        call_duration=30,
        call_status="answered",
    )

    with patch.object(msg_svc, "_enqueue_transcribe", _fake_transcribe):
        await msg_svc.receive(db, workspace_id=WS, payload=payload)

    assert transcribe_calls == []
