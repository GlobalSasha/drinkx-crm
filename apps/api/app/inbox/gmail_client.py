"""Gmail API wrapper.

Thin async-friendly facade over google-api-python-client. The underlying
library is sync, so we run blocking calls in a thread pool. All public
methods are fail-soft: they catch transport / API errors, log them, and
return an empty list (or None for single-message lookups).

Token storage: callers pass the *stored* credentials string from
ChannelConnection.credentials_json — which may be either plaintext JSON
(stub mode / Sprint 2.0 legacy) or a `fernet:` encrypted payload (after
Sprint 2.1 G1). The constructor calls
`app.inbox.crypto.decrypt_credentials` to recover plaintext before
parsing. On successful token refresh `refreshed_credentials_json()`
returns the value to persist — already re-encrypted in encrypted mode.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = structlog.get_logger()


def credentials_from_json(creds_json: str) -> Credentials:
    """Build a google-auth Credentials object from the stored JSON blob."""
    data = json.loads(creds_json)
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
        expiry=_parse_expiry(data.get("expiry")),
    )


def credentials_to_json(creds: Credentials) -> str:
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else None,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    return json.dumps(payload)


def _parse_expiry(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        # google-auth stores expiry as naive UTC; round-trip through ISO.
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


class GmailClient:
    """Sync google-api-python-client wrapped in asyncio.to_thread()."""

    def __init__(self, credentials_json: str):
        # Lazy import: keeps `crypto` module out of the import graph for
        # tests that stub sqlalchemy and don't need crypto round-trips.
        from app.inbox.crypto import decrypt_credentials

        plaintext = decrypt_credentials(credentials_json)
        self._creds = credentials_from_json(plaintext)
        self._service = None  # built lazily

    def _ensure_fresh(self) -> None:
        """Refresh access token if expired. Caller persists rotated JSON."""
        if self._creds.expired and self._creds.refresh_token:
            try:
                self._creds.refresh(Request())
            except Exception as exc:
                log.warning("gmail.refresh_failed", error=str(exc)[:200])

    def _client(self):
        if self._service is None:
            self._ensure_fresh()
            self._service = build(
                "gmail",
                "v1",
                credentials=self._creds,
                cache_discovery=False,
            )
        return self._service

    def refreshed_credentials_json(self) -> str:
        """Value to persist back to channel_connections.credentials_json
        after any token refresh — already re-encrypted in encrypted mode."""
        from app.inbox.crypto import encrypt_credentials

        plaintext = credentials_to_json(self._creds)
        return encrypt_credentials(plaintext)

    async def list_messages(
        self,
        *,
        query: str | None = None,
        max_results: int = 500,
    ) -> list[dict[str, Any]]:
        """Return a list of {id, threadId} dicts. Auto-paginates up to max_results."""

        def _do() -> list[dict[str, Any]]:
            try:
                svc = self._client()
                collected: list[dict[str, Any]] = []
                page_token: str | None = None
                remaining = max_results
                while remaining > 0:
                    resp = (
                        svc.users()
                        .messages()
                        .list(
                            userId="me",
                            q=query or "",
                            maxResults=min(remaining, 500),
                            pageToken=page_token,
                        )
                        .execute()
                    )
                    msgs = resp.get("messages") or []
                    collected.extend(msgs)
                    page_token = resp.get("nextPageToken")
                    remaining = max_results - len(collected)
                    if not page_token:
                        break
                return collected[:max_results]
            except HttpError as exc:
                log.warning("gmail.list_messages.http_error", status=exc.status_code)
                return []
            except Exception as exc:
                log.exception("gmail.list_messages.failed", error=str(exc)[:200])
                return []

        return await asyncio.to_thread(_do)

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Fetch one full message (headers + body). Returns None on failure."""

        def _do() -> dict[str, Any] | None:
            try:
                svc = self._client()
                return (
                    svc.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )
            except HttpError as exc:
                log.warning(
                    "gmail.get_message.http_error",
                    message_id=message_id,
                    status=exc.status_code,
                )
                return None
            except Exception as exc:
                log.exception(
                    "gmail.get_message.failed",
                    message_id=message_id,
                    error=str(exc)[:200],
                )
                return None

        return await asyncio.to_thread(_do)

    async def get_history(
        self,
        *,
        start_history_id: str,
    ) -> list[dict[str, Any]]:
        """Return new history entries since `start_history_id`. Used for the
        5-min incremental tick. Empty list on failure or no changes."""

        def _do() -> list[dict[str, Any]]:
            try:
                svc = self._client()
                entries: list[dict[str, Any]] = []
                page_token: str | None = None
                while True:
                    resp = (
                        svc.users()
                        .history()
                        .list(
                            userId="me",
                            startHistoryId=start_history_id,
                            historyTypes=["messageAdded"],
                            pageToken=page_token,
                        )
                        .execute()
                    )
                    entries.extend(resp.get("history") or [])
                    page_token = resp.get("nextPageToken")
                    if not page_token:
                        break
                return entries
            except HttpError as exc:
                log.warning("gmail.get_history.http_error", status=exc.status_code)
                return []
            except Exception as exc:
                log.exception("gmail.get_history.failed", error=str(exc)[:200])
                return []

        return await asyncio.to_thread(_do)

    async def get_profile(self) -> dict[str, Any] | None:
        """Read profile (emailAddress + historyId). Used to seed the cursor."""

        def _do() -> dict[str, Any] | None:
            try:
                svc = self._client()
                return svc.users().getProfile(userId="me").execute()
            except HttpError as exc:
                log.warning("gmail.get_profile.http_error", status=exc.status_code)
                return None
            except Exception as exc:
                log.exception("gmail.get_profile.failed", error=str(exc)[:200])
                return None

        return await asyncio.to_thread(_do)
