"""Per-IP submit rate limiter — Sprint 2.2 G2.

Redis INCR + EXPIRE pattern, fail-open on any Redis error. The choice
to fail open is deliberate: a Redis hiccup that drops legitimate form
submissions costs us real customer leads, while a Redis hiccup that
admits a few extra spam submissions costs us a few junk Lead rows.
The latter is recoverable — soft-delete + manager review — the former
isn't.

Counter is keyed by `(slug, ip)` so a single bot hitting one form
doesn't spend the budget across other forms in the same workspace.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger()


def _rl_key(slug: str, ip: str) -> str:
    return f"form_rl:{slug}:{ip}"


async def check_rate_limit(
    redis_client,
    *,
    ip: str,
    slug: str,
    limit: int,
    window_seconds: int = 60,
) -> bool:
    """True = request allowed, False = over the limit.

    On Redis transport / connection errors we return True (fail open).
    See module docstring for the trade-off rationale.
    """
    if not ip:
        # No IP → can't rate-limit. Allow + log so operators see the
        # gap if a proxy ever forgets to forward the address.
        log.warning("forms.rate_limit.empty_ip", slug=slug)
        return True

    key = _rl_key(slug, ip)
    try:
        count = await redis_client.incr(key)
        if count == 1:
            # First hit in this window — set the TTL atomically. If a
            # second request lands before this expire fires, the TTL
            # is whatever Redis already had (or no TTL on a brand-new
            # key); we accept that small race window because the next
            # incr in 60s will hit a fresh key anyway.
            await redis_client.expire(key, window_seconds)
        return int(count) <= limit
    except Exception as exc:  # noqa: BLE001 — fail-open envelope
        log.warning(
            "forms.rate_limit.redis_error",
            slug=slug,
            error=str(exc)[:200],
        )
        return True
