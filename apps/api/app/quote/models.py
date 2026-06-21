"""Quote/КП product catalog — Sprint Quote v1, Phase 1.

The catalog a quote line can reference. Products only exist to serve quotes,
so they live in the `quote` domain (YAGNI — no separate `products` domain).
Workspace-scoped; soft-deletable (never hard-delete) so historical quote
lines that reference a product keep resolving.
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


# Quote status lifecycle. Transitions are permissive (any manual move is
# allowed); each just stamps the relevant timestamp — see quote.services.
QUOTE_STATUSES = ("draft", "sent", "accepted", "rejected")


class Quote(Base, UUIDPrimaryKeyMixin):
    """A commercial proposal (КП) for a lead. subtotal/total are
    server-computed and stored — see quote.services.compute_totals."""

    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number", name="uq_quotes_workspace_number"),
        Index("ix_quotes_lead", "lead_id"),
        Index("ix_quotes_workspace", "workspace_id"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="draft", server_default="draft"
    )
    recipient_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    vat_rate: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=20, server_default="20"
    )
    discount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    subtotal: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lines: Mapped[list["QuoteLine"]] = relationship(
        cascade="all, delete-orphan",
        order_by="QuoteLine.position",
        lazy="selectin",
    )


class QuoteLine(Base, UUIDPrimaryKeyMixin):
    """One line item on a quote. product_id_ref null = free-text row;
    product_name is denormalized so catalog edits/deletes don't corrupt
    a historical quote."""

    __tablename__ = "quote_lines"
    __table_args__ = (Index("ix_quote_lines_quote", "quote_id"),)

    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    product_id_ref: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=1, server_default="1"
    )
    unit_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    line_discount_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default="0"
    )
    total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
