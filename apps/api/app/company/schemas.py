"""Pydantic schemas for the company overview (CEO /today)."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class SourceBreakdown(BaseModel):
    source_id: uuid.UUID | None
    name: str  # «Без источника» for null
    is_paid: bool
    leads: int
    qualified: int
    conversion_pct: float  # qualified / leads * 100, 0 when leads == 0


class DailyPoint(BaseModel):
    date: date
    source_id: uuid.UUID | None
    count: int


class CompanySummaryOut(BaseModel):
    period: str
    leads_today: int
    leads_yesterday: int
    leads_7d: int
    avg_per_day_7d: float
    stuck_count: int
    ad_conversion_pct: float | None  # over paid sources in the period; None if no paid leads
    sources: list[SourceBreakdown]
    daily: list[DailyPoint]  # last 14 days, per source


class StuckLead(BaseModel):
    lead_id: uuid.UUID
    company_name: str
    source_name: str | None
    manager_name: str | None
    days_idle: int


class ManagerLoad(BaseModel):
    user_id: uuid.UUID
    name: str
    in_work: int
    new_week: int
    stuck: int


class CompanyAttentionOut(BaseModel):
    stuck: list[StuckLead]
    managers: list[ManagerLoad]
