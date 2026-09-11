"""Thin wrapper around the Supabase auth admin API for user invites
— Sprint 2.4 G1.

We don't pull `supabase-py` (heavy dep + we only need two calls).
Instead we hit the GoTrue REST endpoints directly with httpx + the
already-configured `SUPABASE_SECRET_KEY` (service role key).

`POST {SUPABASE_URL}/auth/v1/invite`
  body: { "email": "..." }
  headers: Authorization: Bearer SERVICE_ROLE_KEY, apikey: SERVICE_ROLE_KEY

ВНИМАНИЕ на адрес. До 11.09.2026 здесь стоял
`/auth/v1/admin/invite_user_by_email` — это имя МЕТОДА в JS-SDK
(`supabase.auth.admin.inviteUserByEmail`), а не HTTP-путь. GoTrue отвечал на
него «404 page not found», приглашение падало с 502, и за всё время
существования invite-only ни одна строка в `user_invites` не создалась.

`POST {SUPABASE_URL}/auth/v1/otp` (`should_create_user: false`)
  Запасной путь: у человека уже есть аккаунт в Supabase — обычно потому, что
  он пробовал войти до того, как его пригласили, и получил отказ. `/invite`
  на такой адрес отвечает 422 email_exists. Это не провал приглашения:
  доступ в CRM даёт строка `user_invites`, а не наличие аккаунта. Шлём ему
  ссылку для входа и говорим сервису продолжать.

Stub-mode: when SUPABASE_SECRET_KEY is empty (dev), we log the
invitation instead of calling Supabase. Same pattern as the email
digest's stub-mode (Sprint 1.5).
"""
from __future__ import annotations

import enum

import structlog
import httpx

from app.config import get_settings

log = structlog.get_logger()


class SupabaseInviteError(Exception):
    """Raised when the Supabase admin API call fails. Router maps
    to HTTP 502 — the request was structurally correct, but our
    upstream couldn't deliver."""


class InviteOutcome(enum.Enum):
    """Что произошло с письмом. Обе ветки — успех для приглашения;
    различаются только тем, что увидит приглашающий."""

    INVITED = "invited"          # ушло приглашение
    SIGN_IN_LINK = "sign_in_link"  # аккаунт уже был — ушла ссылка для входа
    NOT_SENT = "not_sent"        # аккаунт уже был, письмо отправить не вышло


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def _is_email_exists(res: httpx.Response) -> bool:
    """GoTrue отдаёт 422 с error_code=email_exists (в старых версиях —
    msg «already been registered»). Ловим оба варианта."""
    if res.status_code not in (400, 422):
        return False
    body = res.text.lower()
    return "email_exists" in body or "already been registered" in body


async def _send_sign_in_link(
    client: httpx.AsyncClient, *, base: str, key: str, email: str
) -> bool:
    """Ссылка для входа тому, у кого аккаунт уже есть. Провал здесь не
    роняет приглашение — строка в `user_invites` и так откроет доступ,
    человеку просто придётся зайти самому."""
    try:
        res = await client.post(
            f"{base}/auth/v1/otp",
            headers=_headers(key),
            json={"email": email, "should_create_user": False},
        )
    except httpx.HTTPError as exc:
        log.warning("supabase.signin_link_network_error", email=email, error=str(exc)[:200])
        return False

    if res.status_code >= 400:
        log.warning(
            "supabase.signin_link_http_error",
            email=email,
            status=res.status_code,
            body=res.text[:500],
        )
        return False

    log.info("supabase.signin_link_sent", email=email)
    return True


async def send_invite_email(*, email: str) -> InviteOutcome:
    """Trigger Supabase to send a magic-link invitation email.

    On success: INVITED.
    When the address already has a Supabase account: SIGN_IN_LINK if we
    managed to send them a sign-in link instead, else NOT_SENT. Neither is
    an error — access is granted by the `user_invites` row.
    On stub mode (no service-role key): logs and returns INVITED.
    On upstream failure: raises SupabaseInviteError.
    """
    s = get_settings()
    if not s.supabase_secret_key or not s.supabase_url:
        log.warning(
            "supabase.invite_stub_mode",
            email=email,
            reason="SUPABASE_SECRET_KEY or SUPABASE_URL empty",
        )
        return InviteOutcome.INVITED

    base = s.supabase_url.rstrip("/")
    key = s.supabase_secret_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{base}/auth/v1/invite",
                headers=_headers(key),
                json={"email": email},
            )

            if _is_email_exists(res):
                log.info("supabase.invite_account_exists", email=email)
                sent = await _send_sign_in_link(
                    client, base=base, key=key, email=email
                )
                return InviteOutcome.SIGN_IN_LINK if sent else InviteOutcome.NOT_SENT
    except httpx.HTTPError as exc:
        log.warning(
            "supabase.invite_network_error",
            email=email,
            error=str(exc)[:200],
        )
        raise SupabaseInviteError(f"Network error: {exc}") from exc

    if res.status_code >= 400:
        # Supabase typically returns {"msg": "..."} or similar.
        body = res.text[:500]
        log.warning(
            "supabase.invite_http_error",
            email=email,
            status=res.status_code,
            body=body,
        )
        raise SupabaseInviteError(
            f"Supabase {res.status_code}: {body}"
        )

    log.info("supabase.invite_sent", email=email)
    return InviteOutcome.INVITED
