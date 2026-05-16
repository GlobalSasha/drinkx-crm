"""Stage-transition rule engine (ADR-003, ADR-011, ADR-012)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.contacts.models import Contact
from app.leads.models import Lead, LeadStageHistory
from app.pipelines.models import Stage

log = logging.getLogger(__name__)


@dataclass
class GateViolation:
    """One reason a transition cannot proceed.

    `hard=True` means the violation cannot be bypassed by `gate_skipped`
    (e.g., structural integrity issues like cross-pipeline moves).
    `hard=False` means a manager may force-move with `gate_skipped=True` + reason
    (e.g., missing economic buyer per ADR-012).
    """
    code: str
    message: str
    hard: bool = False


@dataclass
class TransitionContext:
    lead: Lead
    from_stage: Stage | None
    to_stage: Stage
    user_id: uuid.UUID | None
    gate_skipped: bool
    skip_reason: str | None
    violations: list[GateViolation] = field(default_factory=list)


class StageTransitionBlocked(Exception):
    """Raised when gates fail and gate_skipped is False."""
    def __init__(self, violations: list[GateViolation]) -> None:
        self.violations = violations
        super().__init__(f"Transition blocked by {len(violations)} gate(s)")


class StageTransitionInvalid(Exception):
    """Raised when transition itself is invalid (e.g., closed lead, stage not in same pipeline)."""


# A pre-check: returns list of violations for this lead+stage combo
PreCheck = Callable[[TransitionContext, AsyncSession], Awaitable[list[GateViolation]]]
# A post-action: mutates lead after the transition is committed in-memory
PostAction = Callable[[TransitionContext, AsyncSession], Awaitable[None]]


# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------

async def check_economic_buyer_for_stage_6_plus(
    ctx: TransitionContext, db: AsyncSession
) -> list[GateViolation]:
    """ADR-012: entering "Договор / пилот" or later requires an Economic Buyer contact.

    Positions are 0-indexed in DEFAULT_STAGES; "Договор / пилот" is position 6.
    Spec wording "stage>=7" treats positions as 1-indexed.
    Soft gate: skippable with `gate_skipped=True` + reason.
    """
    if ctx.to_stage.position < 6:
        return []

    result = await db.execute(
        select(Contact).where(
            Contact.lead_id == ctx.lead.id,
            Contact.role_type == "economic_buyer",
        )
    )
    if result.scalar_one_or_none() is None:
        return [GateViolation(
            code="economic_buyer_required",
            message="Economic Buyer contact required for stage 6+ (ADR-012)",
            hard=False,
        )]
    return []


async def check_pipeline_match(
    ctx: TransitionContext, db: AsyncSession
) -> list[GateViolation]:
    """to_stage must belong to the lead's pipeline. Hard gate (not skippable)."""
    if ctx.lead.pipeline_id is None:
        return []  # lead detached from pipeline — allow (no constraint)
    if ctx.to_stage.pipeline_id != ctx.lead.pipeline_id:
        return [GateViolation(
            code="stage_wrong_pipeline",
            message="Target stage belongs to a different pipeline",
            hard=True,
        )]
    return []


PRE_CHECKS: list[PreCheck] = [
    check_pipeline_match,
    check_economic_buyer_for_stage_6_plus,
]


# ---------------------------------------------------------------------------
# Post-actions
# ---------------------------------------------------------------------------

