"""Tests for Sprint 1.3.B — data sources (Brave, HH.ru, WebFetch).

All network calls are intercepted via httpx.MockTransport.
Cache calls are monkeypatched — no real Redis.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.enrichment.sources.base import SourceResult
from app.enrichment.sources.brave import BraveSearch
from app.enrichment.sources.cache import _cache_key
from app.enrichment.sources.hh import HHRu
from app.enrichment.sources.web_fetch import WebFetch, _strip_html


# ---------------------------------------------------------------------------
# HTTP mock helpers
# ---------------------------------------------------------------------------

class _MockHandler:
    """httpx transport that returns a fixed response and captures requests."""

    def __init__(self, status: int, body: Any, *, raise_timeout: bool = False) -> None:
        self.status = status
        self._body = json.dumps(body) if isinstance(body, (dict, list)) else body
        self.raise_timeout = raise_timeout
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_timeout:
            raise httpx.TimeoutException("timed out", request=request)
        return httpx.Response(
            self.status,
            content=self._body.encode(),
            headers={"content-type": "application/json"},
        )


def _patch_httpx(monkeypatch, handler: _MockHandler, module) -> None:
    """Replace httpx.AsyncClient in the given source module with one using MockTransport."""
    original_async_client = httpx.AsyncClient

    def _fake_async_client(**kwargs: Any) -> httpx.AsyncClient:
        # Strip follow_redirects / max_redirects for MockTransport compatibility
        kwargs.pop("follow_redirects", None)
        kwargs.pop("max_redirects", None)
        kwargs.pop("timeout", None)
        return original_async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module, "httpx", _make_fake_httpx(_fake_async_client))


def _make_fake_httpx(async_client_factory):
    """Return a module-like object whose AsyncClient uses our factory."""
    class _FakeHttpx:
        TimeoutException = httpx.TimeoutException
        HTTPError = httpx.HTTPError

        @staticmethod
        def AsyncClient(**kwargs):
            return async_client_factory(**kwargs)

    return _FakeHttpx()


def _no_cache(monkeypatch, *modules):
    """Patch cache_get → None, cache_set → no-op in all given source modules."""
    for mod in modules:
        monkeypatch.setattr(mod, "cache_get", AsyncMock(return_value=None))
        monkeypatch.setattr(mod, "cache_set", AsyncMock())


# ---------------------------------------------------------------------------
# Brave Search tests
# ---------------------------------------------------------------------------

def _brave_body(results: list[dict] | None = None) -> dict:
    return {
        "web": {
            "results": results or [
                {"title": "Foo Bar", "url": "https://foo.bar", "description": "Desc", "age": "1d", "language": "ru"},
                {"title": "Baz Qux", "url": "https://baz.qux", "description": "More", "age": None, "language": "en"},
            ]
        }
    }


def _fake_settings_brave(brave_api_key: str = "test-brave-key"):
    from app.config import Settings
    return Settings(_env_file=None, brave_api_key=brave_api_key)


@pytest.mark.asyncio
async def test_brave_calls_endpoint_with_subscription_header(monkeypatch):
    """GET to Brave endpoint must carry X-Subscription-Token header."""
    import app.enrichment.sources.brave as brave_mod

    handler = _MockHandler(200, _brave_body())
    _patch_httpx(monkeypatch, handler, brave_mod)
    _no_cache(monkeypatch, brave_mod)
    monkeypatch.setattr(brave_mod, "get_settings", lambda: _fake_settings_brave())

    result = await BraveSearch().fetch("drinkx bar")

    assert len(handler.requests) == 1
    req = handler.requests[0]
    assert "api.search.brave.com" in str(req.url)
    assert req.headers.get("x-subscription-token") == "test-brave-key"


@pytest.mark.asyncio
async def test_brave_returns_items_from_web_results(monkeypatch):
    import app.enrichment.sources.brave as brave_mod

    handler = _MockHandler(200, _brave_body())
    _patch_httpx(monkeypatch, handler, brave_mod)
    _no_cache(monkeypatch, brave_mod)
    monkeypatch.setattr(brave_mod, "get_settings", lambda: _fake_settings_brave())

    result = await BraveSearch().fetch("bars moscow")

    assert result.source == "brave"
    assert result.error == ""
    assert len(result.items) == 2
    assert result.items[0]["title"] == "Foo Bar"
    assert result.items[0]["url"] == "https://foo.bar"


@pytest.mark.asyncio
async def test_brave_429_returns_error_not_raise(monkeypatch):
    import app.enrichment.sources.brave as brave_mod

    handler = _MockHandler(429, "rate limited")
    _patch_httpx(monkeypatch, handler, brave_mod)
    _no_cache(monkeypatch, brave_mod)
    monkeypatch.setattr(brave_mod, "get_settings", lambda: _fake_settings_brave())

    result = await BraveSearch().fetch("query")

    assert result.error == "rate limited"
    assert result.items == []


@pytest.mark.asyncio
async def test_brave_no_api_key_returns_error(monkeypatch):
    import app.enrichment.sources.brave as brave_mod

    _no_cache(monkeypatch, brave_mod)
    monkeypatch.setattr(brave_mod, "get_settings", lambda: _fake_settings_brave(brave_api_key=""))

    result = await BraveSearch().fetch("query")

    assert "BRAVE_API_KEY" in result.error
    assert result.items == []


@pytest.mark.asyncio
async def test_brave_uses_cache_when_present(monkeypatch):
    """If cache_get returns data, no HTTP call should be made."""
    import app.enrichment.sources.brave as brave_mod

    cached_items = [{"title": "Cached", "url": "https://cached.io", "description": "", "age": None, "language": None}]
    monkeypatch.setattr(brave_mod, "cache_get", AsyncMock(return_value={"items": cached_items}))
    monkeypatch.setattr(brave_mod, "cache_set", AsyncMock())

    # We deliberately do NOT patch httpx — if a real HTTP call is made the test will fail
    # because there's no server. But with proper cache hit, no HTTP happens.
    result = await BraveSearch().fetch("query", use_cache=True)

    assert result.cached is True
    assert result.items == cached_items


@pytest.mark.asyncio
async def test_brave_writes_cache_on_success(monkeypatch):
    """cache_set must be called with the extracted items after a successful fetch."""
    import app.enrichment.sources.brave as brave_mod

    handler = _MockHandler(200, _brave_body())
    _patch_httpx(monkeypatch, handler, brave_mod)
    mock_cache_get = AsyncMock(return_value=None)
    mock_cache_set = AsyncMock()
    monkeypatch.setattr(brave_mod, "cache_get", mock_cache_get)
    monkeypatch.setattr(brave_mod, "cache_set", mock_cache_set)
    monkeypatch.setattr(brave_mod, "get_settings", lambda: _fake_settings_brave())

    await BraveSearch().fetch("query", use_cache=True)

    mock_cache_set.assert_called_once()
    call_args = mock_cache_set.call_args
    assert call_args.args[0] == "brave"
    assert "items" in call_args.args[2]


@pytest.mark.asyncio
async def test_brave_skips_cache_when_use_cache_false(monkeypatch):
    """With use_cache=False, neither cache_get nor cache_set should be called."""
    import app.enrichment.sources.brave as brave_mod

    handler = _MockHandler(200, _brave_body())
    _patch_httpx(monkeypatch, handler, brave_mod)
    mock_cache_get = AsyncMock(return_value=None)
    mock_cache_set = AsyncMock()
    monkeypatch.setattr(brave_mod, "cache_get", mock_cache_get)
    monkeypatch.setattr(brave_mod, "cache_set", mock_cache_set)
    monkeypatch.setattr(brave_mod, "get_settings", lambda: _fake_settings_brave())

    await BraveSearch().fetch("query", use_cache=False)

    mock_cache_get.assert_not_called()
    mock_cache_set.assert_not_called()


# ---------------------------------------------------------------------------
# HH.ru tests
# ---------------------------------------------------------------------------

def _hh_body(items: list[dict] | None = None) -> dict:
    return {
        "items": items or [
            {
                "id": "123",
                "name": "Менеджер продаж",
                "employer": {"name": "ООО Ромашка", "id": "777"},
                "area": {"name": "Москва"},
                "alternate_url": "https://hh.ru/vacancy/123",
                "published_at": "2024-01-15T10:00:00+0300",
                "salary": {"from": 100000, "to": 150000, "currency": "RUR"},
            }
        ],
        "found": 1,
        "pages": 1,
    }


@pytest.mark.asyncio
async def test_hh_calls_public_api_with_user_agent(monkeypatch):
    import app.enrichment.sources.hh as hh_mod

    handler = _MockHandler(200, _hh_body())
    _patch_httpx(monkeypatch, handler, hh_mod)
    _no_cache(monkeypatch, hh_mod)

    await HHRu().fetch("бар ресторан")

    assert len(handler.requests) == 1
    req = handler.requests[0]
    assert "hh.ru/vacancies" in str(req.url)
    assert "drinkx-crm" in req.headers.get("user-agent", "")


@pytest.mark.asyncio
async def test_hh_extracts_employer_and_area(monkeypatch):
    import app.enrichment.sources.hh as hh_mod

    handler = _MockHandler(200, _hh_body())
    _patch_httpx(monkeypatch, handler, hh_mod)
    _no_cache(monkeypatch, hh_mod)

    result = await HHRu().fetch("бар ресторан")

    assert result.source == "hh"
    assert len(result.items) == 1
    item = result.items[0]
    assert item["company"] == "ООО Ромашка"
    assert item["company_id"] == "777"
    assert item["city"] == "Москва"
    assert item["title"] == "Менеджер продаж"


@pytest.mark.asyncio
async def test_hh_handles_empty_items(monkeypatch):
    import app.enrichment.sources.hh as hh_mod

    handler = _MockHandler(200, {"items": [], "found": 0, "pages": 0})
    _patch_httpx(monkeypatch, handler, hh_mod)
    _no_cache(monkeypatch, hh_mod)

    result = await HHRu().fetch("nonexistent company xyz")

    assert result.items == []
    assert result.error == ""


# ---------------------------------------------------------------------------
# WebFetch tests
# ---------------------------------------------------------------------------

_SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Acme Drinks Co</title>
  <script>alert('xss')</script>
  <style>body { color: red; }</style>
</head>
<body>
  <h1>Welcome</h1>
  <p>We sell premium beverages.</p>
</body>
</html>"""


