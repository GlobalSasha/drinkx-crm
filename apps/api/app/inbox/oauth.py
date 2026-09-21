"""Gmail OAuth helpers — build consent URL and exchange code for tokens.

The user already has a Supabase Google sign-in. The Gmail readonly scope
is consented to *separately* — Google will show a fresh consent screen
because the requested scopes differ. We do NOT touch Supabase auth here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlencode
from uuid import UUID

import structlog

# Google returns extra scopes (openid, userinfo.*) on top of the requested
# gmail.readonly when the user already granted them via Supabase sign-in.
# Relax oauthlib's strict scope check before importing Flow.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google_auth_oauthlib.flow import Flow  # noqa: E402

from app.config import get_settings

log = structlog.get_logger()

_STATE_TTL_SECONDS = 600  # consent flow must complete within 10 min

# Ключ на время жизни процесса — запасной вариант ТОЛЬКО для локальной
# разработки, когда SUPABASE_JWT_SECRET не задан. Он случайный, поэтому
# подписать state им снаружи нельзя; внутри одного процесса цикл
# consent → callback (10 минут) отрабатывает как обычно.
_EPHEMERAL_DEV_KEY = secrets.token_bytes(32)
_warned_ephemeral = False


class OAuthStateKeyError(Exception):
    """Ключ подписи OAuth-state не настроен там, где он обязателен."""


def _redirect_uri() -> str:
    s = get_settings()
    return f"{s.api_base_url.rstrip('/')}/api/inbox/gmail/callback"


def _scope_list() -> list[str]:
    s = get_settings()
    return [scope.strip() for scope in s.gmail_scopes.split() if scope.strip()]


def _client_config() -> dict:
    s = get_settings()
    return {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }


def build_consent_url(state: str) -> str:
    """Return the Google consent URL the user is redirected to.

    `state` is an opaque token tying the callback back to the user that
    started the flow (we sign it with the JWT secret).
    """
    flow = Flow.from_client_config(
        _client_config(),
        scopes=_scope_list(),
        redirect_uri=_redirect_uri(),
        autogenerate_code_verifier=False,   # disable PKCE — confidential client, secret is present
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",        # required to receive a refresh_token
        include_granted_scopes="true",
        prompt="consent",             # force refresh_token even on re-auth
        state=state,
    )
    return auth_url


def exchange_code_for_credentials(code: str) -> dict:
    """Exchange the OAuth `code` for access + refresh tokens.

    Returns the JSON payload to persist as
    ChannelConnection.credentials_json. Caller passes this to
    GmailClient on the next call.
    """
    flow = Flow.from_client_config(
        _client_config(),
        scopes=_scope_list(),
        redirect_uri=_redirect_uri(),
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else _scope_list(),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def _state_signing_key() -> bytes:
    """Ключ подписи `state`.

    `gmail/callback` не может опереться на `current_user` — браузер
    приходит туда без нашего заголовка, — поэтому подпись state и есть
    граница «чей ящик к чьей учётке». Зашитая в исходники константа в
    роли ключа означала бы, что state за любого пользователя подпишет
    каждый, кто читал репозиторий.

    Поэтому: настроенный секрет — всегда; в production без секрета —
    отказ (тот же fail-closed, что в `app/inbox/crypto.py`); вне
    production — случайный ключ процесса и предупреждение в лог.
    """
    global _warned_ephemeral
    s = get_settings()
    secret = (s.supabase_jwt_secret or "").strip()
    if secret:
        return secret.encode("utf-8")
    if s.app_env == "production":
        log.error("inbox.oauth.state_key_missing_in_prod")
        raise OAuthStateKeyError(
            "SUPABASE_JWT_SECRET is not configured in production — refusing "
            "to sign or verify Gmail OAuth state"
        )
    if not _warned_ephemeral:
        _warned_ephemeral = True
        log.warning(
            "inbox.oauth.state_key_ephemeral",
            message=(
                "SUPABASE_JWT_SECRET not configured — Gmail OAuth state is "
                "signed with a random per-process key. Set SUPABASE_JWT_SECRET "
                "for anything other than local development."
            ),
        )
    return _EPHEMERAL_DEV_KEY


def sign_state(user_id: UUID) -> str:
    """Pack (user_id, exp) and HMAC-sign it. Returned token is opaque."""
    exp = int(time.time()) + _STATE_TTL_SECONDS
    payload = f"{user_id}.{exp}".encode("utf-8")
    sig = hmac.new(_state_signing_key(), payload, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    pl_b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    return f"{pl_b64}.{sig_b64}"


def verify_state(state: str) -> UUID | None:
    """Recover user_id from a signed state. Returns None on invalid/expired."""
    try:
        pl_b64, sig_b64 = state.split(".", 1)
        payload = base64.urlsafe_b64decode(pl_b64 + "=" * (-len(pl_b64) % 4))
        sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        expected = hmac.new(_state_signing_key(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        user_str, exp_str = payload.decode("utf-8").split(".", 1)
        if int(exp_str) < int(time.time()):
            return None
        return UUID(user_str)
    except (ValueError, TypeError):
        return None
    except OAuthStateKeyError:
        # Проверить подпись нечем — значит state недействителен.
        return None


def build_post_callback_redirect(*, success: bool, error: str | None = None) -> str:
    """Where the SPA lands after the Gmail OAuth callback.

    Sprint 3.7: /inbox was retired; redirect to /settings?section=channels
    so the user sees their connected accounts immediately after authorising.
    """
    s = get_settings()
    base = s.frontend_base_url.rstrip("/")
    params = {"connect": "gmail", "status": "ok" if success else "error"}
    if error:
        params["error"] = error[:200]
    return f"{base}/settings?section=channels&{urlencode(params)}"
