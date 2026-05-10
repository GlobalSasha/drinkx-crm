"""Automation Builder Pydantic schemas — Sprint 2.5 G1, multi-step Sprint 2.7 G2."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirror models.VALID_TRIGGERS / VALID_ACTIONS / VALID_*_STATUSES.
# Pydantic Literal validates at the API boundary so the service never
# sees a stray string.
TriggerType = Literal["stage_change", "form_submission", "inbox_match"]
ActionType = Literal["send_template", "create_task", "move_stage"]
StepType = Literal["delay_hours", "send_template", "create_task", "move_stage"]
RunStatus = Literal["queued", "success", "skipped", "failed"]
StepRunStatus = Literal["pending", "success", "skipped", "failed"]


class AutomationStep(BaseModel):
    """One node in a multi-step chain. `type=delay_hours` only carries
    a `config.hours` int; the other types match `ActionType` and use
    the same config shapes as legacy `action_config_json`."""
    type: StepType
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    trigger: TriggerType
    trigger_config_json: dict[str, Any] | None = None
    condition_json: dict[str, Any] | None = None
    action_type: ActionType
    action_config_json: dict[str, Any]
    # Sprint 2.7 G2 — null/empty = legacy single-action behaviour.
    steps_json: list[dict[str, Any]] | None = None
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
    # Sprint 2.7 G2 — when present, the legacy action_type/_config still
    # has to be valid (we serialize the first step into it for back-
    # compat with older clients reading the row), but the steps are
    # the source of truth for execution.
    steps_json: list[AutomationStep] | None = None
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
    steps_json: list[AutomationStep] | None = None
    is_active: bool | None = None


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    automation_id: uuid.UUID
    lead_id: uuid.UUID | None
    status: RunStatus
    error: str | None = None
    executed_at: datetime


class AutomationStepRunOut(BaseModel):
    """Per-step row used by the RunsDrawer grid below the parent run."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    automation_run_id: uuid.UUID
    step_index: int
    step_json: dict[str, Any]
    scheduled_at: datetime
    executed_at: datetime | None
    status: StepRunStatus
    error: str | None = None
