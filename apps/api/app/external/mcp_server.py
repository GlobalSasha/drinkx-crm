"""Remote MCP server for external OS read access.

Mounts at ``/mcp`` (streamable HTTP transport). Auth: the same Bearer
machine key as the REST surface, resolved *per call* — every tool resolves a
valid ``read:core`` key to a workspace via ``resolve_service_key`` BEFORE
returning any CRM data. All tools are read-only.

SDK: ``mcp`` 1.28.1. The installed ``FastMCP`` exposes:
  * ``@server.tool()`` decorator to register tools,
  * ``await server.list_tools()`` (async) returning ``MCPTool`` objects with
    ``.name`` — used by the registration test,
  * ``server.streamable_http_app()`` returning a Starlette ASGI app to mount,
  * ``server.get_context()`` yielding a ``Context`` whose
    ``.request_context.request`` is the incoming Starlette ``Request`` (the
    streamable-HTTP transport populates it from the ASGI scope). This is the
    clean per-tool header accessor, so we use it directly — the machine key is
    read from ``Authorization`` inside each tool and resolved to a workspace.
    No ASGI middleware fallback was needed.
"""
from __future__ import annotations

import uuid

from mcp.server.fastmcp import FastMCP

from app.db import get_session_factory  # returns an async_sessionmaker
from app.external import services as svc
from app.external.dependencies import _extract_bearer, resolve_service_key

server = FastMCP("drinkx-crm")


def _authorization_header() -> str | None:
    """Read the incoming HTTP Authorization header from the active request."""
    request = server.get_context().request_context.request
    if request is None:  # pragma: no cover - defensive; always set over HTTP
        return None
    return request.headers.get("authorization")


async def _resolve_workspace() -> uuid.UUID:
    """Resolve the Bearer machine key (read:core) to a workspace id."""
    token = _extract_bearer(_authorization_header())
    async with get_session_factory()() as s:
        ctx = await resolve_service_key(s, token, scope="read:core")
    return ctx.workspace_id


@server.tool()
async def search_leads(
    q: str | None = None,
    pipeline_id: str | None = None,
    stage_id: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search leads by company name / pipeline / stage. Read-only."""
    workspace_id = await _resolve_workspace()
    async with get_session_factory()() as s:
        page = await svc.list_leads(
            s, workspace_id, q=q,
            pipeline_id=uuid.UUID(pipeline_id) if pipeline_id else None,
            stage_id=uuid.UUID(stage_id) if stage_id else None,
            limit=limit,
        )
    return [item.model_dump(exclude_none=True, mode="json") for item in page.items]


@server.tool()
async def get_lead_summary(lead_id: str) -> dict | None:
    """Full picture of one lead (company, contacts, stage, rot flags). Read-only."""
    workspace_id = await _resolve_workspace()
    async with get_session_factory()() as s:
        out = await svc.lead_summary(s, workspace_id, uuid.UUID(lead_id))
    return out.model_dump(exclude_none=True, mode="json") if out else None


@server.tool()
async def pipeline_overview(pipeline_id: str) -> dict | None:
    """Per-stage counts and deal amounts for a pipeline. Read-only."""
    workspace_id = await _resolve_workspace()
    async with get_session_factory()() as s:
        out = await svc.pipeline_summary(s, workspace_id, uuid.UUID(pipeline_id))
    return out.model_dump(exclude_none=True, mode="json") if out else None


@server.tool()
async def list_pipelines() -> list[dict]:
    """List pipelines with their stages. Read-only."""
    workspace_id = await _resolve_workspace()
    async with get_session_factory()() as s:
        pls = await svc.list_pipelines(s, workspace_id)
    return [p.model_dump(exclude_none=True, mode="json") for p in pls]


def build_mcp_app():
    """ASGI (Starlette) app for mounting at ``/mcp`` (streamable HTTP)."""
    return server.streamable_http_app()
