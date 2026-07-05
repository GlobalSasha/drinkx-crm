"""MCP server exposes exactly the 4 read-only tools.

Two levels of coverage:

1. ``test_four_tools_registered`` — structure-level: FastMCP.list_tools() is an
   async accessor in mcp 1.28.1 that returns MCPTool objects with a `.name`.

2. ``test_mcp_transport_*`` — transport-level: drives a real MCP streamable-HTTP
   session against the mounted ``/mcp`` path using an in-process ASGI transport
   (httpx ``ASGITransport`` feeding the SDK's ``streamable_http_client``). These
   would fail if the session-manager lifespan never ran (the first request would
   raise ``RuntimeError("Task group is not initialized")``) or if the mounted
   path were wrong (``/mcp/mcp`` → 404). They need NO Postgres: the handshake and
   ``tools/list`` are pure MCP protocol, and the no-auth tool call hits
   ``resolve_service_key`` which raises 401 on a missing token BEFORE any DB
   query.
"""
from __future__ import annotations

import contextlib

import httpx
import pytest

from app.external.mcp_server import server  # the FastMCP instance
from app.main import create_app

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.asyncio
async def test_four_tools_registered():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"search_leads", "get_lead_summary", "pipeline_overview", "list_pipelines"}


# ---------------------------------------------------------------------------
# Transport-level driver
# ---------------------------------------------------------------------------
# The FastMCP `server` is a module singleton and its StreamableHTTPSessionManager
# can only `run()` once per instance (the SDK forbids re-entry). Each test needs
# to enter AND exit the lifespan within its own task (anyio task groups are
# task-bound — a cross-task exit raises "cancel scope in a different task"), so
# we cannot share one long-lived lifespan across tests via a fixture. Instead
# each test builds a fresh app and resets the singleton's lazily-created session
# manager so a brand-new one is spun up for that test's lifespan.


@contextlib.asynccontextmanager
async def _mcp_app_with_lifespan():
    # Force a fresh StreamableHTTPSessionManager for this test's lifespan.
    server._session_manager = None
    app = create_app()
    async with app.router.lifespan_context(app):
        yield app


@contextlib.asynccontextmanager
async def _mcp_session(app):
    """Open an initialized ClientSession against the mounted /mcp over ASGI.

    Builds one in-process httpx client backed by ``ASGITransport(app)`` and hands
    it to the SDK's ``streamable_http_client`` so no real socket is opened.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as http_client:
        async with streamable_http_client(
            "http://localhost/mcp/", http_client=http_client
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


@pytest.mark.asyncio
async def test_mcp_transport_lists_four_tools():
    """Full initialize handshake + tools/list over the mounted path succeeds.

    This exercises the lifespan (session manager must be running) and the path
    resolution (/mcp, not /mcp/mcp). No Authorization header is needed for the
    protocol-level handshake and listing.
    """
    async with _mcp_app_with_lifespan() as app:
        async with _mcp_session(app) as session:
            result = await session.list_tools()
            names = {t.name for t in result.tools}
            assert names == {
                "search_leads",
                "get_lead_summary",
                "pipeline_overview",
                "list_pipelines",
            }


@pytest.mark.asyncio
async def test_mcp_transport_tool_call_without_auth_surfaces_error():
    """A tool call with NO Authorization header surfaces an auth error.

    ``resolve_service_key`` raises HTTP 401 on a missing token BEFORE touching
    the DB, so this needs no Postgres. What we assert is that the failure is an
    application auth error, NOT a 500 task-group RuntimeError and NOT real CRM
    data — i.e. the lifespan ran and the path resolved, but the request was
    correctly rejected for missing auth.
    """
    async with _mcp_app_with_lifespan() as app:
        async with _mcp_session(app) as session:
            result = await session.call_tool("list_pipelines", {})
            # The tool raised (HTTPException 401 → tool error result).
            assert result.isError is True
            text = " ".join(
                getattr(block, "text", "") for block in result.content
            ).lower()
            # Must be the auth failure, not a task-group RuntimeError.
            assert "task group is not initialized" not in text
            assert "401" in text or "missing key" in text or "unauthorized" in text
