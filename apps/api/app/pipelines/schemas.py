"""Pipeline + Stage Pydantic schemas.

Sprint 2.3 G1 expansion: writable shapes for the new admin-only
CRUD endpoints. The previously read-only `PipelineOut` shape is
unchanged so existing frontend code keeps working.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Read shapes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Write shapes (Sprint 2.3 G1)
#
# A `StageIn` carries everything the manager needs to define a stage
# from scratch — the gate engine still works against `gate_criteria_json`,
# the rotting heuristic still reads `rot_days`. We expose all of these
# for forward-compat with the Settings UI even though v1 of the UI may
# only set name + color + is_won/is_lost.
# ---------------------------------------------------------------------------

class StageIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    position: int = Field(ge=0, le=99)
    color: str = Field(default="#a1a1a6", max_length=20)
    rot_days: int = Field(default=7, ge=0, le=365)
    probability: int = Field(default=10, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False
    gate_criteria_json: list[str] = Field(default_factory=list)

    @field_validator("color")
    @classmethod
    def _color_is_hex(cls, v: str) -> str:
        # Loose validation — manager enters #rrggbb / #rgb / a CSS name
        # we don't try to be picky.
        v = v.strip()
        if not v:
            return "#a1a1a6"
        return v[:20]


class PipelineCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="sales", max_length=40)
    stages: list[StageIn] = Field(min_length=1, max_length=24)


class PipelineUpdateIn(BaseModel):
    """PATCH /api/pipelines/{id} — rename + replace stages.

    `stages` is omit-or-full-replace, not row-level merge. The Settings
    UI sends the entire stage list back on save. Lead.stage_id stays
    intact via stage IDs (not auto-assigned UUIDs); the editor produces
    new IDs only for newly-added rows.
    """
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = Field(default=None, max_length=40)
    stages: list[StageIn] | None = None
