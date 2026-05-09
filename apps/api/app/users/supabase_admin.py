"""Thin wrapper around the Supabase admin API for user invites
— Sprint 2.4 G1.

We don't pull `supabase-py` (heavy dep + we only need one call).
Instead we hit the admin REST endpoint directly with httpx + the
already-configured `SUPABASE_SECRET_KEY` (service role key).

`POST {SUPABASE_URL}/auth/v1/admin/invite_user_by_email`
  body: { "email": "...", "data": {...} }
  headers: Authorization: Bearer SERVICE_ROLE_KEY, apikey: SERVICE_ROLE_KEY

Stub-mode: when SUPABASE_SECRET_KEY is empty (dev), we log the
invitation instead of calling Supabase. Same pattern as the email
digest's stub-mode (Sprint 1.5).
"""
from __future__ import annotations

import structlog
import httpx

from app.config import get_settings

log = structlog.get_logger()


class SupabaseInviteError(Exception):
    """Raised when the Supabase admin API call fails. Router maps
    to HTTP 502 — the request was structurally correct, but our
    upstream couldn't deliver."""


async def send_invite_email(*, email: str) -> None:
    """Trigger Supabase to send a magic-link invitation email.

    On success: returns None (Supabase 200).
    On stub mode (no service-role key): logs and returns None.
    On upstream failure: raises SupabaseInviteError.
    """
    s = get_settings()
    if not s.supabase_secret_key or not s.supabase_url:
        log.warning(
            "supabase.invite_stub_mode",
            email=email,
            reason="SUPABASE_SECRET_KEY or SUPABASE_URL empty",
        )
        return

    url = f"{s.supabase_url.rstrip('/')}/auth/v1/admin/invite_user_by_email"
    headers = {
        "Authorization": f"Bearer {s.supabase_secret_key}",
        "apikey": s.supabase_secret_key,
        "Content-Type": "application/json",
    }
    payload = {"email": email}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=headers, json=payload)
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
