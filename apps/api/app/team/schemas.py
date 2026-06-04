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


# ---------------------------------------------------------------------------
# Manager workload (T2)
# ---------------------------------------------------------------------------

class WorkloadStageOut(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    color: str


class WorkloadCellOut(BaseModel):
    count: int
    sum_amount: float


class WorkloadManagerOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    by_stage: dict[str, WorkloadCellOut]
    open_count: int
    pipeline_sum: float
    stuck_count: int


class WorkloadOut(BaseModel):
    stages: list[WorkloadStageOut]
    managers: list[WorkloadManagerOut]


# ---------------------------------------------------------------------------
# Manager deal portfolio (deal analytics)
# ---------------------------------------------------------------------------

class PortfolioKpiOut(BaseModel):
    active_count: int
    total_amount: float
    total_quantity: int
    avg_amount: float | None = None
    new_7d: int
    new_30d: int
    at_risk_count: int
    at_risk_amount: float


class PortfolioSegmentOut(BaseModel):
    segment: str
    count: int
    amount: float
    quantity: int


class PortfolioStageOut(BaseModel):
    stage_id: str
    stage_name: str
    position: int
    count: int
    amount: float


class PortfolioPriorityOut(BaseModel):
    priority: str
    label: str
    count: int
    amount: float


class PortfolioTopDealOut(BaseModel):
    lead_id: str
    company_name: str
    segment: str | None = None
    amount: float


class ManagerPortfolioOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    kpi: PortfolioKpiOut
    by_segment: list[PortfolioSegmentOut]
    by_stage: list[PortfolioStageOut]
    by_priority: list[PortfolioPriorityOut]
    top_deals: list[PortfolioTopDealOut]
