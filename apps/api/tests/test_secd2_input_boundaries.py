"""SEC-D2 oracle — входящие запросы: X-Forwarded-For rate-limit bypass
(SEC-DELTA-004) + webhook auth/dedup/body-size boundary checks.

Mock-only, mirrors tests/test_public_submit.py's stub pattern (sqlalchemy +
redis stubbed at import time, handler invoked directly — no TestClient,
no real Postgres). Run against drinkx_ci5 per the SEC-D2 task contract;
none of the tests here actually touch a database, they assert on mock
call sequencing (was the write helper called before/after the guard).

Root cause under test (`app/forms/public_routers.py::_client_ip`):
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()   # <-- LEFTMOST hop

nginx (infra/production/nginx/crm.drinkx.tech.conf) sets:
    proxy_set_header X-Real-IP $remote_addr;                  # trustworthy
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # appends
        # the real client IP to whatever XFF value the client already sent,
        # so the ATTACKER-CONTROLLED value ends up leftmost, not rightmost.

A caller can therefore send `X-Forwarded-For: 10.0.0.<i>` with i incrementing
every request and the per-IP rate limiter keys each request under a
different (slug, ip) bucket — the limit never trips no matter how many
requests land from the same real connection.

INPUT-01 tests below are expected to FAIL against the current
`_client_ip` (counter-example) and to PASS once the fix reads the
proxy-set `X-Real-IP` (or the rightmost XFF hop, with 1 trusted proxy)
ahead of a client-supplied XFF value.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy / redis stubs — identical approach to test_public_submit.py so
# this file can be collected standalone without a real DB/redis package.
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

    sa_exc.IntegrityError = _IntegrityError

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


def _stub_redis():
    if "redis" in sys.modules:
        return
    redis_mod = ModuleType("redis")
    redis_async = ModuleType("redis.asyncio")
    redis_async.Redis = object
    redis_async.from_url = lambda *a, **kw: MagicMock()
    redis_mod.asyncio = redis_async
    sys.modules["redis"] = redis_mod
    sys.modules["redis.asyncio"] = redis_async


_stub_redis()

import app.forms.public_routers as public_mod  # noqa: E402
from app.forms.rate_limit import check_rate_limit  # noqa: E402
import app.inbox.webhooks as webhooks_mod  # noqa: E402

# Trigger ORM mapper configuration for models with string-referenced
# relationships, same defensive import as tests/test_failclosed_defaults.py.
from app.contacts.models import Contact  # noqa: F401,E402
from app.followups.models import Followup  # noqa: F401,E402
from app.activity.models import Activity  # noqa: F401,E402


WS = uuid.uuid4()
LIMIT = 10  # matches settings.form_rate_limit_per_minute in test_public_submit.py


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors tests/test_public_submit.py)
# ---------------------------------------------------------------------------

def _make_form(*, slug="test-form-abc123", is_active=True):
    return type("WebFormStub", (), {
        "id": uuid.uuid4(),
        "workspace_id": WS,
        "slug": slug,
        "name": "Test Form",
        "fields_json": [],
        "target_pipeline_id": None,
        "target_stage_id": None,
        "redirect_url": "https://example.com/thanks",
        "is_active": is_active,
        "submissions_count": 0,
        "source_label": None,
        "notify_email": None,
        "default_assignee_id": None,
        "contact_task_sla_hours": 2,
        "ingest_token": None,
        "autoreply_enabled": False,
        "autoreply_subject": None,
        "autoreply_body": None,
    })()


def _make_lead(company_name="Stars Coffee"):
    return type("LeadStub", (), {
        "id": uuid.uuid4(),
        "workspace_id": WS,
        "company_name": company_name,
        "assigned_to": None,
    })()


def _make_request(*, headers=None, client_host="203.0.113.9"):
    req = MagicMock()
    req.headers = headers or {}
    req.client = MagicMock()
    req.client.host = client_host
    return req


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    empty = MagicMock()
    empty.all = MagicMock(return_value=[])
    db.execute.return_value = empty
    return db


class _InMemoryRedis:
    """Minimal Redis stand-in that actually implements INCR semantics
    per key, so distinct rate-limit keys behave independently — the
    same in-memory-fallback idea the task contract points at, scoped
    to just incr/expire since that's all check_rate_limit touches."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None


async def _run_submit(*, request, redis_client, form=None, db=None):
    """Drive submit_form far enough to observe whether the DB write
    path (create_lead_from_submission) was reached — i.e. whether the
    request got past the rate limiter."""
    form = form or _make_form()
    lead = _make_lead()
    db = db or _make_db()
    create_lead = AsyncMock(return_value=lead)

    with patch("app.forms.public_routers.get_bytes_redis", return_value=redis_client), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock(return_value=form)), \
         patch.object(public_mod, "create_lead_from_submission", new=create_lead), \
         patch.object(public_mod, "FormSubmission", lambda **kw: MagicMock(**kw)), \
         patch("app.forms.repositories.increment_submissions_count", new=AsyncMock()):
        try:
            await public_mod.submit_form(
                slug=form.slug, request=request, payload={"company_name": "X"}, db=db,
            )
            blocked = False
        except Exception as exc:  # noqa: BLE001
            from fastapi import HTTPException
            if isinstance(exc, HTTPException) and exc.status_code == 429:
                blocked = True
            else:
                raise
    return blocked, create_lead, db


