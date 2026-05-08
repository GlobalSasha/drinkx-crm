"""Tests for app.inbox.crypto — Sprint 2.1 G1.

Two modes:
- encrypted (FERNET_KEY set, valid 32-byte urlsafe-b64 key) → round-trip
- stub (FERNET_KEY empty / invalid) → plaintext passthrough + warning

Skips quietly when `cryptography` isn't pip-installed in the dev env.
"""
from __future__ import annotations

import importlib

import pytest

cryptography = pytest.importorskip("cryptography.fernet")
Fernet = cryptography.Fernet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_crypto():
    """Settings are cached via @lru_cache so we have to clear + re-import
    after monkeypatching env between cases."""
    from app.config import get_settings

    get_settings.cache_clear()
    import app.inbox.crypto as crypto_mod  # noqa: WPS433

    importlib.reload(crypto_mod)
    return crypto_mod


# ---------------------------------------------------------------------------
# Encrypted mode
# ---------------------------------------------------------------------------

def test_encrypted_mode_round_trip(monkeypatch):
    """encrypt → decrypt yields the original payload byte-for-byte; output
    carries the `fernet:` prefix marker."""
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("FERNET_KEY", key)
    crypto = _reload_crypto()

    plaintext = '{"refresh_token": "abc.def-123_XYZ", "scopes": ["x"]}'
    stored = crypto.encrypt_credentials(plaintext)
    assert stored.startswith(crypto.ENCRYPTED_PREFIX)
    assert plaintext not in stored  # actually encrypted

    recovered = crypto.decrypt_credentials(stored)
    assert recovered == plaintext
    assert crypto.is_encrypted(stored) is True


def test_encrypted_mode_rejects_tampered_token(monkeypatch):
    """A flipped-byte token must raise — silent failure would leak.

    We swap a single character mid-token to keep the prefix + base64 shape
    intact; that forces decrypt past the prefix-strip and into Fernet's
    integrity check, which is what we want to verify."""
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("FERNET_KEY", key)
    crypto = _reload_crypto()

    stored = crypto.encrypt_credentials("payload")
    body = stored[len(crypto.ENCRYPTED_PREFIX):]
    # Flip one char somewhere in the middle so length stays valid
    mid = len(body) // 2
    swap = "B" if body[mid] != "B" else "C"
    tampered = crypto.ENCRYPTED_PREFIX + body[:mid] + swap + body[mid + 1:]

    with pytest.raises(crypto.CredentialsCryptoError):
        crypto.decrypt_credentials(tampered)


def test_encrypted_mode_legacy_plaintext_passes_through(monkeypatch):
    """Sprint 2.0 wrote plaintext rows. Those must keep working after we
    flip on FERNET_KEY — `decrypt_credentials` returns them as-is."""
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("FERNET_KEY", key)
    crypto = _reload_crypto()

    legacy = '{"refresh_token": "legacy"}'
    assert crypto.is_encrypted(legacy) is False
    assert crypto.decrypt_credentials(legacy) == legacy


# ---------------------------------------------------------------------------
# Stub mode
# ---------------------------------------------------------------------------

def test_stub_mode_passes_plaintext_through(monkeypatch):
    """Empty FERNET_KEY → encrypt is identity, decrypt is identity."""
    monkeypatch.setenv("FERNET_KEY", "")
    crypto = _reload_crypto()

    plaintext = '{"refresh_token": "stub"}'
    stored = crypto.encrypt_credentials(plaintext)
    assert stored == plaintext
    assert crypto.is_encrypted(stored) is False
    assert crypto.decrypt_credentials(stored) == plaintext


def test_stub_mode_refuses_to_decrypt_encrypted_input(monkeypatch):
    """If a row arrives with the encrypted prefix but FERNET_KEY isn't
    set (config drift / lost key), we MUST raise — silent fallback would
    leak token bytes via downstream JSON parser errors or worse."""
    monkeypatch.setenv("FERNET_KEY", "")
    crypto = _reload_crypto()

    poisoned = crypto.ENCRYPTED_PREFIX + "gAAAAAFakeTokenBody=="
    with pytest.raises(crypto.CredentialsCryptoError):
        crypto.decrypt_credentials(poisoned)


def test_invalid_fernet_key_falls_to_stub_mode(monkeypatch):
    """Garbage key value → Fernet construction fails → stub-mode behaviour."""
    monkeypatch.setenv("FERNET_KEY", "this-is-not-a-valid-fernet-key")
    crypto = _reload_crypto()

    # encrypt_credentials returns plaintext (stub mode) instead of crashing.
    plaintext = '{"x": 1}'
    assert crypto.encrypt_credentials(plaintext) == plaintext
