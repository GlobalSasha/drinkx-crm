"""Workspace and User ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.pipelines.models import Pipeline


# Roles used across the app — keep in sync with web/lib/types.ts (Sprint 1.2)
USER_ROLES = ("admin", "head", "manager")

DEFAULT_SCORING_CRITERIA = [
    {"criterion_key": "scale_potential",       "label": "Масштаб потенциала",       "weight": 20, "max_value": 5},
    {"criterion_key": "pilot_probability_90d", "label": "Вероятность пилота 90д",   "weight": 15, "max_value": 5},
    {"criterion_key": "economic_buyer",        "label": "Экономический покупатель", "weight": 15, "max_value": 5},
    {"criterion_key": "reference_value",       "label": "Референсная ценность",     "weight": 15, "max_value": 5},
    {"criterion_key": "standard_product",      "label": "Стандартный продукт",      "weight": 10, "max_value": 5},
    {"criterion_key": "data_readiness",        "label": "Готовность данных",        "weight": 10, "max_value": 5},
    {"criterion_key": "partner_potential",     "label": "Партнёрский потенциал",    "weight": 10, "max_value": 5},
    {"criterion_key": "budget_confirmed",      "label": "Бюджет подтверждён",       "weight": 5,  "max_value": 5},
]


class Workspace(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    plan: Mapped[str] = mapped_column(String(40), default="free", nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Lead Pool: how many cards a manager picks per "weekly sprint"
    sprint_capacity_per_week: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    # Sprint 2.3 G1: canonical pointer to the workspace's default
    # pipeline (FK SET NULL). Replaces the boolean Pipeline.is_default
    # signal as the single source of truth — old code still reads
    # is_default for back-compat, new code reads through here.
    default_pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="SET NULL"),
        nullable=True,
    )

    users: Mapped[list[User]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    pipelines: Mapped[list[Pipeline]] = relationship(  # noqa: F821
        back_populates="workspace",
        cascade="all, delete-orphan",
        foreign_keys="Pipeline.workspace_id",
    )
    scoring_criteria: Mapped[list["ScoringCriteria"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
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


class UserInvite(Base, UUIDPrimaryKeyMixin):
    """Track team invitations issued via Supabase magic-link
    (Sprint 2.4 G1). Source of truth for the admin UI; auth bootstrap
    does NOT read this table on sign-in — the invitee just joins the
    canonical workspace as `manager` per ADR-021, and the inviter
    promotes them via PATCH /api/users/{id}/role afterwards."""

    __tablename__ = "user_invites"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    suggested_role: Mapped[str] = mapped_column(
        String(20), default="manager", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "email", name="ix_user_invites_workspace_email"
        ),
    )


class ScoringCriteria(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scoring_criteria"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    max_value: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    workspace: Mapped["Workspace"] = relationship(back_populates="scoring_criteria")

    __table_args__ = (
        UniqueConstraint("workspace_id", "criterion_key", name="uq_scoring_criteria_workspace_key"),
    )
