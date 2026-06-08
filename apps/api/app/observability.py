"""Sentry init — small isolated module so tests can import it
without pulling FastAPI / SQLAlchemy / Redis through `app.main`.

Sprint 2.7 G1: previously inlined in `app.main:lifespan`; lifted out
so the swallow-site tests can verify the no-op-on-empty-DSN contract
without standing up the entire app.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Any

_LOGGING_CONFIGURED = False


def configure_logging(settings: Any) -> None:
    """Wire structlog + stdlib logging into one pipeline.

    Production (`app_env == production` OR `log_dir` set):
      - render every record (structlog events AND plain stdlib loggers, incl.
        uvicorn) as a single JSON line;
      - emit to stdout (→ `docker compose logs`) AND, if `log_dir` is set, to a
        rotating file `<log_dir>/app.log` (10MB × 5) that `GET /admin/logs`
        reads back.
    Dev: keep the human-readable console renderer, stdout only.

    Idempotent — safe to call from both the API lifespan and the Celery app.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    import structlog

    log_level = getattr(settings, "log_level", "INFO") or "INFO"
    log_dir = getattr(settings, "log_dir", "") or ""
    is_prod = getattr(settings, "app_env", "development") == "production" or bool(log_dir)

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_prod:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # stdlib formatter that runs the SAME renderer over both structlog events
    # and foreign (uvicorn / logging.getLogger) records.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    handlers.append(stream)

    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            # One file per process (api / worker / beat) — they share the same
            # mounted dir, and a single RotatingFileHandler across processes
            # would race on rotation. The endpoint reads app-*.log and tags
            # each line with the service from the filename.
            service = os.getenv("SERVICE_NAME", "api")
            fileh = RotatingFileHandler(
                os.path.join(log_dir, f"app-{service}.log"),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fileh.setFormatter(formatter)
            handlers.append(fileh)
        except OSError:
            # Never let a bad log path take the app down — fall back to stdout.
            pass

    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(log_level)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _LOGGING_CONFIGURED = True


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
