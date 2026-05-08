"""Settings domain Pydantic schemas — Sprint 2.4 G2.

Read-only views over already-existing config:
  - Gmail OAuth state per current user (from ChannelConnection rows
    written by the Sprint 2.0 OAuth flow).
  - SMTP config from app.config.Settings — surfaced for the admin
    Settings UI without exposing the password.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GmailChannelOut(BaseModel):
    """Gmail connection state for the current user. Drives the
    «Подключить Gmail» / «Подключено» card in /settings → Каналы."""
    # Whether the SUPABASE_URL + GOOGLE_CLIENT_* env vars are
    # configured at all on the server. False → CTA goes through
    # but the API will reject with 503.
    configured: bool
    # Whether the current user has an active ChannelConnection row.
    # If `configured=True` and `connected=False`, the manager just
    # hasn't clicked Подключить yet.
    connected: bool
    # When was the last successful sync (NULL if never).
    last_sync_at: datetime | None = None


class SmtpConfigOut(BaseModel):
    """SMTP server config — read-only in v1. Editing is via env
    vars on the host, not via the UI (Sprint 2.4 NOT-ALLOWED:
    «DB-backed SMTP credentials»). Password is never returned."""
    configured: bool
    host: str
    port: int
    from_address: str
    # `user` is shown as a hint to the operator; password never is.
    user: str


class ChannelsStatusOut(BaseModel):
    gmail: GmailChannelOut
    smtp: SmtpConfigOut
