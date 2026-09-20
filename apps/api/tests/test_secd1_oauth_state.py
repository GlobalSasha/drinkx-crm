"""SEC-D1 (P2-12 -> SEC-DELTA-001) -- Gmail OAuth `state` signing key.

`app/inbox/oauth.py::_state_signing_key` falls back to the hardcoded
string "drinkx-dev-state-key" whenever `settings.supabase_jwt_secret`
is empty -- with no gate on `app_env`. `gmail/callback` trusts the
identity recovered from `verify_state` with no `current_user` check
(by design -- the browser lands there without a Bearer header), so the
signing key IS the access-control boundary for "whose mailbox gets
linked to whose account".

Contract: scratchpad/program/contracts/SEC-D1_TASK_CONTRACT.md
Repro:    scratchpad/program/SEC-D1/REPRO.md

AUTH-01 / AUTH-03 are written to the SECURE contract and are expected to
FAIL against the current code -- that failure is the counterexample this
file exists to pin down. AUTH-02 documents the working control case.
AUTH-04 is not reproduced here -- see the note above that test.

Isolation notes (audit-integration round, drinkx_ci shared run):
- `gmail_callback` calls `await db.commit()` on success, which is a REAL
  Postgres commit -- not something the per-test `db` fixture's trailing
  `rollback()` can undo. Every test below that drives a callback all the
  way to a successful link therefore explicitly deletes the Workspace it
  created (cascades to User/ChannelConnection rows via `ondelete=CASCADE`)
  in a `finally`, so no row survives the test into the shared DB. Without
  this, a later, unrelated test's "oldest workspace" query
  (`app/auth/services.py`'s `ORDER BY created_at ASC LIMIT 1`) can pick up
  an orphaned workspace committed here and fail for a reason that has
  nothing to do with what it's testing.
- `celery_app.send_task` is stubbed for every callback call (same pattern
  as `tests/test_export_access.py`) -- with no broker running, the
  Celery Redis result backend was retrying for ~20s per successful
  callback (`Connection to Redis lost: Retry (0/20)...(19/20)`), which
  was the actual source of the ~78s runtime, not slowness in the code
  under test. Stubbing is scoped to a single call (`get`/`set` around
  the request) and restored in `finally`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 - configures SQLAlchemy mappers
from app.config import Settings
from app.inbox import oauth as oauth_helpers
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

DEV_FALLBACK_CONSTANT = "drinkx-dev-state-key"  # the literal from app/inbox/oauth.py


def _forge_state(user_id: uuid.UUID, *, secret: str, ttl: int = 600) -> str:
    """Compute a `state` token exactly the way `sign_state` does, so we
    can forge one for an arbitrary user_id without calling sign_state
    (an attacker who only knows the fallback constant is in the same
    position: they never had access to a legitimate signing call)."""
    exp = int(time.time()) + ttl
    payload = f"{user_id}.{exp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    pl_b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    return f"{pl_b64}.{sig_b64}"


async def _make_user(db, workspace_id, *, email_prefix: str):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{email_prefix}-{uuid.uuid4().hex[:6]}@example.com",
        name=email_prefix,
        role="manager",
    )
    db.add(u)
    await db.flush()
    return u


async def _cleanup_workspace(db, workspace_id) -> None:
    """Undo a REAL commit made by the gmail_callback endpoint.

    `db.commit()` inside the router is a genuine Postgres commit on the
    shared test database -- the per-test `db` fixture's `rollback()`
    (called after the test returns) is a no-op once that has already
    happened. Deleting the Workspace here, in the SAME session, and
    committing that delete, cascades (ondelete=CASCADE) to every User
    and ChannelConnection row this test created, so nothing leaks into
    whatever test runs next in the same process/database.
    """
    from sqlalchemy import delete

    from app.auth.models import Workspace

    await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
    await db.commit()


async def _callback(db, settings_obj, *, code: str | None, state: str | None):
    """GET /api/inbox/gmail/callback with get_settings patched inside
    app.inbox.oauth (the module that owns the signing key + client
    config), token exchange stubbed (no real network/Google), and the
    Celery dispatch stubbed (no real/attempted network to Redis)."""
    from app.db import get_db
    from app.main import app
    from app.scheduled.celery_app import celery_app

    app.dependency_overrides[get_db] = lambda: db

    orig_get_settings = oauth_helpers.get_settings
    orig_exchange = oauth_helpers.exchange_code_for_credentials
    orig_send_task = celery_app.send_task
    oauth_helpers.get_settings = lambda: settings_obj
    oauth_helpers.exchange_code_for_credentials = lambda _code: {
        "token": "attacker-access-token",
        "refresh_token": "attacker-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "stub",
        "client_secret": "stub",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        "expiry": None,
    }
    celery_app.send_task = lambda *a, **kw: None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            params = {}
            if code is not None:
                params["code"] = code
            if state is not None:
                params["state"] = state
            return await client.get(
                "/api/inbox/gmail/callback", params=params, follow_redirects=False
            )
    finally:
        oauth_helpers.get_settings = orig_get_settings
        oauth_helpers.exchange_code_for_credentials = orig_exchange
        celery_app.send_task = orig_send_task
        app.dependency_overrides.clear()


async def _connection_for(db, user_id):
    from sqlalchemy import select

    from app.inbox.models import ChannelConnection

    res = await db.execute(
        select(ChannelConnection).where(
            ChannelConnection.user_id == user_id,
            ChannelConnection.channel_type == "gmail",
        )
    )
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# AUTH-01 -- forged state (empty secret, known fallback constant)
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_auth01_forged_state_with_empty_secret_must_not_link_victim_mailbox(db, workspace):
    """Contract AUTH-01 (forgery leg): with `supabase_jwt_secret=""`, an
    attacker who knows the source-level fallback constant can compute a
    valid HMAC for ANY user_id without ever calling sign_state.

    Expected (secure): verify_state must not accept a signature made with
    the hardcoded constant once real config is missing -- callback must
    reject and no ChannelConnection may be written for the victim.

    Actual (current code): the callback accepts the forged state and
    upserts a ChannelConnection for the victim's user_id containing the
    ATTACKER's exchanged tokens (the attacker did their own Google
    consent; the code-exchange result is attributed to the victim
    because identity is taken solely from `state`). This is the
    counterexample -- this assertion is expected to FAIL on current code.
    """
    victim = await _make_user(db, workspace.id, email_prefix="victim")
    await db.flush()

    settings_empty_secret = Settings(
        supabase_jwt_secret="",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )
    forged_state = _forge_state(victim.id, secret=DEV_FALLBACK_CONSTANT)

    try:
        resp = await _callback(db, settings_empty_secret, code="attacker-code", state=forged_state)

        conn = await _connection_for(db, victim.id)

        # SECURE expectation: forged state rejected, nothing written for the victim.
        assert "invalid_state" in resp.headers.get("location", "") or resp.status_code >= 400, (
            f"forged state was accepted (redirect={resp.headers.get('location')!r}); "
            "empty-secret fallback lets anyone sign a state for any user_id"
        )
        assert conn is None, (
            "a ChannelConnection was written for the victim from a state forged "
            "with the hardcoded dev fallback constant -- see REPRO.md"
        )
    finally:
        await _cleanup_workspace(db, workspace.id)


@skip_no_pg
@pytest.mark.asyncio
async def test_auth01_state_signed_with_different_secret_is_rejected(db, workspace):
    """Contract AUTH-01 (wrong-signature leg): a state signed with a
    secret that does NOT match the verifying config must be rejected.
    This leg passes on current code -- verify_state's HMAC compare is
    otherwise sound; the vulnerability is specifically the fallback
    constant becoming the de-facto shared secret when config is empty.

    No commit reaches Postgres on this path (rejected before the
    upsert), so no explicit workspace cleanup is needed here -- the
    `db` fixture's trailing rollback is enough.
    """
    victim = await _make_user(db, workspace.id, email_prefix="victim2")
    await db.flush()

    settings_real_secret = Settings(
        supabase_jwt_secret="server-side-real-secret-abc123",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )
    forged_state = _forge_state(victim.id, secret="some-other-guess")

    resp = await _callback(db, settings_real_secret, code="attacker-code", state=forged_state)
    conn = await _connection_for(db, victim.id)

    assert "invalid_state" in resp.headers.get("location", "")
    assert conn is None


# ---------------------------------------------------------------------------
# AUTH-02 -- valid state, synthetic test secret configured
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_auth02_valid_state_links_mailbox_to_the_right_user(db, workspace):
    """Control case: with a real (synthetic, test-only) secret configured
    on both ends, a legitimately signed state links the mailbox to the
    SAME user who started the flow. Token exchange is stubbed."""
    user = await _make_user(db, workspace.id, email_prefix="owner")
    await db.flush()

    settings_ok = Settings(
        supabase_jwt_secret="synthetic-test-secret-for-secd1",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )

    orig_get_settings = oauth_helpers.get_settings
    oauth_helpers.get_settings = lambda: settings_ok
    try:
        state = oauth_helpers.sign_state(user.id)
    finally:
        oauth_helpers.get_settings = orig_get_settings

    try:
        resp = await _callback(db, settings_ok, code="legit-code", state=state)
        conn = await _connection_for(db, user.id)

        assert "status=ok" in resp.headers.get("location", "")
        assert conn is not None
        assert conn.workspace_id == workspace.id
        assert conn.status == "active"
    finally:
        await _cleanup_workspace(db, workspace.id)


@skip_no_pg
@pytest.mark.asyncio
async def test_replay_of_a_still_valid_state_is_not_rejected(db, workspace):
    """Documents actual behavior (contract: 'record what actually
    happens', no fixed pass/fail expectation): `sign_state` has a TTL
    (10 minutes, see `_STATE_TTL_SECONDS`) but no nonce/one-time-use
    marker. Replaying a still-valid state a second time within the TTL
    window is NOT rejected -- it re-runs the same upsert (idempotent on
    workspace_id, user_id, channel_type), so a captured-but-unexpired
    state can be replayed to re-arm/re-link the same connection until
    it expires. This is lower severity than AUTH-01 (bounded by the
    10-minute window and requires already intercepting a valid state)
    but is a real gap versus a one-time-use authorization code."""
    user = await _make_user(db, workspace.id, email_prefix="replay")
    await db.flush()

    settings_ok = Settings(
        supabase_jwt_secret="synthetic-test-secret-for-secd1",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )
    orig_get_settings = oauth_helpers.get_settings
    oauth_helpers.get_settings = lambda: settings_ok
    try:
        state = oauth_helpers.sign_state(user.id)
    finally:
        oauth_helpers.get_settings = orig_get_settings

    try:
        resp1 = await _callback(db, settings_ok, code="legit-code-1", state=state)
        resp2 = await _callback(db, settings_ok, code="legit-code-2", state=state)

        assert "status=ok" in resp1.headers.get("location", "")
        assert "status=ok" in resp2.headers.get("location", ""), (
            "actual behavior: replay within the TTL window is accepted "
            "(no nonce/one-time-use check in verify_state)"
        )
    finally:
        await _cleanup_workspace(db, workspace.id)


# ---------------------------------------------------------------------------
# AUTH-03 -- empty secret outside dev must not silently use the constant
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_auth03_empty_secret_in_production_must_refuse_not_use_constant():
    """Contract AUTH-03: with `supabase_jwt_secret=""` and `app_env`
    NOT a dev mode, `sign_state`/`verify_state` must refuse rather than
    silently sign with the hardcoded constant -- the same fail-closed
    pattern already used elsewhere in this codebase for exactly this
    shape of problem (see `app/inbox/crypto.py::encrypt_credentials`,
    which raises `CredentialsCryptoError` when `app_env == "production"`
    and no FERNET_KEY is configured, instead of falling back to
    plaintext).

    No `db`/`workspace` fixture, no HTTP call, no commit -- nothing to
    clean up.

    Expected (secure): raises before returning a token signed with the
    fallback constant.
    Actual (current code): `_state_signing_key()` has no `app_env`
    check at all -- it always falls back silently. This assertion is
    expected to FAIL on current code; that failure is the
    counterexample.
    """
    settings_prod_empty_secret = Settings(
        app_env="production",
        supabase_jwt_secret="",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )
    orig_get_settings = oauth_helpers.get_settings
    oauth_helpers.get_settings = lambda: settings_prod_empty_secret
    try:
        with pytest.raises(Exception):
            oauth_helpers.sign_state(uuid.uuid4())
    finally:
        oauth_helpers.get_settings = orig_get_settings


# ---------------------------------------------------------------------------
# QA follow-up (2026-09-21) -- implementer's actual fix (210d5ba) deviates
# from the contract's suggested shape: instead of gating the ephemeral
# fallback on an explicit dev/test flag, it gates it on `app_env ==
# "production"` being FALSE -- i.e. every non-production app_env (dev,
# test, staging, anything else) gets a per-process RANDOM key with a
# warning log, not the old hardcoded constant. These tests pin down that
# actual behavior end-to-end (connect-gmail HTTP shape + callback) so a
# regression back to the hardcoded constant, or a regression that makes
# prod fall through to the ephemeral path, is caught.
# ---------------------------------------------------------------------------

async def _connect_gmail(user, settings_obj):
    """Call the connect-gmail endpoint function directly (bypasses the
    `current_user` FastAPI dependency -- same pattern the callback helper
    uses for `get_settings`), with `get_settings` patched in both modules
    the route touches: `app.inbox.routers` (google_client_id/secret gate)
    and `app.inbox.oauth` (the signing-key gate)."""
    from app.inbox import routers as inbox_routers

    orig_routers_settings = inbox_routers.get_settings
    orig_oauth_settings = oauth_helpers.get_settings
    inbox_routers.get_settings = lambda: settings_obj
    oauth_helpers.get_settings = lambda: settings_obj
    try:
        return await inbox_routers.connect_gmail(user=user)
    finally:
        inbox_routers.get_settings = orig_routers_settings
        oauth_helpers.get_settings = orig_oauth_settings


def _settings_with_google(**overrides) -> Settings:
    return Settings(
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
        **overrides,
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_auth03_production_empty_secret_connect_gmail_returns_503(db, workspace):
    """connect-gmail must refuse (503), not hand back a state signed with
    anything an attacker could reproduce, when app_env=production and no
    secret is configured."""
    from fastapi import HTTPException

    user = await _make_user(db, workspace.id, email_prefix="prod-connect")
    await db.flush()
    settings_prod_empty = _settings_with_google(app_env="production", supabase_jwt_secret="")

    with pytest.raises(HTTPException) as exc_info:
        await _connect_gmail(user, settings_prod_empty)
    assert exc_info.value.status_code == 503


@skip_no_pg
@pytest.mark.asyncio
async def test_auth03_production_empty_secret_callback_refuses_without_writing(db, workspace):
    """Even if an attacker forges *some* state (they cannot know the
    production secret, but this pins the fail-closed callback side too):
    with app_env=production and an empty secret, the callback must reject
    and the victim's ChannelConnection count must not grow."""
    victim = await _make_user(db, workspace.id, email_prefix="prod-victim")
    await db.flush()
    settings_prod_empty = Settings(
        app_env="production",
        supabase_jwt_secret="",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )
    forged_state = _forge_state(victim.id, secret=DEV_FALLBACK_CONSTANT)

    before = await _connection_for(db, victim.id)
    assert before is None

    resp = await _callback(db, settings_prod_empty, code="attacker-code", state=forged_state)
    after = await _connection_for(db, victim.id)

    assert "invalid_state" in resp.headers.get("location", "") or resp.status_code >= 400
    assert after is None, "ChannelConnection count grew despite production + empty secret"


@skip_no_pg
@pytest.mark.asyncio
async def test_dev_env_empty_secret_consent_to_callback_succeeds_in_one_process(db, workspace):
    """Contract deviation check: implementer chose a random per-process
    key (not the old hardcoded constant) for the non-production fallback.
    Within ONE process, consent (connect-gmail, via sign_state) followed
    by callback (verify_state) must still succeed -- the random key is
    stable for the process lifetime."""
    user = await _make_user(db, workspace.id, email_prefix="dev-consent")
    await db.flush()
    settings_dev_empty = _settings_with_google(app_env="development", supabase_jwt_secret="")

    result = await _connect_gmail(user, settings_dev_empty)
    assert "redirect_url" in result
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(result["redirect_url"]).query)
    state = qs["state"][0]

    try:
        resp = await _callback(db, settings_dev_empty, code="legit-code", state=state)
        conn = await _connection_for(db, user.id)

        assert "status=ok" in resp.headers.get("location", "")
        assert conn is not None
        assert conn.user_id == user.id
    finally:
        await _cleanup_workspace(db, workspace.id)


