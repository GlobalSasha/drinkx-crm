"""Contact ORM model — multi-stakeholder per lead (ADR-012, ADR-016)."""
from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class ContactRoleType(str, Enum):
    economic_buyer = "economic_buyer"
    champion = "champion"
    technical_buyer = "technical_buyer"
    operational_buyer = "operational_buyer"


class VerifiedStatus(str, Enum):
    verified = "verified"
    to_verify = "to_verify"


class Contact(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "contacts"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    telegram_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    verified_status: Mapped[str] = mapped_column(String(20), default="to_verify", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="contacts")  # type: ignore[name-defined]
