"""Sprint 3.9 G2 — lightweight enrichment mode helpers."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _C:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _C()
    _sa_orm.defer = _C()


def test_format_rss_block_empty_and_populated():
    from app.enrichment.orchestrator import _format_rss_block
    from app.enrichment.sources.rss_feed import FeedItem

    assert "нет свежих" in _format_rss_block([])

    item = FeedItem(
        title="Сеть открыла 5 точек",
        summary="...",
        url="https://x/1",
        published=datetime(2026, 5, 1, tzinfo=timezone.utc),
        source_name="retail.ru",
    )
    block = _format_rss_block([item])
    assert "Сеть открыла 5 точек" in block
    assert "2026-05-01" in block
    assert "retail.ru" in block
