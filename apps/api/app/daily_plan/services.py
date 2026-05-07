"""Daily plan generator service — Sprint 1.4.

generate_for_user() is synchronous-callable (no Celery in Phase 1).
Celery wrapping is Phase 2.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.auth.models import User
from app.daily_plan.models import DailyPlan, DailyPlanItem
from app.daily_plan.priority_scorer import score_lead
from app.daily_plan.schemas import ScoredItem
from app.enrichment.budget import add_to_daily_spend
from app.enrichment.profile import render_profile_for_prompt
from app.enrichment.providers.base import LLMError, TaskType
from app.enrichment.providers.factory import complete_with_fallback
from app.leads.models import Lead
from app.pipelines.models import Stage

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

_DEFAULT_BUDGET_MINUTES = 360  # 6 hours fallback
_MINUTES_PER_ITEM = 15
_TIME_BLOCKS = ["morning", "midday", "afternoon"]

# System prompt suffix for hint generation
_HINT_SYSTEM_SUFFIX = (
    "Ты пишешь однострочную подсказку для менеджера: что сделать с этим лидом сегодня. "
    "Не больше 80 символов. Без emoji. Без преамбулы."
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _work_hours_minutes(working_hours_json: dict, plan_date: date) -> int:
    """Return total working minutes for plan_date from user's working_hours_json.

    Expected shape: {"mon": {"start": "09:00", "end": "18:00"}, ...}
    Day keys: mon, tue, wed, thu, fri, sat, sun.
    Falls back to _DEFAULT_BUDGET_MINUTES if shape is unknown or day is off.
    """
    if not working_hours_json:
        return _DEFAULT_BUDGET_MINUTES

    day_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
    day_key = day_map.get(plan_date.weekday(), "")
    day_conf = working_hours_json.get(day_key, {})
    if not isinstance(day_conf, dict):
        return _DEFAULT_BUDGET_MINUTES

    start_str = day_conf.get("start", "")
    end_str = day_conf.get("end", "")
    if not start_str or not end_str:
        return _DEFAULT_BUDGET_MINUTES

    try:
        sh, sm = (int(x) for x in start_str.split(":"))
        eh, em = (int(x) for x in end_str.split(":"))
        total = (eh * 60 + em) - (sh * 60 + sm)
        return total if total > 0 else _DEFAULT_BUDGET_MINUTES
    except (ValueError, AttributeError):
        return _DEFAULT_BUDGET_MINUTES


def _split_into_time_blocks(items: list[ScoredItem]) -> list[tuple[ScoredItem, str]]:
    """Assign each item a time_block by splitting evenly into thirds."""
    n = len(items)
    if n == 0:
        return []
    third = max(1, (n + 2) // 3)
    result: list[tuple[ScoredItem, str]] = []
    for i, item in enumerate(items):
        block_idx = min(i // third, len(_TIME_BLOCKS) - 1)
        result.append((item, _TIME_BLOCKS[block_idx]))
    return result


def _classify_task_kind(lead: Lead) -> str:
    """Heuristic task_kind from lead state."""
    next_step = (lead.next_step or "").lower()
    if "встреча" in next_step or "meeting" in next_step:
        return "meeting"
    # Default: call
    return "call"


def _build_user_hint_prompt(lead: Lead) -> str:
    """Short user prompt for the LLM hint call."""
    ai_data = lead.ai_data or {}
    profile_snippet = ai_data.get("company_profile", "")
    next_steps = ai_data.get("next_steps", [])
    next_step_hint = next_steps[0] if next_steps else (lead.next_step or "")

    parts = [
        f"Компания: {lead.company_name or '—'}",
        f"Сегмент: {lead.segment or '—'}",
        f"Город: {lead.city or '—'}",
    ]
    if profile_snippet:
        parts.append(f"Профиль: {profile_snippet[:200]}")
    if next_step_hint:
        parts.append(f"Следующий шаг: {next_step_hint[:120]}")
    if lead.next_action_at:
        parts.append(f"Дедлайн: {lead.next_action_at.strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)


def _compose_summary(items_picked: list[ScoredItem]) -> dict:
    """Build summary_json: {total_minutes, count, urgency_breakdown}."""
    total_minutes = sum(i.estimated_minutes for i in items_picked)
    urgency_breakdown: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for item in items_picked:
        ai_data = item.lead.ai_data or {}
        urgency = ai_data.get("urgency", "medium")
        if urgency not in urgency_breakdown:
            urgency = "medium"
        urgency_breakdown[urgency] += 1
    return {
        "total_minutes": total_minutes,
        "count": len(items_picked),
        "urgency_breakdown": urgency_breakdown,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_for_user(
    db: AsyncSession,
    *,
    user: User,
    plan_date: date,
) -> DailyPlan:
    """Generate (or replace) a DailyPlan for one user/date. Idempotent.

    Never raises — failures are written to the DailyPlan row (status='failed').
    """
    bound_log = log.bind(
        user_id=str(user.id),
        workspace_id=str(user.workspace_id),
        plan_date=str(plan_date),
    )
    bound_log.info("daily_plan.generate.start")

    # Upsert: delete any previous plan for this (user, date) pair first.
    await db.execute(
        delete(DailyPlan).where(
            DailyPlan.user_id == user.id,
            DailyPlan.plan_date == plan_date,
        )
    )

    plan = DailyPlan(
        workspace_id=user.workspace_id,
        user_id=user.id,
        plan_date=plan_date,
        status="generating",
    )
    db.add(plan)
    await db.flush()  # populate plan.id

    try:
        now = datetime.now(tz=timezone.utc)

        # Step 1 — Load assigned leads with their stages
        leads_result = await db.execute(
            select(Lead, Stage)
            .outerjoin(Stage, Lead.stage_id == Stage.id)
            .where(
                Lead.assigned_to == user.id,
                Lead.assignment_status == "assigned",
            )
        )
        rows = leads_result.all()
        bound_log.info("daily_plan.leads_loaded", count=len(rows))

        # Step 2 — Score and sort
        scored: list[ScoredItem] = []
        for lead, stage in rows:
            s = score_lead(lead, stage, now)
            scored.append(ScoredItem(lead=lead, stage=stage, priority_score=s))
        scored.sort(key=lambda x: x.priority_score, reverse=True)

        # Step 3 — Resolve work hour budget
        budget_minutes = _work_hours_minutes(
            user.working_hours_json or {}, plan_date
        )

        # Step 4 — Pack items into budget (greedy, 15 min each)
        packed: list[ScoredItem] = []
        minutes_used = 0
        for item in scored:
            if minutes_used + item.estimated_minutes > budget_minutes:
                break
            packed.append(item)
            minutes_used += item.estimated_minutes

        bound_log.info(
            "daily_plan.packed",
            packed=len(packed),
            budget_minutes=budget_minutes,
        )

        # Step 5 — Build items with LLM hints
        profile_block = render_profile_for_prompt()
        system_prompt = "\n\n".join(filter(None, [profile_block, _HINT_SYSTEM_SUFFIX]))
        total_cost_usd = 0.0

        items_with_blocks = _split_into_time_blocks(packed)
        orm_items: list[DailyPlanItem] = []

        for position, (scored_item, time_block) in enumerate(items_with_blocks):
            lead = scored_item.lead
            hint = ""
            try:
                user_prompt = _build_user_hint_prompt(lead)
                completion = await complete_with_fallback(
                    system=system_prompt,
                    user=user_prompt,
                    task_type=TaskType.daily_plan,
                    max_tokens=120,
                    temperature=0.3,
                )
                hint = completion.text.strip()[:80]
                total_cost_usd += completion.cost_usd
            except LLMError as exc:
                bound_log.warning(
                    "daily_plan.hint_fallback",
                    lead_id=str(lead.id),
                    error=str(exc)[:200],
                )
                # Deterministic fallback hint
                next_step = (lead.next_step or "двигаемся по этапу")[:60]
                hint = f"Связаться с {lead.company_name or '—'} — {next_step}"[:80]

            task_kind = _classify_task_kind(lead)

            orm_items.append(
                DailyPlanItem(
                    daily_plan_id=plan.id,
                    lead_id=lead.id,
                    position=position,
                    priority_score=scored_item.priority_score,
                    estimated_minutes=scored_item.estimated_minutes,
                    time_block=time_block,
                    task_kind=task_kind,
                    hint_one_liner=hint,
                    done=False,
                )
            )

        for orm_item in orm_items:
            db.add(orm_item)

        # Step 6 — Compose summary
        plan.summary_json = _compose_summary(packed)
        plan.generated_at = datetime.now(tz=timezone.utc)
        plan.status = "ready"

        await db.commit()

        # Step 7 — Roll up LLM cost to daily budget guard (best-effort)
        if total_cost_usd > 0:
            await add_to_daily_spend(user.workspace_id, total_cost_usd)

        bound_log.info(
            "daily_plan.generate.done",
            items=len(orm_items),
            cost_usd=round(total_cost_usd, 5),
        )

    except Exception as exc:
        error_type = type(exc).__name__
        bound_log.error(
            "daily_plan.generate.failed",
            error_type=error_type,
            error=str(exc)[:500],
        )
        try:
            plan.status = "failed"
            plan.generation_error = f"{error_type}: {exc}"[:1000]
            await db.commit()
        except Exception as commit_exc:
            bound_log.error(
                "daily_plan.commit_failed", error=str(commit_exc)[:200]
            )

    return plan


# ---------------------------------------------------------------------------
# Read-side service functions (Phase 3)
# ---------------------------------------------------------------------------

async def get_plan_for_user_date(
    db: AsyncSession,
    *,
    user_id: UUID,
    plan_date: date,
) -> DailyPlan | None:
    """Fetch plan + items + lead joins for one user/date."""
    result = await db.execute(
        select(DailyPlan)
        .where(DailyPlan.user_id == user_id, DailyPlan.plan_date == plan_date)
        .options(
            selectinload(DailyPlan.items).joinedload(DailyPlanItem.lead)
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        return None
    # Populate joined fields on each item (ORM doesn't map them as columns)
    for item in plan.items:
        if item.lead is not None:
            item.lead_company_name = item.lead.company_name  # type: ignore[attr-defined]
            item.lead_segment = item.lead.segment  # type: ignore[attr-defined]
            item.lead_city = item.lead.city  # type: ignore[attr-defined]
        else:
            item.lead_company_name = None  # type: ignore[attr-defined]
            item.lead_segment = None  # type: ignore[attr-defined]
            item.lead_city = None  # type: ignore[attr-defined]
    return plan


async def get_today_plan_for_user(
    db: AsyncSession,
    *,
    user: User,
) -> DailyPlan | None:
    """Convenience: today in user's timezone."""
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(user.timezone or "Europe/Moscow")
    except Exception:
        from datetime import timezone as _tz
        tz = _tz.utc  # type: ignore[assignment]
    today = datetime.now(tz=tz).date()
    return await get_plan_for_user_date(db, user_id=user.id, plan_date=today)


