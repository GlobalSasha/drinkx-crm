"""WebForms ORM — Sprint 2.2 G1.

`WebForm` is the form definition (config: name, slug, fields, target
pipeline/stage, redirect URL). `FormSubmission` is one captured
submission carrying the raw payload + attribution (UTM, source domain,
IP). Both lifecycle-tied to the workspace via FK CASCADE.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class WebForm(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    """Public form definition. `slug` is globally unique so the
    /api/forms/{slug}/submit endpoint can route without a workspace
    prefix."""
    __tablename__ = "web_forms"
    __table_args__ = (
        Index("ix_web_forms_workspace", "workspace_id", "is_active"),
        Index("ix_web_forms_slug", "slug", unique=True),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    fields_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)

    target_pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    redirect_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    submissions_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class FormSubmission(Base, UUIDPrimaryKeyMixin):
    """One submission. Explicit `created_at` (no TimestampedMixin) since
    submissions are append-only — no `updated_at` makes sense."""
    __tablename__ = "form_submissions"
    __table_args__ = (
        Index("ix_form_submissions_form", "web_form_id", "created_at"),
        Index("ix_form_submissions_lead", "lead_id"),
    )

    web_form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("web_forms.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    utm_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_domain: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
