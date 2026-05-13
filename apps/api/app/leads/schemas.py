"""Pydantic DTOs for leads endpoints."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.leads.constants import SEGMENT_KEYS, normalize_city
from app.leads.models import AssignmentStatus, DealType, Priority  # noqa: F401 — imported for OpenAPI clarity


def _validate_segment(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value not in SEGMENT_KEYS:
        raise ValueError(
            f"Invalid segment '{value}'. Must be one of: {SEGMENT_KEYS}"
        )
    return value


class LeadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    segment: str | None = None
    city: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    inn: str | None = None
    source: str | None = None
    tags_json: list[str] = Field(default_factory=list)
    deal_type: str | None = None
    priority: str | None = None
    score: int = 0
    blocker: str | None = None
    next_step: str | None = None
    next_action_at: datetime | None = None


class LeadCreate(LeadBase):
    """Used by managers; assignment_status forced to 'assigned' to current user."""

    pipeline_id: UUID | None = None
    stage_id: UUID | None = None
    # Sprint 3.3 — optional company link. When set, the service copies
    # `companies.name` into `leads.company_name` so the snapshot stays
    # correct from creation onward.
    company_id: UUID | None = None

    @field_validator("segment")
    @classmethod
    def _segment(cls, v: str | None) -> str | None:
        return _validate_segment(v)

    @field_validator("city")
    @classmethod
    def _city(cls, v: str | None) -> str | None:
        return normalize_city(v)


class LeadUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str | None = None
    segment: str | None = None
    city: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    inn: str | None = None
    source: str | None = None
    tags_json: list[str] | None = None
    deal_type: str | None = None
    priority: str | None = None
    score: int | None = None
    blocker: str | None = None
    next_step: str | None = None
    next_action_at: datetime | None = None
    pipeline_id: UUID | None = None
    stage_id: UUID | None = None

    @field_validator("segment")
    @classmethod
    def _segment(cls, v: str | None) -> str | None:
        return _validate_segment(v)

    @field_validator("city")
    @classmethod
    def _city(cls, v: str | None) -> str | None:
        return normalize_city(v)


class LeadOut(LeadBase):
    id: UUID
    workspace_id: UUID
    pipeline_id: UUID | None
    stage_id: UUID | None
    fit_score: Decimal | None = None
    assignment_status: str
    assigned_to: UUID | None
    assigned_at: datetime | None
    transferred_from: UUID | None
    transferred_at: datetime | None
    is_rotting_stage: bool
    is_rotting_next_step: bool
    last_activity_at: datetime | None
    archived_at: datetime | None
    won_at: datetime | None
    lost_at: datetime | None
    lost_reason: str | None
    ai_data: dict | None = None
    created_at: datetime
    updated_at: datetime


class LeadListOut(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    page_size: int


class SprintCreateIn(BaseModel):
    cities: list[str] = Field(default_factory=list)
    segment: str | None = None
    limit: int | None = None  # if None, falls back to workspace.sprint_capacity_per_week


class SprintCreateOut(BaseModel):
    claimed_count: int
    requested: int
    items: list[LeadOut]


class TransferIn(BaseModel):
    to_user_id: UUID
    comment: str | None = None


class MoveStageIn(BaseModel):
    stage_id: UUID
    gate_skipped: bool = False
    skip_reason: str | None = None
    lost_reason: str | None = None  # only used when entering lost stage


class GateViolationOut(BaseModel):
    """Shape of one violation returned in 409 detail.violations[]."""
    code: str
    message: str
    hard: bool = False


class MoveStageBlockedDetail(BaseModel):
    """Body of the 409 response when a stage transition is blocked by gates."""
    message: str
    violations: list[GateViolationOut]
