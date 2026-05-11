"""Pydantic DTOs for companies endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = None
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)
    website: str | None = None
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = None
    city: str | None = None
    address: str | None = None
    primary_segment: str | None = None
    employee_range: str | None = None
    notes: str | None = None


class CompanyCreate(CompanyBase):
    """Payload for POST /companies. `normalized_name` and `domain` are
    derived server-side — see ADR-022."""


class CompanyUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = None
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)
    website: str | None = None
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = None
    city: str | None = None
    address: str | None = None
    primary_segment: str | None = None
    employee_range: str | None = None
    notes: str | None = None


class CompanyOut(CompanyBase):
    id: UUID
    workspace_id: UUID
    normalized_name: str
    domain: str | None = None
    is_archived: bool
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DuplicateCandidate(BaseModel):
    """Returned inside the 409 body when a creation hit a duplicate."""

    id: UUID
    name: str
    inn: str | None = None
    leads_count: int


class CompanyListOut(BaseModel):
    items: list[CompanyOut]
    total: int


class CompanyLeadOut(BaseModel):
    """Lead summary inside the company card response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    stage_id: UUID | None = None
    score: int
    fit_score: float | None = None
    assigned_to: UUID | None = None
    created_at: datetime


class CompanyContactOut(BaseModel):
    """Contact summary inside the company card response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    lead_id: UUID


class CompanyActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID
    type: str
    subject: str | None = None
    body: str | None = None
    created_at: datetime


class CompanyCardOut(CompanyOut):
    """`GET /companies/{id}` — card payload."""

    leads: list[CompanyLeadOut] = Field(default_factory=list)
    contacts: list[CompanyContactOut] = Field(default_factory=list)
    recent_activities: list[CompanyActivityOut] = Field(default_factory=list)