def _web_handler(body: str = _SAMPLE_HTML, status: int = 200) -> _MockHandler:
    h = _MockHandler(status, body)
    # override content-type to html
    original_call = h.__call__

    def call(request):
        resp = original_call(request)
        return httpx.Response(resp.status_code, content=body.encode(), headers={"content-type": "text/html; charset=utf-8"})

    h.__call__ = call
    return h


@pytest.mark.asyncio
async def test_web_fetch_strips_html_to_text(monkeypatch):
    import app.enrichment.sources.web_fetch as wf_mod

    handler = _web_handler()
    _patch_httpx(monkeypatch, handler, wf_mod)
    _no_cache(monkeypatch, wf_mod)

    result = await WebFetch().fetch("https://example.com")

    assert result.error == ""
    assert len(result.items) == 1
    text = result.items[0]["text"]
    assert "<script>" not in text
    assert "<style>" not in text
    assert "<h1>" not in text
    assert "Welcome" in text
    assert "premium beverages" in text


@pytest.mark.asyncio
async def test_web_fetch_extracts_title(monkeypatch):
    import app.enrichment.sources.web_fetch as wf_mod

    handler = _web_handler()
    _patch_httpx(monkeypatch, handler, wf_mod)
    _no_cache(monkeypatch, wf_mod)

    result = await WebFetch().fetch("https://example.com")

    assert result.items[0]["title"] == "Acme Drinks Co"


