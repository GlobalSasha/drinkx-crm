"""ORM models for the base_update domain.

IngestJob 1—N IngestRecord 1—N IngestConflict. All workspace-scoped,
FK cascade. Mirrors the import_export job/status-string convention.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.base_update import constants as c
from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class IngestJob(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "ingest_jobs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=c.JOB_PENDING, index=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_filenames: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    stats_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    records: Mapped[list["IngestRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class IngestRecord(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "ingest_records"

    ingest_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    extracted_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    match_company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    match_lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_files: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["IngestJob"] = relationship(back_populates="records")
    conflicts: Mapped[list["IngestConflict"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class IngestConflict(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "ingest_conflicts"

    ingest_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingest_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    base_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    incoming_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=c.CONFLICT_OPEN, index=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    record: Mapped["IngestRecord"] = relationship(back_populates="conflicts")
