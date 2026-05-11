"""Team stats response schemas — Sprint 3.4 G1."""
from __future__ import annotations

import uuid
from datetime import datetime, date

from pydantic import BaseModel, ConfigDict, Field


class TeamStatsCounts(BaseModel):
    kp_sent: int
    leads_taken_from_pool: int
    leads_moved: int
    tasks_completed: int


class TeamStatsManagerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    name: str
    email: str
    avatar_url: str | None = None
    role: str
    stats: TeamStatsCounts
    last_active_at: datetime | None = None


class TeamStatsOut(BaseModel):
    period: str
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    managers: list[TeamStatsManagerOut]

    model_config = ConfigDict(populate_by_name=True)


class TeamStatsDailyRow(BaseModel):
    date: date
    kp_sent: int
    leads_taken_from_pool: int
    leads_moved: int
    tasks_completed: int


class ManagerStatsOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    period: str
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    stats: TeamStatsCounts
    daily: list[TeamStatsDailyRow]

    model_config = ConfigDict(populate_by_name=True)
