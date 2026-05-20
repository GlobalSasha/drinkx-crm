"""Sprint 4.0 — record_llm_usage best-effort behaviour."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

# Under the SQLAlchemy stub, DeclarativeBase has no metaclass so LlmUsage
# doesn't get an auto-generated __init__ that accepts keyword args.
# Stub the model module so insert_usage can instantiate it in tests.
import sys
from types import ModuleType

def _stub_llm_usage_models():
    if "app.llm_usage.models" in sys.modules:
        return
    mod = ModuleType("app.llm_usage.models")
    mod.LlmUsage = MagicMock  # accepts any kwargs; db.add() receives the mock instance
    sys.modules["app.llm_usage.models"] = mod

_stub_llm_usage_models()


def _result():
    from app.enrichment.providers.base import CompletionResult
    return CompletionResult(
        text="x", model="mimo-flash", provider="mimo",
        prompt_tokens=100, completion_tokens=50, cost_usd=0.0012,
    )


@pytest.mark.asyncio
async def test_record_llm_usage_stages_row_no_commit():
    from app.llm_usage import service

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    ws = uuid.uuid4()
    await service.record_llm_usage(
        db, workspace_id=ws, task_type="research_synthesis", result=_result()
    )

    db.add.assert_called_once()        # row staged on the caller's session
    db.commit.assert_not_called()      # MUST NOT commit the caller's transaction


@pytest.mark.asyncio
async def test_record_llm_usage_swallows_add_error():
    from app.llm_usage import service

    db = MagicMock()
    db.add = MagicMock(side_effect=RuntimeError("session poisoned"))

    # Must NOT raise — telemetry failure cannot break the LLM path.
    await service.record_llm_usage(
        db, workspace_id=uuid.uuid4(), task_type="sales_coach", result=_result()
    )


@pytest.mark.asyncio
async def test_record_llm_usage_no_workspace_is_noop():
    from app.llm_usage import service

    db = MagicMock()
    db.add = MagicMock()
    await service.record_llm_usage(
        db, workspace_id=None, task_type="prefilter", result=_result()
    )
    db.add.assert_not_called()
