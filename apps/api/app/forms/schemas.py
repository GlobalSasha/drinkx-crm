"""Pydantic schemas for the WebForms domain — Sprint 2.2 G1.

`WebFormOut.embed_snippet` is a synthetic field — computed at serialise
time from settings.api_base_url + slug, never stored on the row.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Field types accepted by the form builder.
FieldType = Literal["text", "email", "phone", "textarea", "select"]


class FieldDefinition(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=200)
    type: FieldType
    required: bool = False
    options: list[str] | None = None  # required for type='select'


class WebFormCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fields_json: list[FieldDefinition] = Field(default_factory=list)
    target_pipeline_id: UUID | None = None
    target_stage_id: UUID | None = None
    redirect_url: str | None = Field(default=None, max_length=500)
    default_assignee_id: UUID | None = None
    contact_task_sla_hours: int = Field(default=2, ge=1, le=240)
    source_label: str | None = Field(default=None, max_length=120)
    notify_email: str | None = Field(default=None, max_length=254)
    require_key: bool = False  # True → server generates ingest_token


class WebFormUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    fields_json: list[FieldDefinition] | None = None
    target_pipeline_id: UUID | None = None
    target_stage_id: UUID | None = None
    redirect_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    default_assignee_id: UUID | None = None
    contact_task_sla_hours: int | None = Field(default=None, ge=1, le=240)
    source_label: str | None = Field(default=None, max_length=120)
    notify_email: str | None = Field(default=None, max_length=254)
    require_key: bool | None = None


class WebFormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by: UUID | None
    name: str
    slug: str
    fields_json: list[dict]
    target_pipeline_id: UUID | None
    target_stage_id: UUID | None
    redirect_url: str | None
    is_active: bool
    submissions_count: int
    created_at: datetime
    updated_at: datetime

    # Synthetic — populated by the router via build_embed_snippet().
    embed_snippet: str | None = None

    default_assignee_id: UUID | None = None
    contact_task_sla_hours: int = 2
    source_label: str | None = None
    notify_email: str | None = None
    ingest_token: str | None = None


class WebFormPageOut(BaseModel):
    items: list[WebFormOut]
    total: int
    page: int
    page_size: int


class FormSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    web_form_id: UUID
    lead_id: UUID | None
    utm_json: dict | None
    source_domain: str | None
    created_at: datetime


class FormSubmissionPageOut(BaseModel):
    items: list[FormSubmissionOut]
    total: int
    page: int
    page_size: int


class FormStatsOut(BaseModel):
    """Per-form stats card — Sprint 3.6 G3."""
    submissions_7d: int
    submissions_30d: int
    claimed_count: int
    by_stage: dict[str, int]


class FormChannelStat(BaseModel):
    form_id: UUID
    channel: str          # source_label or name
    submissions: int
    leads: int
    won: int
    conversion: float     # won / leads, 0.0 when leads == 0


class FormAnalyticsOut(BaseModel):
    rows: list[FormChannelStat]
    total_submissions: int
    total_leads: int
    total_won: int
