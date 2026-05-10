"""Automation Builder data access — Sprint 2.5 G1, multi-step Sprint 2.7 G2."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation_builder.models import (
    Automation,
    AutomationRun,
    AutomationStepRun,
)


async def list_for_workspace(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[Automation]:
    """All automations in the workspace, ordered by `is_active` first
    (active rules float to the top of the admin list) then `created_at`
    desc — newest are typically the ones an admin is iterating on."""
    res = await db.execute(
        select(Automation)
        .where(Automation.workspace_id == workspace_id)
        .order_by(
            Automation.is_active.desc(), Automation.created_at.desc()
        )
    )
    return list(res.scalars().all())


async def list_active_for_trigger(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    trigger: str,
) -> list[Automation]:
    """The hot-path read used by the trigger fan-out. Hits the
    composite index (workspace_id, trigger, is_active) — the entire
    point of having that index."""
    res = await db.execute(
        select(Automation).where(
            Automation.workspace_id == workspace_id,
            Automation.trigger == trigger,
            Automation.is_active.is_(True),
        )
    )
    return list(res.scalars().all())


async def get_by_id(
    db: AsyncSession,
    *,
    automation_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Automation | None:
    res = await db.execute(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.workspace_id == workspace_id,
        )
    )
    return res.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID | None,
    name: str,
    trigger: str,
    trigger_config_json: dict | None,
    condition_json: dict | None,
    action_type: str,
    action_config_json: dict,
    is_active: bool,
    steps_json: list[dict] | None = None,
) -> Automation:
    row = Automation(
        workspace_id=workspace_id,
        created_by=created_by,
        name=name,
        trigger=trigger,
        trigger_config_json=trigger_config_json,
        condition_json=condition_json,
        action_type=action_type,
        action_config_json=action_config_json,
        steps_json=steps_json,
        is_active=is_active,
    )
    db.add(row)
    await db.flush()
    return row


async def update(
    db: AsyncSession,
    *,
    automation: Automation,
    name: str | None = None,
    trigger: str | None = None,
    trigger_config_json: dict | None = None,
    trigger_config_set: bool = False,
    condition_json: dict | None = None,
    condition_set: bool = False,
    action_type: str | None = None,
    action_config_json: dict | None = None,
    steps_json: list[dict] | None = None,
    steps_set: bool = False,
    is_active: bool | None = None,
) -> Automation:
    """In-place update. None = leave field as-is. The `*_set` flags
    cover the JSON columns where the caller may want to explicitly
    clear (set to None)."""
    if name is not None:
        automation.name = name
    if trigger is not None:
        automation.trigger = trigger
    if trigger_config_set:
        automation.trigger_config_json = trigger_config_json
    if condition_set:
        automation.condition_json = condition_json
    if action_type is not None:
        automation.action_type = action_type
    if action_config_json is not None:
        automation.action_config_json = action_config_json
    if steps_set:
        automation.steps_json = steps_json
    if is_active is not None:
        automation.is_active = is_active
    await db.flush()
    return automation


async def delete(
    db: AsyncSession, *, automation: Automation
) -> None:
    """Hard-delete. Run history goes with it via FK CASCADE — caller
    should soft-disable via `is_active=False` when audit trail
    matters."""
    await db.delete(automation)
    await db.flush()


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

async def create_run(
    db: AsyncSession,
    *,
    automation_id: uuid.UUID,
    lead_id: uuid.UUID | None,
    status: str,
    error: str | None = None,
) -> AutomationRun:
    row = AutomationRun(
        automation_id=automation_id,
        lead_id=lead_id,
        status=status,
        error=error[:500] if error else None,
    )
    db.add(row)
    await db.flush()
    return row


async def list_runs_for_automation(
    db: AsyncSession,
    *,
    automation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 50,
) -> list[AutomationRun]:
    """Recent runs newest-first. Workspace-scoped through the
    automation join — defends against id-guessing across workspaces."""
    res = await db.execute(
        select(AutomationRun)
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .where(
            AutomationRun.automation_id == automation_id,
            Automation.workspace_id == workspace_id,
        )
        .order_by(AutomationRun.executed_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Step-run access — Sprint 2.7 G2
# ---------------------------------------------------------------------------

async def create_step_run(
    db: AsyncSession,
    *,
    automation_run_id: uuid.UUID,
    lead_id: uuid.UUID | None,
    step_index: int,
    step_json: dict,
    scheduled_at: datetime,
    executed_at: datetime | None,
    status: str,
    error: str | None = None,
) -> AutomationStepRun:
    row = AutomationStepRun(
        automation_run_id=automation_run_id,
        lead_id=lead_id,
        step_index=step_index,
        step_json=step_json,
        scheduled_at=scheduled_at,
        executed_at=executed_at,
        status=status,
        error=error[:500] if error else None,
    )
    db.add(row)
    await db.flush()
    return row


async def list_step_runs_for_run(
    db: AsyncSession,
    *,
    automation_run_id: uuid.UUID,
) -> list[AutomationStepRun]:
    """Per-step grid for the RunsDrawer — ordered by step_index."""
    res = await db.execute(
        select(AutomationStepRun)
        .where(AutomationStepRun.automation_run_id == automation_run_id)
        .order_by(AutomationStepRun.step_index.asc())
    )
    return list(res.scalars().all())


async def list_due_step_runs(
    db: AsyncSession, *, now: datetime, limit: int = 200
) -> list[AutomationStepRun]:
    """Beat-scheduler picker. Returns step rows whose scheduled time
    is in the past and which haven't fired yet. Bounded by `limit`
    so a single tick can't run away with the worker — leftovers
    catch up on the next tick."""
    res = await db.execute(
        select(AutomationStepRun)
        .where(
            AutomationStepRun.executed_at.is_(None),
            AutomationStepRun.scheduled_at <= now,
        )
        .order_by(AutomationStepRun.scheduled_at.asc())
        .limit(limit)
    )
    return list(res.scalars().all())
