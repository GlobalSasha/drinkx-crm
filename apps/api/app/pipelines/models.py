"""Pipeline and Stage ORM models."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
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
    gate_criteria_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


# Default seed for the first pipeline created per workspace.
# Used by app/auth/services.py:bootstrap_workspace().
DEFAULT_STAGES = [
    {"name": "Новый контакт",      "position": 0,  "color": "#a1a1a6", "rot_days": 3,  "probability": 5},
    {"name": "Квалификация",       "position": 1,  "color": "#0a84ff", "rot_days": 5,  "probability": 15},
    {"name": "Discovery",          "position": 2,  "color": "#5e5ce6", "rot_days": 7,  "probability": 25},
    {"name": "Solution Fit",       "position": 3,  "color": "#bf5af2", "rot_days": 7,  "probability": 40},
    {"name": "Business Case / КП", "position": 4,  "color": "#ff9f0a", "rot_days": 5,  "probability": 50},
    {"name": "Multi-stakeholder",  "position": 5,  "color": "#ff6b00", "rot_days": 7,  "probability": 60},
    {"name": "Договор / пилот",    "position": 6,  "color": "#ff3b30", "rot_days": 5,  "probability": 75},
    {"name": "Производство",       "position": 7,  "color": "#ff2d55", "rot_days": 10, "probability": 85},
    {"name": "Пилот",              "position": 8,  "color": "#34c759", "rot_days": 14, "probability": 90},
    {"name": "Scale / серия",      "position": 9,  "color": "#30d158", "rot_days": 14, "probability": 95},
    {"name": "Закрыто (won)",      "position": 10, "color": "#32d74b", "rot_days": 0,  "probability": 100, "is_won": True},
    {"name": "Закрыто (lost)",     "position": 11, "color": "#ff3b30", "rot_days": 0,  "probability": 0,   "is_lost": True},
]

DEFAULT_GATE_CRITERIA: dict[int, list[str]] = {
    1: ["ICP соответствие подтверждено", "ЛПР идентифицирован", "Сегмент и тип сделки определены", "Приоритет A/B/C/D присвоен"],
    2: ["Проведён discovery-звонок (≥30 мин)", "Боль/потребность зафиксирована", "Бюджет предварительно обсуждён"],
    3: ["Solution fit подтверждён", "Pilot feasibility оценена", "Технический покупатель вовлечён"],
    4: ["КП отправлено", "ROI-расчёт согласован", "Следующий шаг назначен с датой"],
    5: ["Экономический покупатель идентифицирован", "Все стейкхолдеры вовлечены", "Внутренний чемпион активен"],
    6: ["Договор отправлен", "Юридическое согласование начато", "Пилот-план согласован"],
    7: ["Договор подписан", "Производство запущено", "Pilot Success Contract заполнен"],
    8: ["Оборудование доставлено", "Установка подтверждена", "Пилотные цели зафиксированы"],
    9: ["Пилот завершён", "KPI зафиксированы", "Решение о масштабировании принято"],
    10: [],
}
