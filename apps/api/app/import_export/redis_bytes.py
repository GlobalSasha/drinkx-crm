"""Redis client tuned for binary export blobs.

The enrichment cache uses a `decode_responses=True` client because it
stores JSON strings. Export blobs are raw bytes (XLSX, ZIP, etc.), so
we maintain a separate client without `decode_responses` — otherwise
`set/get` would coerce to str and corrupt the payload.
"""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis_asyncio

from app.config import get_settings


EXPORT_TTL_SECONDS = 60 * 60  # 1h — long enough for a manager to click


def _key(job_id: str) -> str:
    return f"export:{job_id}"


@lru_cache(maxsize=1)
def get_bytes_redis() -> redis_asyncio.Redis:
    """Module-level binary-mode client. `decode_responses=False` so blobs
    survive a round-trip without any unicode coercion."""
    return redis_asyncio.from_url(
        get_settings().redis_url, decode_responses=False
    )


async def store_export_bytes(job_id: str, data: bytes) -> str:
    """Persist the export payload under `export:{job_id}` with TTL.
    Returns the key so the caller can stash it on the ExportJob row."""
    client = get_bytes_redis()
    key = _key(job_id)
    await client.setex(key, EXPORT_TTL_SECONDS, data)
    return key


async def fetch_export_bytes(redis_key: str) -> bytes | None:
    """None when the key has expired or never existed — caller maps
    that to HTTP 410 (Gone)."""
    client = get_bytes_redis()
    raw = await client.get(redis_key)
    if raw is None:
        return None
    if isinstance(raw, str):
        # Defence in depth: in test envs an aioredis stub might still
        # decode to str. Re-encode to bytes so the StreamingResponse
        # producer is happy.
        return raw.encode("utf-8")
    return raw
