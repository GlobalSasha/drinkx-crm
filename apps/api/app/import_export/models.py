"""Import/export ORM models — Sprint 2.1 G1.

ImportJob owns the lifecycle of a single file → preview → confirm → apply
flow. ImportError captures per-row validation/apply failures so the manager
can see exactly what didn't land after the Celery task finishes.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin


class ImportJobStatus(str, Enum):
    uploaded = "uploaded"      # file received, no mapping yet
    mapping = "mapping"        # manager picking column targets
    previewed = "previewed"    # dry-run validation done, awaiting confirm
    running = "running"        # Celery is applying
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ImportJobFormat(str, Enum):
    xlsx = "xlsx"
    csv = "csv"
    yaml = "yaml"
    json = "json"
    bitrix24 = "bitrix24"
    amocrm = "amocrm"
    bulk_update_yaml = "bulk_update_yaml"


class ImportJob(Base, UUIDPrimaryKeyMixin):
    """One bulk-import attempt. Explicit `created_at`/`finished_at` —
    we don't track an `updated_at` since most state lives inside `diff_json`."""
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index(
            "ix_import_jobs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
        Index("ix_import_jobs_user_status", "user_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="uploaded", server_default="uploaded", nullable=False
    )
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    source_filename: Mapped[str] = mapped_column(
        String(300), default="", server_default="", nullable=False
    )
    upload_size_bytes: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_rows: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    processed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    succeeded: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    failed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Parsed rows + column mapping + dry-run validation summary.
    # Stored in Postgres (not Redis) so previews survive worker restarts.
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExportJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class ExportJobFormat(str, Enum):
    xlsx = "xlsx"
    csv = "csv"
    json = "json"
    yaml = "yaml"
    md_zip = "md_zip"


class ExportJob(Base, UUIDPrimaryKeyMixin):
    """One bulk-export attempt. Result bytes live in Redis under
    `export:{id}` with a 1h TTL — the row stores the key for audit /
    recovery, plus result counts and the manager's filter snapshot.
    """
    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_workspace", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    filters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    redis_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ImportError(Base, UUIDPrimaryKeyMixin):
    """One row × field failure during import. Lifetime tied to ImportJob."""
    __tablename__ = "import_errors"
    __table_args__ = (
        Index("ix_import_errors_job_row", "job_id", "row_number"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(
        String(60), default="", server_default="", nullable=False
    )
    message: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
