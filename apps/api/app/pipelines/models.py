"""Pipeline and Stage ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin

# Pipeline types (from PRD §6.2)
PIPELINE_TYPES = ("sales", "partner", "service")


class Pipeline(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "pipelines"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(40), default="sales", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    workspace = relationship("Workspace", back_populates="pipelines")
    stages: Mapped[list[Stage]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="Stage.position",
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_pipeline_workspace_name"),
    )


class Stage(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "stages"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#a1a1a6", nullable=False)
    rot_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    probability: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # 0-100
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


# Default seed for the first pipeline created per workspace.
# Used by app/auth/services.py:bootstrap_workspace().
DEFAULT_STAGES = [
    {"name": "Новые лиды", "position": 0, "color": "#a1a1a6", "rot_days": 7, "probability": 5},
    {"name": "Квалификация", "position": 1, "color": "#0a84ff", "rot_days": 5, "probability": 20},
    {"name": "КП отправлено", "position": 2, "color": "#af52de", "rot_days": 3, "probability": 40},
    {"name": "Переговоры", "position": 3, "color": "#ff9f0a", "rot_days": 5, "probability": 60},
    {"name": "Согласование", "position": 4, "color": "#34c759", "rot_days": 7, "probability": 80},
    {"name": "Закрыто (won)", "position": 5, "color": "#34c759", "rot_days": 0, "probability": 100, "is_won": True},
    {"name": "Закрыто (lost)", "position": 6, "color": "#ff3b30", "rot_days": 0, "probability": 0, "is_lost": True},
]
