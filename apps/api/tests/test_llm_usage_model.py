"""Sprint 4.0 — LlmUsage model shape."""
from __future__ import annotations

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_llm_usage_table_and_columns():
    from app.llm_usage.models import LlmUsage

    assert LlmUsage.__tablename__ == "llm_usage"

    # Under the sqlalchemy stub __table__ is not available; check attributes.
    for attr in (
        "id", "workspace_id", "task_type", "provider", "model",
        "prompt_tokens", "completion_tokens", "cost_usd",
    ):
        assert hasattr(LlmUsage, attr), f"LlmUsage missing attribute: {attr}"
