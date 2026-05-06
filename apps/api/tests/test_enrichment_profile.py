"""Tests for app/enrichment/profile.py — DrinkX profile loader."""
from __future__ import annotations

import pathlib
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Stub structlog before importing profile
# ---------------------------------------------------------------------------

def _stub_structlog():
    if "structlog" in sys.modules:
        return
    sl = ModuleType("structlog")
    class _Logger:
        def warning(self, *a, **kw): pass
        def info(self, *a, **kw): pass
        def bind(self, **kw): return self
    sl.get_logger = lambda: _Logger()
    sys.modules["structlog"] = sl

_stub_structlog()

from app.enrichment.profile import load_profile, render_profile_for_prompt  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_render_profile_includes_product_and_icp():
    """render_profile_for_prompt returns a non-empty string with key DrinkX info."""
    # Ensure lru_cache is clear so real file is loaded
    load_profile.cache_clear()
    result = render_profile_for_prompt()
    assert result, "Expected non-empty profile string"
    assert "ПРОФИЛЬ DRINKX" in result
    assert "кофе" in result.lower()
    assert "ICP" in result


def test_render_profile_returns_empty_when_yaml_missing(tmp_path: pathlib.Path):
    """render_profile_for_prompt returns '' when YAML file cannot be found."""
    load_profile.cache_clear()
    missing = tmp_path / "nonexistent.yaml"
    with patch("app.enrichment.profile._PROFILE_PATH", missing):
        result = render_profile_for_prompt()
    assert result == ""
    load_profile.cache_clear()


def test_load_profile_is_cached():
    """load_profile returns the same dict object on repeated calls (lru_cache)."""
    load_profile.cache_clear()
    first = load_profile()
    second = load_profile()
    assert first is second  # same object → cached
    load_profile.cache_clear()
