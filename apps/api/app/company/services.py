"""Company overview orchestration — assembles the CEO /today payload."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.company import repositories as repo

VALID_PERIODS = ("week", "month")
NO_SOURCE_LABEL = "Без источника"


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _period_start(period: str) -> datetime:
    if period not in VALID_PERIODS:
        raise ValueError(f"invalid period: {period}")
    start_of_today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days = 6 if period == "week" else 29
    return start_of_today - timedelta(days=days)


async def summary(db: AsyncSession, *, workspace_id: uuid.UUID, period: str) -> dict:
    from_ = _period_start(period)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=6)
    daily_start = today_start - timedelta(days=13)

    pulse = await repo.pulse_counts(
        db, workspace_id=workspace_id,
        today_start=today_start, yesterday_start=yesterday_start, week_start=week_start,
    )
    stuck = await repo.stuck_count(db, workspace_id=workspace_id)
    raw_sources = await repo.source_breakdown(db, workspace_id=workspace_id, from_=from_)
    daily = await repo.daily_by_source(db, workspace_id=workspace_id, from_=daily_start)

    sources = [
        {
            "source_id": s["source_id"],
            "name": s["name"] or NO_SOURCE_LABEL,
            "is_paid": s["is_paid"],
            "leads": s["leads"],
            "qualified": s["qualified"],
            "conversion_pct": _pct(s["qualified"], s["leads"]),
        }
        for s in raw_sources
    ]

    paid_leads = sum(s["leads"] for s in raw_sources if s["is_paid"])
    paid_qualified = sum(s["qualified"] for s in raw_sources if s["is_paid"])
    ad_conversion_pct = _pct(paid_qualified, paid_leads) if paid_leads else None

    return {
        "period": period,
        "leads_today": pulse["today"],
        "leads_yesterday": pulse["yesterday"],
        "leads_7d": pulse["week"],
        "avg_per_day_7d": round(pulse["week"] / 7, 1),
        "stuck_count": stuck,
        "ad_conversion_pct": ad_conversion_pct,
        "sources": sources,
        "daily": daily,
    }


async def attention(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    stuck = await repo.stuck_leads(db, workspace_id=workspace_id)
    managers = await repo.manager_load(db, workspace_id=workspace_id)
    return {"stuck": stuck, "managers": managers}
