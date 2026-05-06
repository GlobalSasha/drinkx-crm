"""Brave Search source — web results for a query."""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.config import get_settings
from app.enrichment.sources.base import SourceResult
from app.enrichment.sources.cache import cache_get, cache_set

log = structlog.get_logger()


class BraveSearch:
    name = "brave"

    async def fetch(
        self,
        query: str,
        *,
        count: int = 10,
        country: str = "RU",
        timeout_seconds: float = 15.0,
        use_cache: bool = True,
    ) -> SourceResult:
        if use_cache:
            cached = await cache_get(self.name, query)
            if cached is not None:
                return SourceResult(
                    source=self.name,
                    query=query,
                    items=cached.get("items", []),
                    raw=cached.get("raw"),
                    cached=True,
                    elapsed_ms=0,
                )

        s = get_settings()
        if not s.brave_api_key:
            log.warning("source.brave.no_api_key")
            return SourceResult(source=self.name, query=query, error="BRAVE_API_KEY not set")

        started = time.perf_counter()
        url = "https://api.search.brave.com/res/v1/web/search"
        params = {"q": query, "count": count, "country": country}
        headers = {
            "X-Subscription-Token": s.brave_api_key,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as e:
            log.warning("source.brave.timeout", error=str(e))
            return SourceResult(source=self.name, query=query, error=f"timeout: {e}")
        except httpx.HTTPError as e:
            log.warning("source.brave.http_error", error=str(e))
            return SourceResult(source=self.name, query=query, error=f"http: {e}")

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code == 429:
            return SourceResult(source=self.name, query=query, error="rate limited", elapsed_ms=elapsed_ms)
        if resp.status_code in (401, 403):
            return SourceResult(source=self.name, query=query, error=f"auth: {resp.status_code}", elapsed_ms=elapsed_ms)
        if not resp.is_success:
            return SourceResult(source=self.name, query=query, error=f"{resp.status_code}: {resp.text[:200]}", elapsed_ms=elapsed_ms)

        data = resp.json()
        results = data.get("web", {}).get("results", []) or []
        items: list[dict[str, Any]] = []
        for r in results[:count]:
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age"),
                "language": r.get("language"),
            })

        result = SourceResult(
            source=self.name,
            query=query,
            items=items,
            raw=None,  # don't cache the full Brave response
            cached=False,
            elapsed_ms=elapsed_ms,
        )

        if use_cache and items:
            await cache_set(self.name, query, {"items": items})

        log.info("source.brave.ok", query=query, count=len(items), elapsed_ms=elapsed_ms)
        return result
