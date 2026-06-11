"""SSRF defense-in-depth: RssFeedSource must not fetch non-public URLs."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.enrichment.sources.rss_feed import RssFeedSource


@pytest.mark.asyncio
async def test_rss_http_get_blocks_internal_url(monkeypatch):
    monkeypatch.setattr(
        "app.enrichment.sources.rss_feed.is_safe_fetch_url", lambda url: False
    )
    with respx.mock:
        route = respx.get("http://169.254.169.254/feed.xml").mock(
            return_value=httpx.Response(200, text="<rss></rss>")
        )
        with pytest.raises(ValueError):
            await RssFeedSource(config={})._http_get("http://169.254.169.254/feed.xml")
    assert route.called is False, "blocked URL must never be requested"


@pytest.mark.asyncio
async def test_rss_http_get_allows_public_url(monkeypatch):
    monkeypatch.setattr(
        "app.enrichment.sources.rss_feed.is_safe_fetch_url", lambda url: True
    )
    with respx.mock:
        respx.get("https://example.com/feed.xml").mock(
            return_value=httpx.Response(200, text="<rss>ok</rss>")
        )
        raw = await RssFeedSource(config={})._http_get("https://example.com/feed.xml")
    assert "ok" in raw
