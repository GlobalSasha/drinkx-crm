"""Tiny async Redis cache for source results."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

import redis.asyncio as redis_asyncio
import structlog

from app.config import get_settings

log = structlog.get_logger()

_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h, per ARCHITECTURE.md
_CACHE_PREFIX = "enrich"


@lru_cache(maxsize=1)
def get_redis() -> redis_asyncio.Redis:
    """Module-level Redis client. Reused across requests."""
    return redis_asyncio.from_url(get_settings().redis_url, decode_responses=True)


def _cache_key(source: str, query: str) -> str:
    h = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
    return f"{_CACHE_PREFIX}:{source}:{h}"


async def cache_get(source: str, query: str) -> dict[str, Any] | None:
    try:
        client = get_redis()
        raw = await client.get(_cache_key(source, query))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        # Cache miss > cache outage; never let cache failures break the request
        log.warning("cache.get_failed", source=source, error=str(e))
        return None


async def cache_set(source: str, query: str, value: dict[str, Any]) -> None:
    try:
        client = get_redis()
        await client.setex(
            _cache_key(source, query),
            _CACHE_TTL_SECONDS,
            json.dumps(value, ensure_ascii=False),
        )
    except Exception as e:
        log.warning("cache.set_failed", source=source, error=str(e))
