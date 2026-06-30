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


def _ad_conversion(rows: list[dict]) -> float | None:
    paid_leads = sum(s["leads"] for s in rows if s["is_paid"])
    paid_qualified = sum(s["qualified"] for s in rows if s["is_paid"])
    return _pct(paid_qualified, paid_leads) if paid_leads else None


async def summary(db: AsyncSession, *, workspace_id: uuid.UUID, period: str) -> dict:
    from_ = _period_start(period)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=6)
    prior_week_start = week_start - timedelta(days=7)
    daily_start = today_start - timedelta(days=13)
    # Prior comparable window for the source/conversion deltas: same length as
    # the selected period, immediately before it.
    period_days = 7 if period == "week" else 30
    prior_from = from_ - timedelta(days=period_days)

    pulse = await repo.pulse_counts(
        db, workspace_id=workspace_id,
        today_start=today_start, yesterday_start=yesterday_start,
        week_start=week_start, prior_week_start=prior_week_start,
    )
    stuck = await repo.stuck_count(db, workspace_id=workspace_id)
    raw_sources = await repo.source_breakdown(db, workspace_id=workspace_id, from_=from_)
    prior_sources = await repo.source_breakdown(
        db, workspace_id=workspace_id, from_=prior_from, to_=from_
    )
    daily = await repo.daily_by_source(db, workspace_id=workspace_id, from_=daily_start)

    prior_leads_by_source = {s["source_id"]: s["leads"] for s in prior_sources}
    sources = [
        {
            "source_id": s["source_id"],
            "name": s["name"] or NO_SOURCE_LABEL,
            "is_paid": s["is_paid"],
            "leads": s["leads"],
            "qualified": s["qualified"],
            "conversion_pct": _pct(s["qualified"], s["leads"]),
            "prev_leads": prior_leads_by_source.get(s["source_id"], 0),
        }
        for s in raw_sources
    ]

    return {
        "period": period,
        "leads_today": pulse["today"],
        "leads_yesterday": pulse["yesterday"],
        "leads_7d": pulse["week"],
        "leads_7d_prior": pulse["week_prior"],
        "avg_per_day_7d": round(pulse["week"] / 7, 1),
        "stuck_count": stuck,
        "ad_conversion_pct": _ad_conversion(raw_sources),
        "ad_conversion_pct_prior": _ad_conversion(prior_sources),
        "sources": sources,
        "daily": daily,
    }


async def attention(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    stuck = await repo.stuck_leads(db, workspace_id=workspace_id)
    managers = await repo.manager_load(db, workspace_id=workspace_id)
    oldest_days_idle = max((s["days_idle"] for s in stuck), default=0)
    return {"stuck": stuck, "managers": managers, "oldest_days_idle": oldest_days_idle}
