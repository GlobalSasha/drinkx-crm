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
from app.leads.models import Lead
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
    user_id: uuid.UUID
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


POST_ACTIONS: list[PostAction] = [
    set_won_lost_timestamps,
    log_stage_change_activity,
]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def move_stage(
    db: AsyncSession,
    lead: Lead,
    to_stage: Stage,
    user_id: uuid.UUID,
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
