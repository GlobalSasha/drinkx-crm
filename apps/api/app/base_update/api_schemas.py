"""REST DTOs for /api/base-update/*."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    status: str
    file_count: int
    source_filenames: list[str] | None = None
    stats_json: dict | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("stats_json", mode="before")
    @classmethod
    def _strip_internal(cls, v: object) -> object:
        if not isinstance(v, dict):
            return v
        return {k: val for k, val in v.items() if not k.startswith("_")} or None


class IngestRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ingest_job_id: uuid.UUID
    company_name: str
    normalized_name: str
    extracted_json: dict | None = None
    match_company_id: uuid.UUID | None = None
    match_lead_id: uuid.UUID | None = None
    action: str | None = None
    source_files: list[str] | None = None
    confidence: float | None = None
    error: str | None = None


class IngestConflictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ingest_job_id: uuid.UUID
    ingest_record_id: uuid.UUID
    type: str
    target_kind: str
    field_name: str | None = None
    base_value: str | None = None
    incoming_value: str | None = None
    candidates_json: list | None = None
    status: str
    resolution: str | None = None
    resolved_value: str | None = None
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None


class ResolveConflictIn(BaseModel):
    """Body for PATCH /conflicts/{id}. The orchestrator interprets these values
    when apply_resolutions runs; the legal `resolution` strings are the R_* constants."""

    resolution: str = Field(..., min_length=1, max_length=20)
    resolved_value: str | None = None
