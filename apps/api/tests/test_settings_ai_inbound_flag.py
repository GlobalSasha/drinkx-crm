"""Sprint 3.7 G1 — workspace flag that gates the AI-comment job
fired on matched inbound. Default OFF so Layer 1 is truly no-LLM."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_ai_settings_out_exposes_inbound_flag():
    from app.settings.schemas import AISettingsOut

    assert "auto_lead_agent_refresh_on_inbound" in AISettingsOut.model_fields
    # Default OFF — Layer 1 is no-LLM by default.
    default = AISettingsOut.model_fields[
        "auto_lead_agent_refresh_on_inbound"
    ].default
    assert default is False


def test_ai_settings_update_in_accepts_flag():
    from app.settings.schemas import AISettingsUpdateIn

    assert "auto_lead_agent_refresh_on_inbound" in AISettingsUpdateIn.model_fields
    # Optional on PATCH — None means "leave as-is".
    body = AISettingsUpdateIn(auto_lead_agent_refresh_on_inbound=True)
    assert body.auto_lead_agent_refresh_on_inbound is True