# ===========================================================================
# INPUT-01 — XFF spoofing must not bypass the per-IP submit rate limit
# ===========================================================================

@pytest.mark.asyncio
async def test_input01_xff_spoofing_bypasses_rate_limit_COUNTEREXAMPLE():
    """Counter-example — EXPECTED TO FAIL against current `_client_ip`.

    Models nginx's actual proxying (`proxy_set_header X-Forwarded-For
    $proxy_add_x_forwarded_for;`): nginx APPENDS the real TCP peer
    ($remote_addr) to whatever XFF value the client already sent, so the
    header FastAPI receives is `"<attacker-value>, <real-client-ip>"` -
    real IP is the RIGHTMOST hop, attacker value is leftmost. The real
    connection (real client IP, appended by nginx) is constant across
    requests; only the attacker-controlled leftmost hop changes. With the
    current leftmost-hop extraction every request lands in its own
    rate-limit bucket, so LIMIT+1 requests all succeed instead of the
    (LIMIT+1)-th being blocked with 429.

    Mutation check (done manually against this file, not committed):
    swapping `_client_ip` to take the RIGHTMOST XFF hop (or trust
    X-Real-IP) makes this test pass; reverting to `xff.split(",")[0]`
    makes it fail again - confirms the oracle is targeted at the actual
    root cause.
    """
    redis_client = _InMemoryRedis()
    blocked_flags = []
    for i in range(LIMIT + 1):
        req = _make_request(
            # nginx-appended form: attacker's spoofed value (changes every
            # request) + the real client IP nginx tacked on (constant).
            headers={"x-forwarded-for": f"10.0.0.{i}, 203.0.113.9"},
            client_host="127.0.0.1",  # nginx itself, as seen by uvicorn
        )
        blocked, create_lead, _db = await _run_submit(request=req, redis_client=redis_client)
        blocked_flags.append(blocked)
        if not blocked:
            create_lead.assert_awaited_once()

    assert blocked_flags[-1] is True, (
        "SEC-DELTA-004: request #{} (attacker sent a fresh X-Forwarded-For "
        "each time) was NOT rate-limited — spoofing X-Forwarded-For bypasses "
        "the per-IP submit limit entirely.".format(LIMIT + 1)
    )


@pytest.mark.asyncio
async def test_input01_legitimate_traffic_is_rate_limited_control():
    """Allowed control — passes today. No XFF header at all (direct
    connection / dev), so `_client_ip` falls back to request.client.host,
    which IS stable across requests. LIMIT requests succeed, the
    (LIMIT+1)-th is blocked."""
    redis_client = _InMemoryRedis()
    blocked_flags = []
    for _ in range(LIMIT + 1):
        req = _make_request(headers={}, client_host="203.0.113.9")
        blocked, _create_lead, _db = await _run_submit(request=req, redis_client=redis_client)
        blocked_flags.append(blocked)

    assert blocked_flags[:LIMIT] == [False] * LIMIT
    assert blocked_flags[LIMIT] is True


@pytest.mark.asyncio
async def test_input01_rate_limit_enforced_before_any_write():
    """Already true today (check_rate_limit runs before get_by_slug /
    create_lead_from_submission) — regression guard, not the bug itself.
    A blocked (429) request must not touch the DB write path at all."""
    redis_client = _InMemoryRedis()
    key_ip = "203.0.113.9"
    # Burn through the limit first.
    for _ in range(LIMIT):
        req = _make_request(headers={}, client_host=key_ip)
        await _run_submit(request=req, redis_client=redis_client)

    req = _make_request(headers={}, client_host=key_ip)
    form = _make_form()
    db = _make_db()
    with patch("app.forms.public_routers.get_bytes_redis", return_value=redis_client), \
         patch("app.forms.repositories.get_by_slug", new=AsyncMock(return_value=form)) as gbs:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await public_mod.submit_form(
                slug=form.slug, request=req, payload={"company_name": "X"}, db=db,
            )
    assert exc_info.value.status_code == 429
    gbs.assert_not_called()      # form lookup never ran
    db.add.assert_not_called()   # no submission row staged


