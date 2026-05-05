"""Workspace and User ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.pipelines.models import Pipeline


# Roles used across the app — keep in sync with web/lib/types.ts (Sprint 1.2)
USER_ROLES = ("admin", "head", "manager")


class Workspace(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    plan: Mapped[str] = mapped_column(String(40), default="free", nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Lead Pool: how many cards a manager picks per "weekly sprint"
    sprint_capacity_per_week: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    pipelines: Mapped[list[Pipeline]] = relationship(  # noqa: F821
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class User(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "users"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="manager", nullable=False)

    # Profile from onboarding step 2
    working_hours_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    specialization: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="Europe/Moscow", nullable=False)
    max_active_deals: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    # External identity (Supabase user id) — set on first sign-in
    supabase_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="users")
