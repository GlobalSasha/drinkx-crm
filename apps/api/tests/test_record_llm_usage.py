"""Sprint 4.0 — record_llm_usage best-effort behaviour."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


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
    # Patch the symbol insert_usage looks up so LlmUsage(...) accepts kwargs
    # under the SQLAlchemy stub; auto-restored on context exit (no global leak).
    with patch("app.llm_usage.repositories.LlmUsage", MagicMock()):
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
    with patch("app.llm_usage.repositories.LlmUsage", MagicMock()):
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