@pytest.mark.asyncio
async def test_input01_x_real_ip_should_be_trusted_over_client_supplied_xff():
    """EXPECTED TO FAIL against current `_client_ip` — it never reads
    X-Real-IP at all. nginx sets `X-Real-IP: $remote_addr` (the actual
    TCP peer, not attacker-influenceable) on every proxied request; the
    fix should prefer it over a client-supplied X-Forwarded-For. Here a
    fixed X-Real-IP is sent with a different spoofed XFF value on each
    request — a fixed rate-limit key means the (LIMIT+1)-th request
    should be blocked."""
    redis_client = _InMemoryRedis()
    blocked_flags = []
    for i in range(LIMIT + 1):
        req = _make_request(
            headers={
                "x-real-ip": "198.51.100.5",       # nginx-set, trustworthy
                "x-forwarded-for": f"10.0.0.{i}",   # attacker-controlled
            },
            client_host="127.0.0.1",  # nginx itself, as seen by uvicorn
        )
        blocked, _create_lead, _db = await _run_submit(request=req, redis_client=redis_client)
        blocked_flags.append(blocked)

    assert blocked_flags[-1] is True, (
        "X-Real-IP (nginx-trustworthy) was not used as the rate-limit key — "
        "a spoofed X-Forwarded-For still won."
    )


# ===========================================================================
# INPUT-02 — webhook auth must reject before any write; dedup behavior
# ===========================================================================

@pytest.mark.asyncio
async def test_input02_telegram_bad_secret_rejected_before_receive():
    """No existing route-level test covers this (adapter-only tests exist
    in tests/test_inbox_telegram.py). Exercises the actual
    `telegram_webhook` endpoint: wrong/missing
    X-Telegram-Bot-Api-Secret-Token must 401 and must NOT call
    message_services.receive (no write)."""
    from fastapi import HTTPException

    settings = MagicMock()
    settings.telegram_webhook_secret = "correct-secret"
    req = MagicMock()
    req.json = AsyncMock(return_value={"update_id": 1})
    db = AsyncMock()

    with patch.object(webhooks_mod, "get_settings", return_value=settings), \
         patch.object(webhooks_mod.message_services, "receive", new=AsyncMock()) as recv:
        with pytest.raises(HTTPException) as exc_info:
            await webhooks_mod.telegram_webhook(
                request=req, db=db, x_telegram_bot_api_secret_token="wrong-secret",
            )
    assert exc_info.value.status_code == 401
    recv.assert_not_awaited()


@pytest.mark.asyncio
async def test_input02_telegram_missing_secret_header_rejected():
    """Same endpoint, no header at all (default None) — also 401."""
    from fastapi import HTTPException

    settings = MagicMock()
    settings.telegram_webhook_secret = "correct-secret"
    req = MagicMock()
    req.json = AsyncMock(return_value={"update_id": 1})
    db = AsyncMock()

    with patch.object(webhooks_mod, "get_settings", return_value=settings), \
         patch.object(webhooks_mod.message_services, "receive", new=AsyncMock()) as recv:
        with pytest.raises(HTTPException) as exc_info:
            await webhooks_mod.telegram_webhook(
                request=req, db=db, x_telegram_bot_api_secret_token=None,
            )
    assert exc_info.value.status_code == 401
    recv.assert_not_awaited()


# Mango bad-sign → 401 before write: already covered, not duplicated here.
#   tests/test_failclosed_defaults.py::test_mango_any_env_salt_set_bad_sign_returns_401
#
# Telegram/Mango duplicate delivery (same external_id) → dedup IS
# implemented: `app/inbox/message_services.py::receive` pre-checks
# `(channel, external_id)` (UNIQUE INDEX uq_inbox_msg_external backs it)
# and returns `(existing_message, created=False)` without inserting a
# second row. Already covered, not duplicated here:
#   tests/test_inbox_messages.py::test_receive_dedups_by_external_id
# This is documented FACTUAL BEHAVIOR (dedup exists), not a gap —
# no `decision` item needed for the dedup question itself.


# ===========================================================================
# INPUT-03 — body size / SSRF / redirect / timeout on outbound + inbound
# ===========================================================================

# Outbound SSRF guard (three outbound paths), web_fetch redirect
# re-validation and timeout: already covered per the SEC-D2 contract,
# not re-tested here:
#   app/common/ssrf.py + its test suite
#   app/enrichment/sources/web_fetch.py (redirect re-validation + timeout)
#
# Inbound webhook body size: there is no FastAPI/app-level Content-Length
# or body-size guard on `/api/webhooks/telegram` or `/api/webhooks/phone`
# (grepped app/inbox/webhooks.py — no check). The only backstop is
# infra-level: infra/production/nginx/crm.drinkx.tech.conf sets
# `client_max_body_size 25M;` at the server-block level, which covers the
# `/api/` location (webhooks included) — nginx returns 413 before the
# request reaches FastAPI. This is DOCUMENTED FACTUAL BEHAVIOR, not
# exercisable from a pytest unit test (it's nginx's job, not app code's).
# Per contract non-goals ("DoS-нагрузка... не в скоуп") this is left as a
# `decision` item, not a fix candidate: an app-level guard is redundant
# with the nginx limit today, but would matter if a future deployment
# path (e.g. direct-to-uvicorn) skips nginx.
