"""Auth + rate limiting for the external OS read surface.

A single machine key (Authorization: Bearer drinkx_os_...) is resolved
to a workspace-scoped ServiceContext. No Supabase JWT here.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.external import keys
from app.external.models import ServiceApiKey

log = structlog.get_logger()

_RATE_LIMIT_RPS = 10
_rate_state: dict[uuid.UUID, tuple[float, float]] = {}  # key_id -> (tokens, last_ts)

# Lazy module-level Redis client for the cross-replica rate limiter (plan 024).
# Reuses the same connection style as app.enrichment.sources.cache.
_rl_redis = None


def _get_rl_redis():
    global _rl_redis
    if _rl_redis is None:
        import redis.asyncio as redis_asyncio

        _rl_redis = redis_asyncio.from_url(
            get_settings().redis_url, decode_responses=True
        )
    return _rl_redis


@dataclass(frozen=True)
class ServiceContext:
    workspace_id: uuid.UUID
    key_id: uuid.UUID
    scopes: list[str]


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _check_rate_limit_inmem(key_id: uuid.UUID) -> None:
    """In-memory token bucket, 10 rps per key. Per-process fallback used only
    when Redis is unavailable (plan 024)."""
    now = time.monotonic()
    tokens, last = _rate_state.get(key_id, (float(_RATE_LIMIT_RPS), now))
    tokens = min(_RATE_LIMIT_RPS, tokens + (now - last) * _RATE_LIMIT_RPS)
    if tokens < 1.0:
        _rate_state[key_id] = (tokens, now)
        log.info("external.auth.rate_limited", key_id=str(key_id))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
    _rate_state[key_id] = (tokens - 1.0, now)


async def _check_rate_limit(key_id: uuid.UUID) -> None:
    """Redis fixed-window limiter, 10 rps per key, shared across replicas
    (plan 024). On any Redis error, degrade to the in-memory bucket rather
    than removing the limit entirely."""
    window = int(time.time())
    rkey = f"ext_rl:{key_id}:{window}"
    try:
        client = _get_rl_redis()
        count = int(await client.incr(rkey))
        if count == 1:
            await client.expire(rkey, 2)
    except Exception as exc:  # noqa: BLE001 — Redis outage → in-memory fallback
        log.warning(
            "external.auth.rate_limit_redis_error",
            key_id=str(key_id),
            error=str(exc)[:200],
        )
        _check_rate_limit_inmem(key_id)
        return
    if count > _RATE_LIMIT_RPS:
        log.info("external.auth.rate_limited", key_id=str(key_id))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
        )


async def resolve_service_key(
    session: AsyncSession, token: str | None, *, scope: str
) -> ServiceContext:
    if not token:
        log.warning("external.auth.missing_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing key")
    row = (
        await session.execute(
            select(ServiceApiKey).where(ServiceApiKey.key_hash == keys.hash_key(token))
        )
    ).scalar_one_or_none()
    if row is None:
        log.warning("external.auth.invalid_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid key")
    if row.revoked_at is not None:
        log.warning("external.auth.revoked_key", key_id=str(row.id), workspace_id=str(row.workspace_id))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="key revoked")
    if scope not in row.scopes:
        log.warning("external.auth.missing_scope", key_id=str(row.id), scope=scope)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"scope {scope} required")
    await _check_rate_limit(row.id)
    row.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    log.info("external.auth.ok", key_id=str(row.id), workspace_id=str(row.workspace_id))
    return ServiceContext(workspace_id=row.workspace_id, key_id=row.id, scopes=list(row.scopes))


def require_service_key(scope: str = "read:core"):
    async def _dep(
        authorization: Annotated[str | None, Header()] = None,
        session: Annotated[AsyncSession, Depends(get_db)] = None,
    ) -> ServiceContext:
        return await resolve_service_key(session, _extract_bearer(authorization), scope=scope)

    return _dep
