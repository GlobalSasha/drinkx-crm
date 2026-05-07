"""Daily email digest builder — Sprint 1.5.

Build one user's digest from three sources:
  1. Today's daily plan items (top 5)
  2. Overdue follow-ups assigned to user (limit 5)
  3. Yesterday's completed enrichment runs for user's leads (limit 5)

If all three are empty → skip (no email).
Otherwise render the HTML template via str.format() (no Jinja) and pass
to send_email().
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from html import escape
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.daily_plan.models import DailyPlan, DailyPlanItem
from app.enrichment.models import EnrichmentRun
from app.followups.models import Followup
from app.leads.models import Lead
from app.notifications.email_sender import send_email

log = structlog.get_logger()

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "daily_digest.html"

_TIME_BLOCK_LABEL = {
    "morning": "Утро",
    "midday": "День",
    "afternoon": "После обеда",
    "evening": "Вечер",
}

_PLAN_LIMIT = 5
_OVERDUE_LIMIT = 5
_BRIEFS_LIMIT = 5


def _row_html(left: str, mid: str, right: str = "") -> str:
    """One <tr> in any of the three sections — same skeleton for all."""
    right_html = (
        f'<td align="right" style="padding:8px 0;font-size:11px;color:#9b9994;'
        f'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap;">{escape(right)}</td>'
        if right else ""
    )
    return (
        f'<tr>'
        f'<td style="padding:8px 0;font-size:13px;color:#1a1a1a;font-weight:600;">{escape(left)}</td>'
        f'<td style="padding:8px 12px;font-size:12px;color:#6b6862;">{escape(mid)}</td>'
        f'{right_html}'
        f'</tr>'
    )


def _empty_html(text: str) -> str:
    return (
        f'<div style="font-size:12px;color:#9b9994;font-style:italic;'
        f'padding:6px 0;">{escape(text)}</div>'
    )


def _table_open() -> str:
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'


def _table_close() -> str:
    return "</table>"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_plan_items(rows: list[tuple[DailyPlanItem, Lead | None]]) -> str:
    if not rows:
        return _empty_html("Плана на сегодня нет.")
    lines = [_table_open()]
    for item, lead in rows[:_PLAN_LIMIT]:
        company = (lead.company_name if lead else None) or "—"
        hint = item.hint_one_liner or ""
        block = _TIME_BLOCK_LABEL.get(item.time_block or "", "")
        lines.append(_row_html(company, hint[:120], block))
    lines.append(_table_close())
    return "".join(lines)


def _render_overdue(rows: list[tuple[Followup, Lead | None]]) -> str:
    if not rows:
        return _empty_html("Просроченных задач нет.")
    lines = [_table_open()]
    for fu, lead in rows[:_OVERDUE_LIMIT]:
        company = (lead.company_name if lead else None) or "—"
        name = fu.name or ""
        due = fu.due_at.strftime("%d.%m %H:%M") if fu.due_at else ""
        lines.append(_row_html(company, name[:120], due))
    lines.append(_table_close())
    return "".join(lines)


def _render_briefs(rows: list[tuple[EnrichmentRun, Lead | None]]) -> str:
    if not rows:
        return _empty_html("Новых AI Brief за вчера нет.")
    lines = [_table_open()]
    for run, lead in rows[:_BRIEFS_LIMIT]:
        company = (lead.company_name if lead else None) or "—"
        score = ""
        if lead is not None and lead.fit_score is not None:
            try:
                score = f"fit {float(lead.fit_score):.1f}/10"
            except (TypeError, ValueError):
                score = ""
        lines.append(_row_html(company, "AI Brief готов", score))
    lines.append(_table_close())
    return "".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def build_digest_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID,  # noqa: ARG001 — kept in signature for future workspace scoping
    user_name: str,
    user_email: str,
    today: date,
) -> bool:
    """Build + send digest. Returns True if sent/stubbed, False otherwise."""
    bound_log = log.bind(user_id=str(user_id), today=str(today))

    # --- Section 1: today's plan items (joined with leads) ---
    plan_res = await session.execute(
        select(DailyPlan).where(
            DailyPlan.user_id == user_id,
            DailyPlan.plan_date == today,
        )
    )
    plan: DailyPlan | None = plan_res.scalar_one_or_none()

    plan_rows: list[tuple[DailyPlanItem, Lead | None]] = []
    if plan is not None and plan.status == "ready":
        items_res = await session.execute(
            select(DailyPlanItem, Lead)
            .outerjoin(Lead, DailyPlanItem.lead_id == Lead.id)
            .where(DailyPlanItem.daily_plan_id == plan.id)
            .order_by(DailyPlanItem.position.asc())
            .limit(_PLAN_LIMIT)
        )
        plan_rows = [(item, lead) for item, lead in items_res.all()]

    # --- Section 2: overdue follow-ups for this user ---
    now = datetime.now(timezone.utc)
    overdue_res = await session.execute(
        select(Followup, Lead)
        .join(Lead, Followup.lead_id == Lead.id)
        .where(
            Lead.assigned_to == user_id,
            Followup.due_at.is_not(None),
            Followup.due_at < now,
            Followup.status != "done",
        )
        .order_by(Followup.due_at.asc())
        .limit(_OVERDUE_LIMIT)
    )
    overdue_rows: list[tuple[Followup, Lead | None]] = list(overdue_res.all())

    # --- Section 3: enrichment runs completed yesterday for user's leads ---
    yesterday_start = datetime.combine(today - timedelta(days=1), time.min, tzinfo=timezone.utc)
    today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    briefs_res = await session.execute(
        select(EnrichmentRun, Lead)
        .join(Lead, EnrichmentRun.lead_id == Lead.id)
        .where(
            Lead.assigned_to == user_id,
            EnrichmentRun.status == "succeeded",
            EnrichmentRun.finished_at.is_not(None),
            EnrichmentRun.finished_at >= yesterday_start,
            EnrichmentRun.finished_at < today_start,
        )
        .order_by(EnrichmentRun.finished_at.desc())
        .limit(_BRIEFS_LIMIT)
    )
    briefs_rows: list[tuple[EnrichmentRun, Lead | None]] = list(briefs_res.all())

    if not plan_rows and not overdue_rows and not briefs_rows:
        bound_log.info("digest.skip_empty")
        return False

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template.format(
        date=today.strftime("%d.%m.%Y"),
        user_name=escape(user_name or user_email or "коллега"),
        plan_items_html=_render_plan_items(plan_rows),
        overdue_html=_render_overdue(overdue_rows),
        briefs_html=_render_briefs(briefs_rows),
    )

    sent = await send_email(
        to=user_email,
        subject=f"План на {today.strftime('%d.%m.%Y')} — DrinkX CRM",
        html=rendered,
    )
    bound_log.info(
        "digest.dispatched",
        sent=sent,
        plan=len(plan_rows),
        overdue=len(overdue_rows),
        briefs=len(briefs_rows),
    )
    return sent
