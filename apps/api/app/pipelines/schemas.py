"""Pipeline + Stage Pydantic schemas."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    position: int
    color: str
    rot_days: int
    probability: int
    is_won: bool
    is_lost: bool
    gate_criteria_json: list[str]


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    type: str
    is_default: bool
    position: int
    stages: list[StageOut]
