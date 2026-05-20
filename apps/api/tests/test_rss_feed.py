"""Sprint 3.9 G1 — RSS feed source."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _rss_xml(items: list[tuple[str, str, str]]) -> str:
    """items = list of (title, link, pubdate_rfc822)."""
    entries = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<description>desc {t}</description><pubDate>{d}</pubDate></item>"
        for (t, l, d) in items
    )
    return f"<rss><channel>{entries}</channel></rss>"


@pytest.mark.asyncio
async def test_fetch_filters_items_older_than_365_days():
    from app.enrichment.sources.rss_feed import RssFeedSource

    fresh = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    old = (datetime.now(timezone.utc) - timedelta(days=500)).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    xml = _rss_xml([("Fresh news", "https://x/1", fresh),
                    ("Old news", "https://x/2", old)])

    src = RssFeedSource(config={"retail": {"rss": [{"url": "u", "name": "n"}]}})
    with patch.object(src, "_http_get", new=AsyncMock(return_value=xml)):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("retail")

    titles = [i.title for i in items]
    assert "Fresh news" in titles
    assert "Old news" not in titles


@pytest.mark.asyncio
async def test_dead_feed_is_skipped_not_fatal():
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={
        "retail": {"rss": [
            {"url": "dead", "name": "dead"},
            {"url": "live", "name": "live"},
        ]}
    })
    fresh = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    live_xml = _rss_xml([("Live item", "https://x/1", fresh)])

    async def _get(url):
        if url == "dead":
            raise RuntimeError("boom")
        return live_xml

    with patch.object(src, "_http_get", new=_get):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("retail")

    assert [i.title for i in items] == ["Live item"]


@pytest.mark.asyncio
async def test_unknown_segment_returns_empty():
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={"retail": {"rss": []}})
    items = await src.fetch_segment_news("nonexistent-segment")
    assert items == []


@pytest.mark.asyncio
async def test_inherit_resolves_parent_feeds():
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={
        "retail": {"rss": [{"url": "r", "name": "retail"}]},
        "qsr": {"inherit": ["retail"]},
    })
    fresh = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = _rss_xml([("Retail item", "https://x/1", fresh)])

    with patch.object(src, "_http_get", new=AsyncMock(return_value=xml)):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("qsr")

    assert [i.title for i in items] == ["Retail item"]


@pytest.mark.asyncio
async def test_company_name_no_match_falls_back_to_all_items():
    """company_name given but no item matches → return all segment items
    (don't return empty)."""
    from app.enrichment.sources.rss_feed import RssFeedSource

    src = RssFeedSource(config={"retail": {"rss": [{"url": "u", "name": "n"}]}})
    fresh = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = (
        "<rss><channel>"
        f"<item><title>Generic retail news</title><link>https://x/1</link>"
        f"<description>nothing relevant</description><pubDate>{fresh}</pubDate></item>"
        "</channel></rss>"
    )
    with patch.object(src, "_http_get", new=AsyncMock(return_value=xml)):
        with patch.object(src, "_cache_get", new=AsyncMock(return_value=None)):
            with patch.object(src, "_cache_set", new=AsyncMock()):
                items = await src.fetch_segment_news("retail", company_name="Acme Corp")

    # No title/summary contains "acme corp" → fallback returns all items
    assert [i.title for i in items] == ["Generic retail news"]
