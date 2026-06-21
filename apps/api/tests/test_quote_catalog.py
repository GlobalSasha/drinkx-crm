"""Quote catalog tests — Phase 1. Pure (no DB) service-level checks."""
from __future__ import annotations

import pytest


def test_validate_category_rejects_unknown():
    from app.quote.services import _validate_category

    with pytest.raises(ValueError, match="Invalid category"):
        _validate_category("bogus")


def test_validate_category_accepts_known_and_none():
    from app.quote.services import _validate_category

    # None = a PATCH that omits category; known values pass.
    _validate_category(None)
    _validate_category("station")
    _validate_category("option")


def test_starter_catalog_is_deterministic_and_valid():
    from app.quote.models import PRODUCT_CATEGORIES
    from app.quote.services import STARTER_CATALOG

    assert len(STARTER_CATALOG) == 5
    assert all(item["category"] in PRODUCT_CATEGORIES for item in STARTER_CATALOG)
    names = [i["name"] for i in STARTER_CATALOG]
    assert len(names) == len(set(names)), "no duplicate seed names"
