"""The lead-agent AUTO suggestion flag gates the scheduled tasks.

When `lead_agent_auto_suggestions_enabled` is False (the default), the
silence scan and the per-lead refresh tasks short-circuit and never invoke
the runner — so no automatic `ai_suggestion` feed cards get written. Every
auto trigger (6h beat scan, stage-change hook, inbox refresh) funnels
through `lead_agent_refresh_suggestion`, so this one guard covers them all.
Manual «Спросить Блейка» uses a separate code path and is unaffected.
"""
from __future__ import annotations

from uuid import uuid4


def test_refresh_suggestion_disabled_by_default(monkeypatch):
    from app.config import get_settings
    from app.scheduled.jobs import lead_agent_refresh_suggestion

    monkeypatch.setattr(
        get_settings(), "lead_agent_auto_suggestions_enabled", False
    )
    lead_id = str(uuid4())
    result = lead_agent_refresh_suggestion(lead_id)

    assert result["status"] == "disabled"
    assert result["lead_id"] == lead_id


def test_scan_silence_disabled_by_default(monkeypatch):
    from app.config import get_settings
    from app.scheduled.jobs import lead_agent_scan_silence

    monkeypatch.setattr(
        get_settings(), "lead_agent_auto_suggestions_enabled", False
    )
    result = lead_agent_scan_silence()

    assert result["status"] == "disabled"


def test_refresh_suggestion_runs_when_enabled(monkeypatch):
    """With the flag on, the gate passes through to the runner core."""
    from app.config import get_settings
    from app.scheduled.jobs import lead_agent_refresh_suggestion

    monkeypatch.setattr(
        get_settings(), "lead_agent_auto_suggestions_enabled", True
    )

    called: dict = {}

    async def _fake_refresh(lead_uuid):
        called["lead"] = lead_uuid
        return {"status": "ok"}

    monkeypatch.setattr(
        "app.lead_agent.tasks.refresh_suggestion_async", _fake_refresh
    )

    lead_id = str(uuid4())
    result = lead_agent_refresh_suggestion(lead_id)

    assert result == {"status": "ok"}
    assert str(called["lead"]) == lead_id
