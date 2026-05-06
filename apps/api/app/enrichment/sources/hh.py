"""HH.ru source — vacancy listings as a growth signal."""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.enrichment.sources.base import SourceResult
from app.enrichment.sources.cache import cache_get, cache_set

log = structlog.get_logger()


class HHRu:
    name = "hh"

    async def fetch(
        self,
        query: str,
        *,
        per_page: int = 20,
        timeout_seconds: float = 10.0,
        use_cache: bool = True,
    ) -> SourceResult:
        if use_cache:
            cached = await cache_get(self.name, query)
            if cached is not None:
                return SourceResult(
                    source=self.name,
                    query=query,
                    items=cached.get("items", []),
                    cached=True,
                    elapsed_ms=0,
                )

        started = time.perf_counter()
        url = "https://api.hh.ru/vacancies"
        params = {"text": query, "per_page": per_page, "host": "hh.ru"}
        headers = {"User-Agent": "drinkx-crm/0.1 (+https://crm.drinkx.tech)"}

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as e:
            return SourceResult(source=self.name, query=query, error=f"timeout: {e}")
        except httpx.HTTPError as e:
            return SourceResult(source=self.name, query=query, error=f"http: {e}")

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not resp.is_success:
            return SourceResult(source=self.name, query=query, error=f"{resp.status_code}", elapsed_ms=elapsed_ms)

        data = resp.json()
        vacancies = data.get("items", []) or []
        items: list[dict[str, Any]] = []
        for v in vacancies[:per_page]:
            items.append({
                "id": v.get("id"),
                "title": v.get("name"),
                "company": (v.get("employer") or {}).get("name", ""),
                "company_id": (v.get("employer") or {}).get("id"),
                "city": (v.get("area") or {}).get("name", ""),
                "url": v.get("alternate_url"),
                "published_at": v.get("published_at"),
                "salary": v.get("salary"),
            })

        result = SourceResult(
            source=self.name,
            query=query,
            items=items,
            elapsed_ms=elapsed_ms,
        )

        if use_cache and items:
            await cache_set(self.name, query, {"items": items})

        log.info("source.hh.ok", query=query, count=len(items), elapsed_ms=elapsed_ms)
        return result
