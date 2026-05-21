"""LeadNote ORM model — free-form client notes.

Notes are observations about a client, not tasks (no due date, no
checkbox) and not activities (never shown in the activity feed). They
survive lead transfers and always credit the original author.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class LeadNote(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "lead_notes"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Author. SET NULL on user delete — the note stays, author_name
    # falls back to "Удалённый пользователь".
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
