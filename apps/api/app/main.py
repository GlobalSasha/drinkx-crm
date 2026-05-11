"""FastAPI app factory."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings


class PublicFormsCORSMiddleware(BaseHTTPMiddleware):
    """Wildcard-CORS for `/api/public/*` (Sprint 2.2 WebForms).

    The global CORSMiddleware below is restricted to `cors_origins` so
    /api/leads etc. don't accidentally accept calls from arbitrary
    domains. Public form submissions, by design, must accept any origin
    — that's the whole point of an embeddable form. This middleware
    runs ahead of the global one and short-circuits OPTIONS preflight
    + adds permissive CORS headers on the response, ONLY for paths
    starting with `/api/public/`.

    Bearer-Authorization isn't a CORS credential per spec, so wildcard
    origin + no credentials is the right shape here. Cookies are not
    used for these endpoints.
    """

    async def dispatch(self, request: Request, call_next):
        is_public = request.url.path.startswith("/api/public/")
        if is_public and request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Max-Age": "86400",
                },
            )
        response = await call_next(request)
        if is_public:
            response.headers["Access-Control-Allow-Origin"] = "*"
        return response

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    log.info("api.startup", env=s.app_env)
    # Sentry init (only if DSN set) — keep cheap on startup
    from app.observability import init_sentry_if_dsn
    init_sentry_if_dsn(s)
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
    # Added LAST so it runs FIRST in the middleware stack (Starlette
    # executes outermost-to-innermost on request, innermost-to-outermost
    # on response). This lets us short-circuit /api/public/* preflight
    # before the restrictive global CORSMiddleware sees it.
    app.add_middleware(PublicFormsCORSMiddleware)

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

    from app.followups.routers import (
        me_router as followups_me_router,
        router as followups_router,
    )
    app.include_router(followups_router)
    app.include_router(followups_me_router)

    from app.pipelines.routers import router as pipelines_router
    app.include_router(pipelines_router)

    from app.enrichment.routers import router as enrichment_router
    app.include_router(enrichment_router)

    from app.daily_plan.routers import router as daily_plan_router
    app.include_router(daily_plan_router)

    from app.notifications.routers import router as notifications_router
    app.include_router(notifications_router)

    from app.audit.routers import router as audit_router
    app.include_router(audit_router)

    from app.inbox.routers import router as inbox_router
    app.include_router(inbox_router)

    from app.import_export.routers import (
        export_router as import_export_export_router,
        router as import_export_router,
    )
    app.include_router(import_export_router)
    app.include_router(import_export_export_router)

    from app.forms.routers import router as forms_router
    app.include_router(forms_router)

    from app.forms.public_routers import public_router as forms_public_router
    app.include_router(forms_public_router)

    from app.users.routers import router as users_router
    app.include_router(users_router)

    from app.settings.routers import router as settings_router
    app.include_router(settings_router)

    from app.custom_attributes.routers import router as custom_attributes_router
    app.include_router(custom_attributes_router)

    from app.template.routers import router as templates_router
    app.include_router(templates_router)

    from app.automation_builder.routers import router as automations_router
    app.include_router(automations_router)

    from app.lead_agent.routers import router as lead_agent_router
    app.include_router(lead_agent_router)

    from app.companies.routers import router as companies_router
    app.include_router(companies_router)

    from app.search.routers import router as search_router
    app.include_router(search_router)

    return app


app = create_app()