@pytest.mark.asyncio
async def test_web_fetch_caps_size_at_max_bytes(monkeypatch):
    """Bodies over _MAX_BYTES should be truncated before processing."""
    import app.enrichment.sources.web_fetch as wf_mod

    # Build a body larger than 800KB
    big_body = "<html><body>" + ("x" * 900_000) + "</body></html>"
    handler = _web_handler(body=big_body)
    _patch_httpx(monkeypatch, handler, wf_mod)
    _no_cache(monkeypatch, wf_mod)

    result = await WebFetch().fetch("https://example.com")

    # text is capped at 50_000 chars after strip; just check no error and items present
    assert result.error == ""
    assert len(result.items) == 1
    assert len(result.items[0]["text"]) <= 50_000


@pytest.mark.asyncio
async def test_web_fetch_rejects_non_http_scheme(monkeypatch):
    import app.enrichment.sources.web_fetch as wf_mod

    _no_cache(monkeypatch, wf_mod)

    result = await WebFetch().fetch("ftp://example.com/file.txt")

    assert "non-http scheme" in result.error
    assert result.items == []


@pytest.mark.asyncio
async def test_web_fetch_handles_timeout(monkeypatch):
    """TimeoutException from httpx must be caught and returned as SourceResult(error=...)."""
    import app.enrichment.sources.web_fetch as wf_mod

    handler = _MockHandler(200, "", raise_timeout=True)
    _patch_httpx(monkeypatch, handler, wf_mod)
    _no_cache(monkeypatch, wf_mod)

    result = await WebFetch().fetch("https://slow.example.com")

    assert "timeout" in result.error
    assert result.items == []


# ---------------------------------------------------------------------------
# _strip_html unit test
# ---------------------------------------------------------------------------

def test_strip_html_removes_script_and_style_blocks():
    html = """
    <html>
    <head>
      <script type="text/javascript">var x = 1;</script>
      <style>.foo { color: red; }</style>
    </head>
    <body><p>Hello world</p></body>
    </html>
    """
    result = _strip_html(html)
    assert "var x" not in result
    assert ".foo" not in result
    assert "Hello world" in result


# ---------------------------------------------------------------------------
# Cache key format test
# ---------------------------------------------------------------------------

def test_cache_key_format():
    """Key must be enrich:{source}:{sha1(query)[:16]}."""
    query = "test query"
    expected_hash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
    key = _cache_key("brave", query)
    assert key == f"enrich:brave:{expected_hash}"
    assert len(key.split(":")) == 3
    assert key.startswith("enrich:brave:")
    assert len(key.split(":")[-1]) == 16
