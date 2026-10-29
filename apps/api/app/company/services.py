"""Company overview orchestration — assembles the CEO /today payload."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.company import repositories as repo
from app.presence import repositories as presence_repo
from app.team import repositories as team_repo

VALID_PERIODS = ("week", "month")
MANAGER_PERIODS = ("day", "week", "month")
NO_SOURCE_LABEL = "Без источника"

_PERIOD_DAYS = {"day": 0, "week": 6, "month": 29}


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _period_start(period: str, *, valid: tuple[str, ...] = VALID_PERIODS) -> datetime:
    if period not in valid:
        raise ValueError(f"invalid period: {period}")
    start_of_today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days = _PERIOD_DAYS[period]
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


INFLOW_DAYS = 62  # two 30-day windows (current vs previous) plus today
INFLOW_MONTHS = 12
DEFAULT_TZ = "Europe/Moscow"


def _tz(name: str | None) -> str:
    try:
        ZoneInfo(name or DEFAULT_TZ)
        return name or DEFAULT_TZ
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TZ


def _month_start(d: date, back: int) -> date:
    """First day of the month `back` months before `d`'s month."""
    idx = d.year * 12 + (d.month - 1) - back
    return date(idx // 12, idx % 12 + 1, 1)


async def inflow(db: AsyncSession, *, workspace_id: uuid.UUID, tz: str | None) -> dict:
    """New leads by local day (last 62 days) and month (last 12), per source.

    One honest definition for the whole block: every new (non-archived) lead,
    labelled by where it came from. Hand-typed leads and file loads share the
    «Вручную и загрузка базы» label — the UI lets you hide it, since a base
    load spikes a single day.
    """
    zone_name = _tz(tz)
    zone = ZoneInfo(zone_name)
    today = datetime.now(zone).date()
    day_from = datetime.combine(today - timedelta(days=INFLOW_DAYS - 1), datetime.min.time(), zone)
    month_from = datetime.combine(
        _month_start(today, INFLOW_MONTHS - 1), datetime.min.time(), zone
    )

    days = await repo.inflow_points(db, workspace_id=workspace_id, from_=day_from, unit="day", tz=zone_name)
    months = await repo.inflow_points(
        db, workspace_id=workspace_id, from_=month_from, unit="month", tz=zone_name
    )

    totals: dict[str, dict] = {}
    for p in months:
        name = p["label"] or repo.MANUAL_SOURCE_LABEL
        t = totals.setdefault(
            name, {"name": name, "is_paid": False, "is_manual": p["label"] is None, "total": 0}
        )
        t["total"] += p["count"]
        t["is_paid"] = t["is_paid"] or p["is_paid"]
    # Biggest real sources first; the manual bucket always last.
    sources = sorted(totals.values(), key=lambda t: (t["is_manual"], -t["total"], t["name"]))

    def points(rows: list[dict]) -> list[dict]:
        return [
            {"bucket": p["bucket"], "source": p["label"] or repo.MANUAL_SOURCE_LABEL, "count": p["count"]}
            for p in rows
        ]

    return {
        "timezone": zone_name,
        "today": today,
        "days": points(days),
        "months": points(months),
        "sources": sources,
        "reaction": await _reaction(db, workspace_id=workspace_id),
    }


REACTION_WINDOW_DAYS = 30
REACTION_WAITING_PREVIEW = 5


def _hours(delta: timedelta) -> float:
    return round(delta.total_seconds() / 3600, 1)


async def _reaction(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    """Time to the first touch on incoming leads: last 30 days vs the 30 before,
    plus the incoming leads of the last 30 days nobody has touched yet."""
    now = datetime.now(timezone.utc)
    cur_from = now - timedelta(days=REACTION_WINDOW_DAYS)
    prev_from = cur_from - timedelta(days=REACTION_WINDOW_DAYS)
    rows = await repo.inbound_reaction(db, workspace_id=workspace_id, from_=prev_from)

    def window(lo: datetime, hi: datetime) -> dict:
        leads = [r for r in rows if lo <= r["created_at"] < hi]
        waits = [_hours(r["first_touch"] - r["created_at"]) for r in leads if r["first_touch"]]
        return {
            "total": len(leads),
            "touched": len(waits),
            "median_hours": round(median(waits), 1) if waits else None,
            "within_hour": sum(1 for w in waits if w <= 1),
        }

    waiting = sorted(
        (r for r in rows if r["created_at"] >= cur_from and r["first_touch"] is None),
        key=lambda r: r["created_at"],
    )
    return {
        "current": window(cur_from, now),
        "previous": window(prev_from, cur_from),
        "waiting_count": len(waiting),
        "waiting": [
            {
                "lead_id": r["lead_id"],
                "company_name": r["company_name"],
                "source": r["label"],
                "hours": _hours(now - r["created_at"]),
            }
            for r in waiting[:REACTION_WAITING_PREVIEW]
        ],
    }


async def attention(db: AsyncSession, *, workspace_id: uuid.UUID) -> dict:
    stuck = await repo.stuck_leads(db, workspace_id=workspace_id)
    managers = await repo.manager_load(db, workspace_id=workspace_id)
    oldest_days_idle = max((s["days_idle"] for s in stuck), default=0)
    return {"stuck": stuck, "managers": managers, "oldest_days_idle": oldest_days_idle}


async def managers(db: AsyncSession, *, workspace_id: uuid.UUID, period: str) -> dict:
    """Per-manager work + result metrics for the CEO/head dashboard."""
    from_ = _period_start(period, valid=MANAGER_PERIODS)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_from = today_start - timedelta(days=13)

    roster = await repo.manager_roster(db, workspace_id=workspace_id)
    if not roster:
        return {
            "period": period,
            "totals": {
                "active_minutes": 0,
                "new_leads": 0,
                "actions": 0,
                "kp_sent": 0,
                "stuck": 0,
            },
            "alerts": [],
            "managers": [],
        }

    user_ids = [r["user_id"] for r in roster]

    active_minutes = await presence_repo.active_minutes_range(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=now
    )
    new_leads = await repo.new_leads_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=now
    )
    actions = await repo.actions_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=now
    )
    kp_sent = await team_repo.kp_sent_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=now
    )
    stage_moves = await team_repo.leads_moved_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=now
    )
    tasks_done = await team_repo.tasks_completed_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=now
    )
    tasks_overdue = await repo.tasks_overdue_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids
    )
    portfolio = await repo.portfolio_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids
    )
    last_active = await team_repo.last_active_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids
    )
    has_leads = await repo.workspace_has_leads(db, workspace_id=workspace_id)

    empty_portfolio = {"in_work": 0, "stuck": 0, "oldest_stuck_days": 0}
    managers_out: list[dict] = []
    alerts: list[dict] = []

    for r in roster:
        uid = r["user_id"]
        port = portfolio.get(uid, empty_portfolio)
        mins = active_minutes.get(uid, 0)
        nl = new_leads.get(uid, 0)
        act = actions.get(uid, 0)
        kp = kp_sent.get(uid, 0)
        # «Был активен» — про присутствие в CRM, а не про работу с лидами,
        # поэтому берём самый свежий сигнал, а не первый непустой. Раньше тут
        # стоял `or`: любое действие по лиду полностью перекрывало дату входа,
        # и менеджер, который сидит в CRM каждый день, но давно не трогал
        # лидов, попадал в алерт «не заходил N дней». last_login_at обновляется
        # на каждом запросе, включая пинг трекера активного времени, — он и
        # есть самая надёжная отметка присутствия.
        seen = [t for t in (last_active.get(uid), r["last_login_at"]) if t is not None]
        last_active_at = max(seen) if seen else None
        active_daily = await presence_repo.active_daily(
            db, workspace_id=workspace_id, user_id=uid, from_=daily_from, to=now
        )
        managers_out.append({
            "user_id": uid,
            "name": r["name"],
            "role": r["role"],
            "active_minutes": mins,
            "active_daily": active_daily,
            "new_leads": nl,
            "actions": act,
            "kp_sent": kp,
            "stage_moves": stage_moves.get(uid, 0),
            "tasks_done": tasks_done.get(uid, 0),
            "tasks_overdue": tasks_overdue.get(uid, 0),
            "in_work": port["in_work"],
            "stuck": port["stuck"],
            "oldest_stuck_days": port["oldest_stuck_days"],
            "last_active_at": last_active_at,
        })

        stuck_n = port["stuck"]
        if stuck_n > 0:
            alerts.append({
                "type": "stuck",
                "user_id": uid,
                "name": r["name"],
                "count": stuck_n,
            })
        silent = last_active_at is None or (now - last_active_at) >= timedelta(hours=48)
        if silent and has_leads:
            if last_active_at is None:
                days = 0
            else:
                days = int((now - last_active_at).total_seconds() // 3600) // 24
            alerts.append({
                "type": "silent",
                "user_id": uid,
                "name": r["name"],
                "days": days,
            })

    managers_out.sort(key=lambda m: (-m["active_minutes"], m["name"]))

    totals = {
        "active_minutes": sum(m["active_minutes"] for m in managers_out),
        "new_leads": sum(m["new_leads"] for m in managers_out),
        "actions": sum(m["actions"] for m in managers_out),
        "kp_sent": sum(m["kp_sent"] for m in managers_out),
        "stuck": sum(m["stuck"] for m in managers_out),
    }
    return {
        "period": period,
        "totals": totals,
        "alerts": alerts,
        "managers": managers_out,
    }
