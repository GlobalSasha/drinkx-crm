"""Tests for STT + transcribe pipeline — Sprint 3.4 G4b.

Two layers tested separately:
  * `SaluteSpeechProvider` — Sber OAuth + recognize flow with httpx
    patched to a fake transport.
  * `transcribe_call_async` — the Celery async core that ties STT and
    MiMo summary together. We inject a fake `app.scheduled.jobs` /
    `app.scheduled.celery_app` into sys.modules so the lazy imports
    inside the task pick up our stubs (Celery isn't installed in unit
    test envs).
"""
from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.inbox.message_tasks as tasks_mod
import app.inbox.stt.salute as salute_mod
from app.inbox.stt.base import SttError
from app.inbox.stt.factory import get_stt_provider
from app.inbox.stt.salute import SaluteSpeechProvider

# Trigger ORM mapper configuration.
from app.contacts.models import Contact  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.activity.models import Activity  # noqa: F401


# ===========================================================================
# Factory
# ===========================================================================

def test_factory_defaults_to_salute(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("STT_PROVIDER", "salute")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    provider = get_stt_provider()
    assert provider.provider_name == "salute"


def test_factory_falls_back_on_unknown(monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("STT_PROVIDER", "nonsense")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    provider = get_stt_provider()
    assert provider.provider_name == "salute"


# ===========================================================================
# SaluteSpeechProvider — OAuth + recognize
# ===========================================================================

def _make_oauth_resp(token="TOK_123"):
    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"access_token": token, "expires_at": 9999999999}
    return _Resp


def _make_stt_resp(text="Привет, это тест"):
    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"result": [{"normalized_text": text}]}
    return _Resp


@pytest.mark.asyncio
async def test_salute_caches_token_across_calls():
    provider = SaluteSpeechProvider(
        client_id="cid", client_secret="csec", scope="SALUTE_SPEECH_PERS"
    )

    oauth_hits: list[dict] = []
    stt_hits: list[dict] = []

    OauthResp = _make_oauth_resp()
    SttResp = _make_stt_resp("первый ответ")

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, *, headers=None, data=None, content=None, params=None):
            if "oauth" in url:
                oauth_hits.append({"headers": headers, "data": data})
                return OauthResp()
            stt_hits.append({
                "url": url, "headers": headers,
                "content_len": len(content or b""), "params": params,
            })
            return SttResp()

    with patch.object(salute_mod.httpx, "AsyncClient", _Client):
        out1 = await provider.transcribe(b"\x00\x01audio1", "ru")
        out2 = await provider.transcribe(b"\x00\x01audio2", "ru")

    assert out1 == "первый ответ"
    assert out2 == "первый ответ"
    # Token cached → exactly ONE oauth call across both transcriptions
    assert len(oauth_hits) == 1
    assert len(stt_hits) == 2
    # STT endpoint received the audio bytes and language param
    assert stt_hits[0]["params"] == {"language": "ru"}
    assert stt_hits[0]["headers"]["Authorization"] == "Bearer TOK_123"
    assert stt_hits[0]["headers"]["Content-Type"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_salute_oauth_failure_raises_stt_error():
    provider = SaluteSpeechProvider(client_id="cid", client_secret="csec")

    class _BadResp:
        status_code = 401
        text = "unauthorized"
        def json(self):
            return {"error": "unauthorized"}

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *_a, **_kw):
            return _BadResp()

    with patch.object(salute_mod.httpx, "AsyncClient", _Client):
        with pytest.raises(SttError) as exc:
            await provider.transcribe(b"\x00\x01", "ru")
    assert "salute_oauth_status_401" in str(exc.value)


@pytest.mark.asyncio
async def test_salute_returns_empty_on_silent_audio():
    provider = SaluteSpeechProvider(client_id="cid", client_secret="csec")

    OauthResp = _make_oauth_resp()
    class _EmptyResp:
        status_code = 200
        text = "{}"
        def json(self):
            return {"result": []}

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, *, headers=None, data=None, content=None, params=None):
            return OauthResp() if "oauth" in url else _EmptyResp()

    with patch.object(salute_mod.httpx, "AsyncClient", _Client):
        text = await provider.transcribe(b"silent", "ru")
    assert text == ""


@pytest.mark.asyncio
async def test_salute_missing_creds_raises_before_network():
    provider = SaluteSpeechProvider(client_id="", client_secret="")
    with pytest.raises(SttError) as exc:
        await provider.transcribe(b"\x00\x01", "ru")
    assert "salute_not_configured" in str(exc.value)


# ===========================================================================
# transcribe_call_async — orchestration
# ===========================================================================

class _FakeSession:
    """Minimal AsyncSession surrogate: records execute side-effects in
    order, lets the caller mutate plain Python objects as 'rows'."""

    def __init__(self, execute_results):
        self._results = list(execute_results)
        self.commits = 0

    async def execute(self, _stmt):
        return self._results.pop(0)

    async def commit(self):
        self.commits += 1


def _make_engine_factory(session):
    engine = MagicMock()
    engine.dispose = AsyncMock()

    @asynccontextmanager
    async def _factory_ctx():
        yield session

    def factory():
        return _factory_ctx()

    return engine, factory


