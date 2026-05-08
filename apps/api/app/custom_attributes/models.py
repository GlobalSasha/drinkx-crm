"""Custom Attributes ORM — Sprint 2.4 G3.

EAV shape:
  - `CustomAttributeDefinition` — schema + UI metadata.
  - `LeadCustomValue` — per-lead value. Three polymorphic columns; the
    `kind` on the definition determines which column is populated.

Why EAV instead of a JSON blob on Lead: filters / segments will need
to query values by definition (e.g. «show me leads where Region =
EMEA»). A JSON sidecar makes that hard to index. Two narrow tables
keep the indexes simple — `(workspace_id, key)` on definitions,
`(lead_id, definition_id)` on values.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin


# Allowed `kind` values. Keep in sync with web/lib/types.ts. Adding a new
# kind requires a new column on `lead_custom_values` (or a JSON fallback) —
# don't extend this list lightly.
ATTRIBUTE_KINDS = ("text", "number", "date", "select")


class CustomAttributeDefinition(Base, UUIDPrimaryKeyMixin):
    """Schema for one custom field on Lead. Workspace-scoped — same key
    across two workspaces is fine."""
    __tablename__ = "custom_attribute_definitions"
    __table_args__ = (
        # `key` is what code references (e.g. lead-import column header).
        # Unique per workspace — re-using the same key in another workspace
        # is fine; the EAV table joins via definition_id, not by key.
        UniqueConstraint(
            "workspace_id", "key", name="uq_custom_attr_def_workspace_key"
        ),
        Index("ix_custom_attr_def_workspace", "workspace_id", "position"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    # `key`: machine-readable, e.g. "preferred_region". Lowercase,
    # ascii, immutable post-create (changing it would orphan values).
    # The service layer enforces immutability.
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    # `label`: human-readable, shown in the UI. Editable.
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # One of ATTRIBUTE_KINDS. Stored as a plain String for forward-
    # compat — the validation lives in the service, not the column type.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # For kind='select' — list of {value, label} dicts. Empty for the
    # other kinds. Renderer treats null and [] interchangeably.
    options_json: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Display order. v1 UI uses up/down buttons (no dnd-kit until 2.4+
    # polish carryover); the service auto-assigns position on create.
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LeadCustomValue(Base, UUIDPrimaryKeyMixin):
    """One value per (lead, definition). Three nullable typed columns —
    only the one matching the definition's kind is populated."""
    __tablename__ = "lead_custom_values"
    __table_args__ = (
        UniqueConstraint(
            "lead_id", "definition_id", name="uq_lead_custom_value_lead_def"
        ),
        Index("ix_lead_custom_values_def", "definition_id"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "custom_attribute_definitions.id", ondelete="CASCADE"
        ),
        nullable=False,
    )

    # Polymorphic value columns. Exactly one of these is populated per
    # row, matching the definition's `kind`. Service layer enforces
    # the invariant; DB doesn't (a CHECK constraint would balloon the
    # migration with no real safety win — anything writing here goes
    # through the service).
    value_text: Mapped[str | None] = mapped_column(String, nullable=True)
    value_number: Mapped[float | None] = mapped_column(
        Numeric(20, 6), nullable=True
    )
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
