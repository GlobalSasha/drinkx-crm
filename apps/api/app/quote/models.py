"""Quote/КП product catalog — Sprint Quote v1, Phase 1.

The catalog a quote line can reference. Products only exist to serve quotes,
so they live in the `quote` domain (YAGNI — no separate `products` domain).
Workspace-scoped; soft-deletable (never hard-delete) so historical quote
lines that reference a product keep resolving.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin

# Keep in sync with web/lib/types.ts PRODUCT_CATEGORIES.
PRODUCT_CATEGORIES = ("station", "service", "install", "option", "other")


class Product(Base, UUIDPrimaryKeyMixin):
    """A catalog item a quote line can reference. Workspace-scoped."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_workspace_active", "workspace_id", "is_active"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="other", server_default="other"
    )
    unit_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