def _patch_engine_factory(monkeypatch, session, *, refresh_capture=None):
    """Inject a fake `app.scheduled.jobs` module into sys.modules so the
    lazy `from app.scheduled.jobs import ...` inside transcribe_call_async
    picks up our stubs rather than importing the real Celery-dependent
    module."""
    engine, factory = _make_engine_factory(session)

    fake_jobs = ModuleType("app.scheduled.jobs")
    fake_jobs._build_task_engine_and_factory = lambda: (engine, factory)

    if refresh_capture is not None:
        class _FakeRefresh:
            @staticmethod
            def apply_async(*, args, countdown):
                refresh_capture.append((args, countdown))
        fake_jobs.lead_agent_refresh_suggestion = _FakeRefresh
    else:
        class _NoopRefresh:
            @staticmethod
            def apply_async(*, args, countdown): pass
        fake_jobs.lead_agent_refresh_suggestion = _NoopRefresh

    monkeypatch.setitem(sys.modules, "app.scheduled.jobs", fake_jobs)
    return engine, factory


def _scalar(value):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    return r


def _scalars(rows):
    r = MagicMock()
    inner = MagicMock()
    inner.__iter__ = lambda self: iter(rows)
    r.scalars = MagicMock(return_value=inner)
    return r


@pytest.mark.asyncio
async def test_transcribe_writes_transcript_summary_and_kicks_agent(monkeypatch):
    """End-to-end happy path through the orchestrator."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.channel = "phone"
    msg.call_status = "answered"
    msg.media_url = "https://mango.example/rec.mp3"
    msg.lead_id = uuid.uuid4()
    msg.call_duration = 252
    msg.transcript = None
    msg.summary = None
    msg.stt_provider = None

    # The orchestrator does TWO executes when there is a matched lead +
    # summary: 1) load InboxMessage, 2) load matching Activities.
    activity = MagicMock()
    activity.payload_json = {"inbox_message_id": str(msg.id)}
    activity.body = "📞 Звонок 4:12"

    session = _FakeSession([_scalar(msg), _scalars([activity])])
    refresh_calls: list[tuple] = []
    _patch_engine_factory(monkeypatch, session, refresh_capture=refresh_calls)

    # Fake STT
    fake_stt = MagicMock()
    fake_stt.provider_name = "salute"
    fake_stt.transcribe = AsyncMock(
        return_value="Менеджер: Здравствуйте. Клиент: Здравствуйте."
    )
    monkeypatch.setattr(tasks_mod, "get_stt_provider", lambda: fake_stt)

    # Fake httpx audio download
    class _AudioResp:
        status_code = 200
        content = b"\x00\x01\x02fake-mp3"

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            return _AudioResp()

    monkeypatch.setattr(tasks_mod.httpx, "AsyncClient", _Client)

    # Fake LLM summary
    fake_completion = MagicMock()
    fake_completion.text = "Клиент уточнял условия пилота. Договорились выслать КП до пятницы."

    async def _fake_complete(**kwargs):
        return fake_completion

    fake_factory_mod = ModuleType("app.enrichment.providers.factory")
    fake_factory_mod.complete_with_fallback = _fake_complete
    # `app.enrichment.providers.__init__` re-exports get_llm_provider
    # from the factory — keep the symbol on the stub so the package
    # import doesn't blow up when it runs for the first time here.
    fake_factory_mod.get_llm_provider = MagicMock()
    monkeypatch.setitem(sys.modules, "app.enrichment.providers.factory", fake_factory_mod)

    out = await tasks_mod.transcribe_call_async(msg.id)

    assert out["status"] == "ok"
    assert out["provider"] == "salute"
    # transcript + summary persisted onto the row
    assert msg.transcript.startswith("Менеджер:")
    assert msg.summary.startswith("Клиент уточнял")
    assert msg.stt_provider == "salute"
    # Activity body now leads with the summary
    assert "Клиент уточнял" in activity.body
    # 60-sec lead-agent kick scheduled
    assert refresh_calls == [([str(msg.lead_id)], 60)]
    assert session.commits >= 1


@pytest.mark.asyncio
async def test_transcribe_skips_missed_calls(monkeypatch):
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.channel = "phone"
    msg.call_status = "missed"
    msg.media_url = None
    msg.lead_id = None

    session = _FakeSession([_scalar(msg)])
    _patch_engine_factory(monkeypatch, session)

    out = await tasks_mod.transcribe_call_async(msg.id)
    assert out["status"] == "nothing_to_transcribe"


@pytest.mark.asyncio
async def test_transcribe_records_provider_on_stt_failure(monkeypatch):
    """STT errors must not lose the row — `stt_provider` is stamped so
    we can see which provider failed without re-running."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.channel = "phone"
    msg.call_status = "answered"
    msg.media_url = "https://mango.example/rec.mp3"
    msg.lead_id = uuid.uuid4()
    msg.transcript = None
    msg.summary = None
    msg.stt_provider = None

    session = _FakeSession([_scalar(msg)])
    _patch_engine_factory(monkeypatch, session)

    fake_stt = MagicMock()
    fake_stt.provider_name = "salute"
    fake_stt.transcribe = AsyncMock(side_effect=SttError("salute_status_500"))
    monkeypatch.setattr(tasks_mod, "get_stt_provider", lambda: fake_stt)

    class _AudioResp:
        status_code = 200
        content = b"audio"

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, _url):
            return _AudioResp()

    monkeypatch.setattr(tasks_mod.httpx, "AsyncClient", _Client)

    out = await tasks_mod.transcribe_call_async(msg.id)

    assert out["status"].startswith("stt_failed:")
    assert msg.stt_provider == "salute"
    # Transcript stays None — nothing to write
    assert msg.transcript is None
