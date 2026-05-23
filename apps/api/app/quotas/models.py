"""ORM model for sales quotas.

A quota is a revenue target for a specific user within a specific period.
Workspace-scoped. v1 is data-model only — there's no admin UI yet; the
table exists so the /forecast page can compute Pipeline Coverage and
Forecast Accuracy once quotas start being set (manually via SQL for now,
or via a future Settings → Команда → Квоты page).

A single user may have multiple overlapping quotas (e.g. monthly +
quarterly) — there's no uniqueness constraint on (user, period).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime  # noqa: F401 — datetime used by TimestampedMixin via metaclass

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class Quota(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "quotas"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
