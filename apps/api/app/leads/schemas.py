"""Pydantic DTOs for leads endpoints."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.leads.models import AssignmentStatus, DealType, Priority  # noqa: F401 — imported for OpenAPI clarity


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
