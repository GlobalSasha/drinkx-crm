"""web_fetch — pull a company website's HTML and extract plain text."""
from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import httpx
import structlog

from app.enrichment.sources.base import SourceResult
from app.enrichment.sources.cache import cache_get, cache_set

log = structlog.get_logger()

_MAX_BYTES = 800_000  # 800KB hard cap
_TAG_RX = re.compile(r"<[^>]+>")
_WS_RX = re.compile(r"\s+")
_SCRIPT_STYLE_RX = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def _strip_html(html: str) -> str:
    html = _SCRIPT_STYLE_RX.sub(" ", html)
    text = _TAG_RX.sub(" ", html)
    return _WS_RX.sub(" ", text).strip()


class WebFetch:
    name = "web_fetch"

    async def fetch(
        self,
        url: str,
        *,
        timeout_seconds: float = 15.0,
        use_cache: bool = True,
    ) -> SourceResult:
        # Reject obviously bad inputs early
        try:
            parsed = urlparse(url)
        except ValueError as e:
            return SourceResult(source=self.name, query=url, error=f"bad url: {e}")
        if parsed.scheme not in ("http", "https"):
            return SourceResult(source=self.name, query=url, error="non-http scheme")
        if not parsed.netloc:
            return SourceResult(source=self.name, query=url, error="no host")

        if use_cache:
            cached = await cache_get(self.name, url)
            if cached is not None:
                return SourceResult(
                    source=self.name,
                    query=url,
                    items=cached.get("items", []),
                    cached=True,
                    elapsed_ms=0,
                )

        started = time.perf_counter()
        headers = {
            "User-Agent": "drinkx-crm/0.1 (+https://crm.drinkx.tech) Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, max_redirects=3) as client:
                resp = await client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            return SourceResult(source=self.name, query=url, error=f"timeout: {e}")
        except httpx.HTTPError as e:
            return SourceResult(source=self.name, query=url, error=f"http: {e}")

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not resp.is_success:
            return SourceResult(source=self.name, query=url, error=f"{resp.status_code}", elapsed_ms=elapsed_ms)

        body = resp.text
        if len(body) > _MAX_BYTES:
            body = body[:_MAX_BYTES]

        text = _strip_html(body)
        # Trim further so a downstream LLM doesn't choke
        text = text[:50_000]

        title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else ""

        items = [{
            "url": str(resp.url),  # final URL after redirects
            "title": title[:300],
            "text": text,
            "status": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
        }]

        result = SourceResult(
            source=self.name,
            query=url,
            items=items,
            elapsed_ms=elapsed_ms,
        )

        if use_cache:
            await cache_set(self.name, url, {"items": items})

        log.info("source.web_fetch.ok", url=url, bytes=len(body), elapsed_ms=elapsed_ms)
        return result
