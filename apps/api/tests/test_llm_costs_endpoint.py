"""Sprint 4.0 — get_costs zero-fills providers and totals."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_get_costs_zero_fills_and_totals():
    from app.llm_usage import service

    with patch.object(
        service, "aggregate_by_provider",
        new=AsyncMock(return_value=[("mimo", 40.2, 980), ("anthropic", 5.1, 42)]),
    ):
        out = await service.get_costs(object(), workspace_id=uuid.uuid4(), period="all")

    providers = {p.provider: p for p in out.by_provider}
    assert providers["mimo"].cost_usd == 40.2
    assert providers["gemini"].cost_usd == 0.0  # zero-filled
    assert providers["deepseek"].calls == 0
    assert out.total_usd == round(40.2 + 5.1, 6)
    assert out.period == "all"
