"""Whitelist response schemas for the external OS read surface.

Never serialize ORM models directly. Only the fields below leave the
system. Dates are timezone-aware and serialize as ISO 8601 UTC.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LeadOut(_Base):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    company_name: str
    segment: str | None = None
    city: str | None = None
    source: str | None = None
    pipeline_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    stage_entered_at: datetime | None = None
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None
    deal_type: str | None = None
    priority: str | None = None
    score: int = 0
    assignment_status: str
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    next_action_at: datetime | None = None
    last_activity_at: datetime | None = None
    won_at: datetime | None = None
    lost_at: datetime | None = None
    tags: list[str] = Field(default=[], validation_alias="tags_json")
    created_at: datetime
    updated_at: datetime


class LeadPage(_Base):
    items: list[LeadOut]
    next_cursor: str | None = None


class CompanyOut(_Base):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    inn: str | None = None
    website: str | None = None
    city: str | None = None
    segment: str | None = Field(default=None, validation_alias="primary_segment")
    created_at: datetime
    updated_at: datetime


class CompanyPage(_Base):
    items: list[CompanyOut]
    next_cursor: str | None = None


class ContactOut(_Base):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    name: str
    position: str | None = Field(default=None, validation_alias="title")
    email: str | None = None
    phone: str | None = None
    lead_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class StageOut(_Base):
    id: uuid.UUID
    name: str
    position: int
    probability: int
    is_won: bool
    is_lost: bool
    rot_days: int


class PipelineOut(_Base):
    id: uuid.UUID
    name: str
    position: int
    stages: list[StageOut]


class LeadSummaryOut(BaseModel):
    lead: LeadOut
    company: CompanyOut | None = None
    contacts: list[ContactOut] = []
    stage_name: str | None = None
    stage_probability: int | None = None
    days_in_stage: int | None = None
    is_rotting_stage: bool = False
    is_rotting_next_step: bool = False


class StageSummary(BaseModel):
    stage_id: uuid.UUID
    stage_name: str
    lead_count: int
    total_amount: Decimal
    rotting_count: int


class PipelineSummaryOut(BaseModel):
    pipeline_id: uuid.UUID
    pipeline_name: str
    stages: list[StageSummary]
    total_leads: int
    total_amount: Decimal


class ManagerOut(BaseModel):
    id: uuid.UUID
    name: str


class MetaOut(BaseModel):
    contract_version: str
    stages: list[StageOut]
    managers: list[ManagerOut]
