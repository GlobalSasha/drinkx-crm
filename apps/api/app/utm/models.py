"""UTM dictionary ORM models — Odoo `utm.source/medium/campaign` pattern.

Each is a per-workspace dictionary keyed by a unique name. `is_auto` marks rows
created automatically from inbound form params (vs. manually curated). Campaigns
additionally carry an optional owner (Odoo `utm.campaign.user_id`) — a hook for
attributing the lead's owner from the campaign later.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class UtmSource(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "utm_sources"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_utm_sources_ws_name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UtmMedium(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "utm_mediums"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_utm_mediums_ws_name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UtmCampaign(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "utm_campaigns"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_utm_campaigns_ws_name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Optional campaign owner (Odoo utm.campaign.user_id) — attribution hook.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