@skip_no_pg
@pytest.mark.asyncio
async def test_dev_env_empty_secret_rejects_state_signed_with_old_hardcoded_constant(db, workspace):
    """The fix's whole point: even in dev, with an empty secret, a state
    forged with the OLD hardcoded constant `drinkx-dev-state-key` must be
    rejected -- the actual key is now a random per-process value the
    constant cannot predict. This is the AUTH-01/AUTH-03 forgery leg
    re-run against the (now non-production) dev/test path specifically,
    since the implementer's fallback applies there too."""
    victim = await _make_user(db, workspace.id, email_prefix="dev-victim")
    await db.flush()
    settings_dev_empty = Settings(
        app_env="development",
        supabase_jwt_secret="",
        google_client_id="fake-client-id",
        google_client_secret="fake-client-secret",
    )
    forged_state = _forge_state(victim.id, secret=DEV_FALLBACK_CONSTANT)

    resp = await _callback(db, settings_dev_empty, code="attacker-code", state=forged_state)
    conn = await _connection_for(db, victim.id)

    assert "invalid_state" in resp.headers.get("location", "") or resp.status_code >= 400
    assert conn is None


# ---------------------------------------------------------------------------
# AUTH-04 -- user role change/removal after linking
# ---------------------------------------------------------------------------

# Not reproduced in this file. Per contract, AUTH-04 is
# covered-by-accepted-evidence from SEC-06/SEC2 (lead/access-domain
# revocation-on-role-change work already merged -- see git log
# `fix(security): SEC2-F1/F2/T1` and `fix(security): SEC-01` on this
# branch). Those tests exercise "does a demoted/removed user keep
# access" for leads/exports/tasks; nothing in inbox/oauth.py reads
# role at link time (it only resolves user_id -> User row), so there
# is no separate oauth-specific AUTH-04 surface to add here.
