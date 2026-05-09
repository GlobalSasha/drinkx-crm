"""Automation Builder Pydantic schemas — Sprint 2.5 G1."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirror models.VALID_TRIGGERS / VALID_ACTIONS / VALID_RUN_STATUSES.
# Pydantic Literal validates at the API boundary so the service never
# sees a stray string.
TriggerType = Literal["stage_change", "form_submission", "inbox_match"]
ActionType = Literal["send_template", "create_task", "move_stage"]
RunStatus = Literal["queued", "success", "skipped", "failed"]


class AutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    trigger: TriggerType
    trigger_config_json: dict[str, Any] | None = None
    condition_json: dict[str, Any] | None = None
    action_type: ActionType
    action_config_json: dict[str, Any]
    is_active: bool
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AutomationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    trigger: TriggerType
    trigger_config_json: dict[str, Any] | None = None
    condition_json: dict[str, Any] | None = None
    action_type: ActionType
    action_config_json: dict[str, Any]
    is_active: bool = True


class AutomationUpdate(BaseModel):
    """PATCH body. All optional — UI sends only changed fields. Setting
    `is_active=False` is the soft-disable path (preferable to delete
    when the rule has run history)."""
    name: str | None = Field(None, min_length=1, max_length=255)
    trigger: TriggerType | None = None
    trigger_config_json: dict[str, Any] | None = None
    condition_json: dict[str, Any] | None = None
    action_type: ActionType | None = None
    action_config_json: dict[str, Any] | None = None
    is_active: bool | None = None


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    automation_id: uuid.UUID
    lead_id: uuid.UUID | None
    status: RunStatus
    error: str | None = None
    executed_at: datetime
