"""MCP server exposes exactly the 4 read-only tools.

Structure-level test (no live transport): FastMCP.list_tools() is an async
accessor in mcp 1.28.1 that returns MCPTool objects with a `.name`.
"""
from __future__ import annotations

import pytest

from app.external.mcp_server import server  # the FastMCP instance


@pytest.mark.asyncio
async def test_four_tools_registered():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"search_leads", "get_lead_summary", "pipeline_overview", "list_pipelines"}
