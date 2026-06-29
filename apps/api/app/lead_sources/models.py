"""LeadSource ORM model — per-workspace dictionary of lead origins.

`is_paid` flags advertising channels (used by the CEO overview to compute
«конверсия с рекламы»). `is_system` marks bootstrap rows (Яндекс Директ, Сайт)
that may be renamed/toggled but never deleted. The list is admin-curated via
`/api/lead-sources` and surfaced in the lead-create form.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class LeadSource(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "lead_sources"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_lead_sources_ws_name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# Seed list applied to every workspace (bootstrap + migration backfill). Tuples
# of (name, is_paid, sort_order); all seeds are is_system=True only for the two
# auto-attributed channels — the manual ones can be removed if a workspace
# doesn't use them.
DEFAULT_LEAD_SOURCES: tuple[dict, ...] = (
    {"name": "Яндекс Директ", "is_paid": True, "is_system": True, "sort_order": 10},
    {"name": "Сайт", "is_paid": False, "is_system": True, "sort_order": 20},
    {"name": "Выставка", "is_paid": False, "is_system": False, "sort_order": 30},
    {"name": "Холодный обзвон", "is_paid": False, "is_system": False, "sort_order": 40},
    {"name": "Реферал", "is_paid": False, "is_system": False, "sort_order": 50},
)