async def list_plans_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    limit: int = 30,
) -> list[DailyPlan]:
    """History — last N plans, ordered by plan_date DESC."""
    from sqlalchemy import desc
    result = await db.execute(
        select(DailyPlan)
        .where(DailyPlan.user_id == user_id)
        .order_by(desc(DailyPlan.plan_date))
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_item_done(
    db: AsyncSession,
    *,
    item_id: UUID,
    user_id: UUID,
) -> DailyPlanItem | None:
    """Set done=True, done_at=now. Returns None if item belongs to a
    different user (prevents cross-user mutation)."""
    result = await db.execute(
        select(DailyPlanItem)
        .join(DailyPlan, DailyPlanItem.daily_plan_id == DailyPlan.id)
        .where(
            DailyPlanItem.id == item_id,
            DailyPlan.user_id == user_id,
        )
        .options(joinedload(DailyPlanItem.lead))
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    item.done = True
    item.done_at = datetime.now(tz=timezone.utc)
    await db.flush()
    # Populate joined fields
    if item.lead is not None:
        item.lead_company_name = item.lead.company_name  # type: ignore[attr-defined]
        item.lead_segment = item.lead.segment  # type: ignore[attr-defined]
        item.lead_city = item.lead.city  # type: ignore[attr-defined]
    else:
        item.lead_company_name = None  # type: ignore[attr-defined]
        item.lead_segment = None  # type: ignore[attr-defined]
        item.lead_city = None  # type: ignore[attr-defined]
    return item


async def request_regenerate(
    db: AsyncSession,
    *,
    user: User,
    plan_date: date,
) -> tuple[DailyPlan, str | None]:
    """Mark the plan row 'generating' and dispatch a Celery task that
    replaces it. Returns (plan_row, celery_task_id)."""
    from app.scheduled.celery_app import celery_app

    # Look up or create the plan row
    result = await db.execute(
        select(DailyPlan).where(
            DailyPlan.user_id == user.id,
            DailyPlan.plan_date == plan_date,
        )
    )
    plan = result.scalar_one_or_none()

    if plan is not None:
        plan.status = "generating"
        plan.generation_error = None
    else:
        plan = DailyPlan(
            workspace_id=user.workspace_id,
            user_id=user.id,
            plan_date=plan_date,
            status="generating",
            summary_json={},
        )
        db.add(plan)

    await db.flush()
    await db.commit()

    # Dispatch the Celery task
    async_result = celery_app.send_task(
        "app.scheduled.jobs.regenerate_for_user",
        args=[str(user.id), plan_date.isoformat()],
    )
    task_id: str | None = None
    try:
        task_id = async_result.id
    except Exception:
        pass

    return plan, task_id
