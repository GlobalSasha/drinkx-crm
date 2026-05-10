"""Single capture point used by every swallow site.

`sentry_sdk.capture_exception` is a no-op when `sentry_sdk.init()` was
never called (empty DSN at startup — see `app/main.py:lifespan`). We
still wrap it here so:

1. Tests have one symbol to monkeypatch when asserting that a swallow
   site reports its failure.
2. If `sentry-sdk` import ever fails (e.g. local dev without the
   optional dep), every call site stays a soft no-op instead of
   crashing the swallow path.
3. We can attach uniform `fingerprint` + `tags` per call site so
   operators can mute noisy ones without losing visibility on others.
"""
from __future__ import annotations

from typing import Any

import structlog

_log = structlog.get_logger()


def capture(
    exc: BaseException,
    *,
    fingerprint: list[str] | None = None,
    tags: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Report `exc` to Sentry. Soft no-op on any failure.

    `fingerprint` groups related errors (e.g. all daily-plan-cron
    user-failures roll into one issue regardless of which user).
    `tags` are searchable; `extra` is free-form context.
    """
    try:
        import sentry_sdk
    except Exception:
        return

    try:
        with sentry_sdk.push_scope() as scope:
            if fingerprint:
                scope.fingerprint = fingerprint
            if tags:
                for k, v in tags.items():
                    scope.set_tag(k, v)
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception as send_err:  # pragma: no cover — defensive
        _log.warning("sentry.capture_failed", error=str(send_err)[:200])
