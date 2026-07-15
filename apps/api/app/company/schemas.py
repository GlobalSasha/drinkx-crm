"""Pydantic schemas for the company overview (CEO /today)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class SourceBreakdown(BaseModel):
    source_id: uuid.UUID | None
    name: str  # «Без источника» for null
    is_paid: bool
    leads: int
    qualified: int
    conversion_pct: float  # qualified / leads * 100, 0 when leads == 0
    prev_leads: int  # leads in the prior comparable period — powers the WoW arrow


class DailyPoint(BaseModel):
    date: date
    source_id: uuid.UUID | None
    count: int


class CompanySummaryOut(BaseModel):
    period: str
    leads_today: int
    leads_yesterday: int
    leads_7d: int
    leads_7d_prior: int  # the 7 days before the trailing week — week-over-week delta
    avg_per_day_7d: float
    stuck_count: int
    ad_conversion_pct: float | None  # over paid sources in the period; None if no paid leads
    ad_conversion_pct_prior: float | None  # same metric over the prior comparable period
    sources: list[SourceBreakdown]
    daily: list[DailyPoint]  # last 14 days, per source


class StuckLead(BaseModel):
    lead_id: uuid.UUID
    company_name: str
    source_name: str | None
    manager_name: str | None
    stage_name: str | None  # stage the lead is stuck on — the "why" hint
    days_idle: int


class ManagerLoad(BaseModel):
    user_id: uuid.UUID
    name: str
    max_active_deals: int | None  # capacity ceiling → load% zones; None falls back to stuck>0
    in_work: int
    new_week: int
    stuck: int


class CompanyAttentionOut(BaseModel):
    stuck: list[StuckLead]
    managers: list[ManagerLoad]
    oldest_days_idle: int  # MAX(days_idle) across stuck leads, 0 when none


class ManagerAlert(BaseModel):
    type: str  # "silent" | "stuck"
    user_id: uuid.UUID
    name: str
    days: int | None = None
    count: int | None = None


class ManagerDailyPoint(BaseModel):
    date: date
    minutes: int


class ManagerRow(BaseModel):
    user_id: uuid.UUID
    name: str
    role: str
    active_minutes: int
    active_daily: list[ManagerDailyPoint]
    new_leads: int
    actions: int
    kp_sent: int
    stage_moves: int
    tasks_done: int
    tasks_overdue: int
    in_work: int
    stuck: int
    oldest_stuck_days: int
    last_active_at: datetime | None


class ManagerTotals(BaseModel):
    active_minutes: int
    new_leads: int
    actions: int
    kp_sent: int
    stuck: int


class CompanyManagersOut(BaseModel):
    period: str
    totals: ManagerTotals
    alerts: list[ManagerAlert]
    managers: list[ManagerRow]
