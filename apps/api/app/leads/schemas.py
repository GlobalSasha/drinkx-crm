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
    # Sprint 3.3 — optional company link. When set, the service copies
    # `companies.name` into `leads.company_name` so the snapshot stays
    # correct from creation onward.
    company_id: UUID | None = None


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
    ai_data: dict | None = None
    # Primary contact («основной ЛПР») — id from leads.primary_contact_id,
    # name resolved via LEFT JOIN in the list-query repository.
    primary_contact_id: UUID | None = None
    primary_contact_name: str | None = None
    # Open work counters. Split is reminder_kind-based per Sprint pre-flight:
    #   open_tasks_count     = status != 'done' AND reminder_kind = 'manager'
    #   open_followups_count = status != 'done' AND reminder_kind IN ('auto_email', 'ai_hint')
    open_followups_count: int = 0
    open_tasks_count: int = 0
    # Deal-value strip (Lead Card v2, migration 0030)
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None
    # Russian label derived from `priority` letter via
    # `app.leads.scoring.priority_label`. Frontend reads this instead
    # of the raw letter so the LeadCard never has to translate.
    priority_label: str | None = None
    created_at: datetime
    updated_at: datetime


class LeadListItemOut(LeadBase):
    """Slim Lead DTO for list endpoints — drops `ai_data` (AI Brief
    output, can be 50KB per lead) and `agent_state` (Lead AI Agent
    memory). Pipeline + Pool views render company name / score /
    fit_score / priority — none of those need the AI payload, so we
    skip it both on the SQL side (see `defer()` in repositories) and
    in the response model so 200-lead lists stay well under 1MB.
    Fetch the full `LeadOut` via `GET /leads/{id}` when opening a
    card."""

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
    primary_contact_id: UUID | None = None
    primary_contact_name: str | None = None
    open_followups_count: int = 0
    open_tasks_count: int = 0
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None
    priority_label: str | None = None
    created_at: datetime
    updated_at: datetime


class LeadListOut(BaseModel):
    items: list[LeadListItemOut]
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


class PrimaryContactIn(BaseModel):
    """Body for PATCH /leads/{id}/primary-contact. Pass null to clear."""

    contact_id: UUID | None = None


class DealPatchIn(BaseModel):
    """Body for PATCH /leads/{id}/deal — partial update of the
    deal-value strip. Any subset of the three fields is accepted;
    omitted fields stay unchanged. Pass null to clear a single field."""

    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None

    # Whether the field was sent at all (vs. left unset). The router
    # walks model_fields_set so a `null` clears the column but a missing
    # key leaves it alone.
    model_config = ConfigDict(extra="forbid")


class ScoreDetailsPatchIn(BaseModel):
    """Body for PATCH /leads/{id}/score-details. The dict is
    whitelisted server-side against the workspace's `scoring_criteria`;
    keys outside the set are silently dropped. Each value must be
    integer 0..criterion.max_value."""

    score_details: dict[str, int] = Field(default_factory=dict)


class ScoreCriterionOut(BaseModel):
    """One row in the score-breakdown response."""

    key: str
    label: str
    weight: int
    max_value: int
    current_value: int
    contribution: float  # value/max_value * weight, useful for the bar


class ScoreBreakdownOut(BaseModel):
    total: int
    max: int
    priority: str | None
    priority_label: str | None
    criteria: list[ScoreCriterionOut]


class StageDurationOut(BaseModel):
    stage_id: UUID
    stage_name: str
    position: int
    days: int | None
    status: str  # "done" | "current" | "pending"


class GateViolationOut(BaseModel):
    """Shape of one violation returned in 409 detail.violations[]."""
    code: str
    message: str
    hard: bool = False


class MoveStageBlockedDetail(BaseModel):
    """Body of the 409 response when a stage transition is blocked by gates."""
    message: str
    violations: list[GateViolationOut]
