"""Credential encryption for ChannelConnection.credentials_json.

Sprint 2.0 carryover (security TODO) → Sprint 2.1 G1.

Modes
-----
- **Encrypted mode** (FERNET_KEY env var set, valid 32-byte urlsafe-b64):
  payload is encrypted with `cryptography.fernet.Fernet` and stored as
  `f"fernet:{token}"` in the existing TEXT column.
- **Stub mode** (FERNET_KEY empty or invalid): payload stored as plaintext
  JSON. A WARNING is logged exactly once at process startup so operators
  see the security debt without spamming logs on every read.

Read path is symmetric: lines that don't start with `fernet:` are returned
as-is (legacy plaintext rows from Sprint 2.0 keep working without a data
migration). Lines that do are decrypted; if FERNET_KEY isn't configured
when we encounter an encrypted line we raise — that's a configuration
error, not data corruption, and silent fallback would leak tokens.

Why not BYTEA + a new column? The existing column is TEXT, fernet tokens
are urlsafe-base64 (text), and a prefix marker makes detection trivial.
Avoiding a schema change keeps the hot-deploy path simple.
"""
from __future__ import annotations

import structlog

from app.config import get_settings

log = structlog.get_logger()

ENCRYPTED_PREFIX = "fernet:"

# State for the once-only stub-mode warning.
_warned_stub = False


class CredentialsCryptoError(Exception):
    """Encrypted payload encountered without a configured FERNET_KEY,
    or the configured key fails to decrypt the stored token."""


def _get_fernet():
    """Build a Fernet instance from the configured key, or None in stub mode."""
    s = get_settings()
    key = (s.fernet_key or "").strip()
    if not key:
        return None
    try:
        # Lazy import — `cryptography` is a heavy dep we don't want to
        # require for unit tests of unrelated modules.
        from cryptography.fernet import Fernet

        return Fernet(key.encode("ascii") if isinstance(key, str) else key)
    except Exception as exc:
        log.error("crypto.fernet_init_failed", error=str(exc)[:200])
        return None


def _maybe_warn_stub_mode() -> None:
    global _warned_stub
    if not _warned_stub:
        _warned_stub = True
        log.warning(
            "crypto.stub_mode",
            message=(
                "FERNET_KEY not configured — channel credentials stored "
                "as plaintext. SECURITY: set FERNET_KEY in production .env."
            ),
        )


def encrypt_credentials(plaintext_json: str) -> str:
    """Return the value to store in `channel_connections.credentials_json`.

    In encrypted mode: prefixed Fernet token.
    In stub mode: the plaintext JSON, unchanged.
    """
    if not isinstance(plaintext_json, str):
        raise TypeError("plaintext_json must be str")
    f = _get_fernet()
    if f is None:
        _maybe_warn_stub_mode()
        return plaintext_json
    token = f.encrypt(plaintext_json.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_credentials(stored: str) -> str:
    """Inverse of `encrypt_credentials`. Legacy plaintext rows pass through."""
    if not isinstance(stored, str):
        raise TypeError("stored must be str")
    if not stored.startswith(ENCRYPTED_PREFIX):
        # Legacy plaintext or stub-mode data — return as-is.
        return stored

    f = _get_fernet()
    if f is None:
        raise CredentialsCryptoError(
            "encrypted credentials encountered but FERNET_KEY is not configured"
        )
    token = stored[len(ENCRYPTED_PREFIX) :]
    try:
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise CredentialsCryptoError(
            f"failed to decrypt credentials: {type(exc).__name__}"
        ) from exc


def is_encrypted(stored: str) -> bool:
    """Probe — used by services to know whether to re-encrypt on update."""
    return isinstance(stored, str) and stored.startswith(ENCRYPTED_PREFIX)
