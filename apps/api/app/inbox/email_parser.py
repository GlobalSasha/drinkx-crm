"""Pure helpers for parsing Gmail message dicts.

Kept dependency-free (stdlib only) so they can be unit-tested without
spinning up SQLAlchemy or hitting Gmail.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any


_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w\-.]+", re.IGNORECASE)


def parse_email_address(raw: str) -> str:
    """Pull the bare email address out of a 'Name <addr@x.com>' header.

    Returns lowercased address, or empty string on failure. Uses stdlib
    `getaddresses` which is RFC-aware; falls back to a regex if that
    doesn't find anything (e.g. the header is just the address).
    """
    if not raw:
        return ""
    pairs = getaddresses([raw])
    for _, addr in pairs:
        if addr and "@" in addr:
            return addr.strip().lower()
    m = _EMAIL_RE.search(raw)
    return m.group(0).lower() if m else ""


def parse_email_list(raw: str) -> list[str]:
    """Parse a To/Cc-style header into a list of bare addresses (lowercased)."""
    if not raw:
        return []
    pairs = getaddresses([raw])
    out: list[str] = []
    seen: set[str] = set()
    for _, addr in pairs:
        if not addr or "@" not in addr:
            continue
        a = addr.strip().lower()
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def parse_rfc2822(raw: str) -> datetime | None:
    """Parse an RFC-2822 'Date:' header. Returns timezone-aware UTC datetime."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _b64url_decode(data: str) -> bytes:
    """Gmail uses urlsafe base64 without padding."""
    if not data:
        return b""
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad)
    except (ValueError, TypeError):
        return b""


def _walk_parts(payload: dict[str, Any]):
    """Yield every {mimeType, body} dict in a Gmail payload tree."""
    if not isinstance(payload, dict):
        return
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def extract_body(message: dict[str, Any]) -> str:
    """Walk a Gmail message tree and return the best-effort plaintext body.

    Preference order:
      1. text/plain part
      2. text/html part (HTML stripped to bare text)
      3. snippet field on the top-level message
    Returns "" if nothing is recoverable.
    """
    if not isinstance(message, dict):
        return ""
    payload = message.get("payload") or {}

    plain: str | None = None
    html: str | None = None
    for part in _walk_parts(payload):
        mime = part.get("mimeType", "")
        body = part.get("body") or {}
        data = body.get("data")
        if not data:
            continue
        decoded = _b64url_decode(data)
        if not decoded:
            continue
        try:
            text = decoded.decode("utf-8", errors="replace")
        except Exception:
            continue
        if mime == "text/plain" and plain is None:
            plain = text
        elif mime == "text/html" and html is None:
            html = text

    if plain:
        return plain
    if html:
        return _strip_html(html)
    snippet = message.get("snippet") or ""
    return snippet if isinstance(snippet, str) else ""


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Cheap HTML → text. Good enough for previews and prompt context."""
    no_tags = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", no_tags).strip()


def is_sent_message(message: dict[str, Any]) -> bool:
    """True if Gmail tagged this as 'SENT' (i.e. outbound from the user)."""
    label_ids = message.get("labelIds") or []
    return "SENT" in label_ids


def headers_to_dict(message: dict[str, Any]) -> dict[str, str]:
    """Lowercase-keyed view of message.payload.headers."""
    payload = message.get("payload") or {}
    out: dict[str, str] = {}
    for h in payload.get("headers") or []:
        name = (h.get("name") or "").lower()
        value = h.get("value") or ""
        if name and value and name not in out:
            out[name] = value
    return out
