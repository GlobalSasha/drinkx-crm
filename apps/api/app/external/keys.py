"""Machine API key generation + hashing for external OS access.

Pure functions, no DB. The full token is shown once at creation;
only its sha256 hash is stored (see ServiceApiKey.key_hash).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_PREFIX = "drinkx_os_"


def hash_key(token: str) -> str:
    """sha256 hex of the full token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str]:
    """Return (full_token, key_hash). Store only the hash."""
    token = _PREFIX + secrets.token_urlsafe(32)
    return token, hash_key(token)


def verify(token: str, key_hash: str) -> bool:
    """Constant-time compare of a presented token against a stored hash."""
    return hmac.compare_digest(hash_key(token), key_hash)
