"""Pydantic schemas — Sprint 2.1 G1 skeleton.

Group 2 will fill in full mapper / preview / row schemas. For now we expose
just enough to drive the routers' health endpoints + the per-job poll.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    user_id: UUID | None
    status: str
    format: str
    source_filename: str
    upload_size_bytes: int
    total_rows: int
    processed: int
    succeeded: int
    failed: int
    error_summary: str | None
    diff_json: dict[str, Any] | None
    created_at: datetime
    finished_at: datetime | None


class ImportErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    row_number: int
    field: str
    message: str
    created_at: datetime


class ImportJobPageOut(BaseModel):
    items: list[ImportJobOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportJobOut(BaseModel):
    """Pydantic model_validate doesn't know about the synthetic
    `download_url` field — services / routers populate it via
    `from_orm_with_url(job)` (see services.export_job_out)."""
    id: UUID
    workspace_id: UUID
    user_id: UUID | None
    status: str
    format: str
    row_count: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    download_url: str | None


class ExportRequestIn(BaseModel):
    format: str  # validated against ExportJobFormat in services
    filters: dict[str, Any] = {}
    include_ai_brief: bool = False
