"""Pure-function tests for external API key helpers (no DB)."""
from __future__ import annotations

from app.external import keys


def test_generate_key_prefix_and_hash():
    token, key_hash = keys.generate_key()
    assert token.startswith("drinkx_os_")
    assert len(token) > len("drinkx_os_") + 30  # >=32 random chars
    assert keys.hash_key(token) == key_hash
    assert len(key_hash) == 64  # sha256 hex


def test_verify_constant_time_true_and_false():
    token, key_hash = keys.generate_key()
    assert keys.verify(token, key_hash) is True
    assert keys.verify("drinkx_os_wrong", key_hash) is False


def test_two_keys_differ():
    t1, h1 = keys.generate_key()
    t2, h2 = keys.generate_key()
    assert t1 != t2 and h1 != h2
