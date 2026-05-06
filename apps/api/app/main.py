"""FastAPI app factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    log.info("api.startup", env=s.app_env)
    # Sentry init (only if DSN set) — keep cheap on startup
    if s.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.app_env, traces_sample_rate=0.1)
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="DrinkX CRM API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version", tags=["meta"])
    async def version() -> dict[str, str]:
        return {"version": "0.1.0", "env": s.app_env}

    # Domain routers — see AUTOPILOT.md
    from app.auth.routers import router as auth_router
    app.include_router(auth_router)

    from app.leads.routers import router as leads_router
    app.include_router(leads_router)

    from app.contacts.routers import router as contacts_router
    app.include_router(contacts_router)

    from app.activity.routers import router as activity_router
    app.include_router(activity_router)

    from app.followups.routers import router as followups_router
    app.include_router(followups_router)

    from app.pipelines.routers import router as pipelines_router
    app.include_router(pipelines_router)

    from app.enrichment.routers import router as enrichment_router
    app.include_router(enrichment_router)

    return app


app = create_app()
