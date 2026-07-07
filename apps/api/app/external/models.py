"""ServiceApiKey — machine credential for external OS read access."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class ServiceApiKey(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    """A hashed machine key scoped to one workspace.

    The full token is `drinkx_os_<random>`; only its sha256 hash lives
    here. `scopes` is a JSON list (v1: `["read:core"]`). A revoked key
    has `revoked_at` set and is rejected by `require_service_key`.
    """

    __tablename__ = "service_api_keys"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
