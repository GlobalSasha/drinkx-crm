"""Sentry init — small isolated module so tests can import it
without pulling FastAPI / SQLAlchemy / Redis through `app.main`.

Sprint 2.7 G1: previously inlined in `app.main:lifespan`; lifted out
so the swallow-site tests can verify the no-op-on-empty-DSN contract
without standing up the entire app.
"""
from __future__ import annotations

from typing import Any


def init_sentry_if_dsn(settings: Any) -> bool:
    """Initialise Sentry SDK only if `settings.sentry_dsn` is set.

    Returns True if init ran, False otherwise. The lazy import means
    `sentry-sdk` only enters the import graph when an operator opts
    in — keeps `python -c 'import app.observability'` cheap.
    """
    dsn = getattr(settings, "sentry_dsn", "") or ""
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=getattr(settings, "app_env", "production"),
        traces_sample_rate=0.1,
    )
    return True
