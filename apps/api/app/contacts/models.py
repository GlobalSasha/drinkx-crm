"""Contact ORM model — multi-stakeholder per lead (ADR-012, ADR-016)."""
from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin
from app.common.phone import to_e164


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

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # E.164-normalized phone — see Lead.phone_e164. Auto-filled via the
    # validator below; used as a dedup / cross-channel match key.
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    @validates("phone")
    def _sync_phone_e164(self, _key: str, value: str | None) -> str | None:
        """Keep `phone_e164` in lock-step with every write to `phone`."""
        self.phone_e164 = to_e164(value)
        return value

    telegram_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    verified_status: Mapped[str] = mapped_column(String(20), default="to_verify", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Same FK-disambiguation as on the Lead side — pin this to the
    # `Contact.lead_id` column so SQLAlchemy doesn't try to use the
    # reverse path through `Lead.primary_contact_id`.
    lead: Mapped["Lead"] = relationship(  # type: ignore[name-defined]
        back_populates="contacts",
        foreign_keys=[lead_id],
    )