async def set_won_lost_timestamps(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Stamp won_at / lost_at when entering a terminal stage."""
    now = datetime.now(timezone.utc)
    if ctx.to_stage.is_won and ctx.lead.won_at is None:
        ctx.lead.won_at = now
    if ctx.to_stage.is_lost and ctx.lead.lost_at is None:
        ctx.lead.lost_at = now


async def log_stage_change_activity(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Append an Activity row of type=stage_change."""
    payload = {
        "from_stage_id": str(ctx.from_stage.id) if ctx.from_stage else None,
        "from_stage_name": ctx.from_stage.name if ctx.from_stage else None,
        "to_stage_id": str(ctx.to_stage.id),
        "to_stage_name": ctx.to_stage.name,
        "to_position": ctx.to_stage.position,
        "gate_skipped": ctx.gate_skipped,
        "skip_reason": ctx.skip_reason,
        "violations": [{"code": v.code, "message": v.message} for v in ctx.violations],
    }
    activity = Activity(
        lead_id=ctx.lead.id,
        user_id=ctx.user_id,
        type="stage_change",
        payload_json=payload,
        body=f"{ctx.from_stage.name if ctx.from_stage else '—'} → {ctx.to_stage.name}",
    )
    db.add(activity)


async def fan_out_automation_builder(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Sprint 2.5 G1: dispatch the user-defined Automation Builder
    rules whose trigger='stage_change' matches this transition.

    Wrapped in `safe_evaluate_trigger` — failures in any single
    automation MUST NOT roll back the parent stage move. Only logs.
    """
    # Lazy import: the Automation Builder package is loaded by main.py
    # and the alembic env, but the stage_change module is imported
    # at startup before the routers register, so circular guards are
    # cheap insurance.
    from app.automation_builder.services import safe_evaluate_trigger

    await safe_evaluate_trigger(
        db,
        workspace_id=ctx.lead.workspace_id,
        trigger="stage_change",
        lead=ctx.lead,
        payload={
            "from_stage_id": str(ctx.from_stage.id) if ctx.from_stage else None,
            "to_stage_id": str(ctx.to_stage.id),
        },
    )


async def record_stage_history(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Append-only `lead_stage_history` audit (migration 0029).

    Closes the open row for the previous stage (sets `exited_at` +
    `duration_sec`) and inserts a fresh open row for the destination.
    Wrapped in try/except so a failure here never rolls back the
    stage move — the move is already applied at this point and the
    `activities.stage_change` row is the canonical audit trail."""
    try:
        now = datetime.now(timezone.utc)
        # Close previous open row (if any).
        result = await db.execute(
            select(LeadStageHistory)
            .where(LeadStageHistory.lead_id == ctx.lead.id)
            .where(LeadStageHistory.exited_at.is_(None))
            .order_by(LeadStageHistory.entered_at.desc())
            .limit(1)
        )
        previous = result.scalar_one_or_none()
        if previous is not None:
            previous.exited_at = now
            previous.duration_sec = int(
                (now - previous.entered_at).total_seconds()
            )
        # Open row for the new stage.
        db.add(
            LeadStageHistory(
                lead_id=ctx.lead.id,
                stage_id=ctx.to_stage.id,
                entered_at=now,
            )
        )
    except Exception as exc:  # noqa: BLE001 — never block the move
        log.warning(
            "stage_change.history_write_failed lead_id=%s to_stage=%s error=%s",
            ctx.lead.id,
            ctx.to_stage.id,
            str(exc)[:200],
        )


async def trigger_lead_agent_refresh(
    ctx: TransitionContext, db: AsyncSession
) -> None:
    """Sprint 3.1 Phase E — kick the Lead AI Agent to recompute its
    background-mode banner suggestion right after a stage change.

    Fire-and-forget: the Celery task does its own session + LLM work
    in the worker process. We never block the parent stage commit on
    a broker hiccup — any exception while enqueueing is swallowed
    with a structlog warning (the agent simply doesn't refresh, the
    previous suggestion stays on the banner until the next trigger).

    No `safe_*` wrapper because `apply_async` is a Redis enqueue,
    not an LLM round-trip; the exception surface is small (broker
    down, args type error) and we want it visible without rolling
    back the move.
    """
    try:
        from app.scheduled.jobs import lead_agent_refresh_suggestion

        lead_agent_refresh_suggestion.apply_async(args=[str(ctx.lead.id)])
    except Exception as exc:  # noqa: BLE001 — broker / serialisation
        log.warning(
            "stage_change.lead_agent_refresh_enqueue_failed lead_id=%s error=%s",
            ctx.lead.id,
            str(exc)[:200],
        )


POST_ACTIONS: list[PostAction] = [
    set_won_lost_timestamps,
    log_stage_change_activity,
    record_stage_history,
    fan_out_automation_builder,
    trigger_lead_agent_refresh,
]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def move_stage(
    db: AsyncSession,
    lead: Lead,
    to_stage: Stage,
    user_id: uuid.UUID | None,
    *,
    gate_skipped: bool = False,
    skip_reason: str | None = None,
) -> Lead:
    """Move a lead to a new stage, running pre-checks and post-actions.

    If gates fail and gate_skipped=False → StageTransitionBlocked.
    If gate_skipped=True, skip_reason MUST be non-empty (raises ValueError otherwise).
    """
    if gate_skipped and not (skip_reason and skip_reason.strip()):
        raise ValueError("skip_reason is required when gate_skipped=True")

    if lead.archived_at is not None:
        raise StageTransitionInvalid("Cannot move stage on archived lead")

    # Resolve from_stage (may be None on first transition)
    from_stage: Stage | None = None
    if lead.stage_id is not None:
        from_stage_result = await db.execute(
            select(Stage).where(Stage.id == lead.stage_id)
        )
        from_stage = from_stage_result.scalar_one_or_none()

    ctx = TransitionContext(
        lead=lead,
        from_stage=from_stage,
        to_stage=to_stage,
        user_id=user_id,
        gate_skipped=gate_skipped,
        skip_reason=skip_reason,
    )

    # Run all pre-checks; collect all violations
    for check in PRE_CHECKS:
        ctx.violations.extend(await check(ctx, db))

    # Hard violations cannot be skipped — return all violations so caller sees the full picture
    if any(v.hard for v in ctx.violations):
        raise StageTransitionBlocked(ctx.violations)

    # Soft violations can be skipped with a reason
    if ctx.violations and not gate_skipped:
        raise StageTransitionBlocked(ctx.violations)

    # ADR-003: log force-moves to operational logger so ops can audit gate bypasses
    if ctx.violations and gate_skipped:
        log.warning(
            "stage_change.gate_skipped lead_id=%s user_id=%s to_stage=%s reason=%r violations=%s",
            lead.id, user_id, to_stage.name, skip_reason,
            [v.code for v in ctx.violations],
        )

    # Apply transition
    lead.stage_id = to_stage.id

    # Run post-actions
    for action in POST_ACTIONS:
        await action(ctx, db)

    await db.flush()
    return lead
