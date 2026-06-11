"""SEC-02 regression: WebFetch must not fetch private/internal URLs (SSRF)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.common import ssrf
from app.enrichment.sources.web_fetch import WebFetch


def test_is_safe_fetch_url_rejects_internal(monkeypatch):
    # Deterministic: pretend every host resolves to a private IP.
    monkeypatch.setattr(ssrf, "is_public_host", lambda host: False)
    assert ssrf.is_safe_fetch_url("http://169.254.169.254/latest/meta-data/") is False
    assert ssrf.is_safe_fetch_url("http://localhost:8000/admin") is False
    # Scheme guard is independent of DNS:
    assert ssrf.is_safe_fetch_url("file:///etc/passwd") is False


@pytest.mark.asyncio
async def test_web_fetch_blocks_internal_url_without_request(monkeypatch):
    # Force the host to look private; assert NO HTTP call is attempted.
    monkeypatch.setattr(
        "app.enrichment.sources.web_fetch.is_safe_fetch_url", lambda url: False
    )
    with respx.mock:
        route = respx.get("http://169.254.169.254/latest/meta-data/").mock(
            return_value=httpx.Response(200, text="SECRET")
        )
        result = await WebFetch().fetch(
            "http://169.254.169.254/latest/meta-data/", use_cache=False
        )
    assert route.called is False, "blocked URL must never be requested"
    assert result.error and "blocked" in result.error
    assert not result.items


@pytest.mark.asyncio
async def test_web_fetch_allows_public_url(monkeypatch):
    monkeypatch.setattr(
        "app.enrichment.sources.web_fetch.is_safe_fetch_url", lambda url: True
    )
    with respx.mock:
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(
                200, text="<title>Hi</title><p>hello world</p>"
            )
        )
        result = await WebFetch().fetch("https://example.com/", use_cache=False)
    # SourceResult.error defaults to "" (empty string), not None — see
    # app/enrichment/sources/base.py. A successful fetch leaves it falsy.
    assert not result.error
    assert result.items, "a public URL should return scraped items"
