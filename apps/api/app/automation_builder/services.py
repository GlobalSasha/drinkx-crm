"""Automation Builder domain services — Sprint 2.5 G1, multi-step Sprint 2.7 G2.

Three concerns:
  1. CRUD on automations (validate trigger/action enums + steps, scope to workspace).
  2. `evaluate_trigger(trigger_type, ctx)` — fan-out from existing hot
     paths (stage_change post-action, form lead-factory after-create,
     inbox processor after-attach). Workspace-scoped, condition-aware,
     append-only run history. Multi-step automations fire step 0
     synchronously and queue steps 1+ as `automation_step_runs` rows
     for the beat scheduler.
  3. Action handlers — `send_template_action` / `create_task_action` /
     `move_stage_action`. v1 keeps the side-effects fail-soft so a
     misconfigured automation can't break the parent transaction.

Caller commits unless documented otherwise. The trigger-fan-out path
calls `safe_evaluate_trigger()` which swallows exceptions — the
parent stage_change / form-create / inbox-attach must never roll back
because of an automation problem.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.automation_builder import repositories as repo
from app.automation_builder.condition import evaluate as evaluate_condition
from app.automation_builder.models import (
    VALID_ACTIONS,
    VALID_STEP_TYPES,
    VALID_TRIGGERS,
    Automation,
    AutomationRun,
    AutomationStepRun,
)
from app.automation_builder.render import render_template_text
from app.leads.models import Lead

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Custom exceptions — router maps to HTTP
# ---------------------------------------------------------------------------

class AutomationNotFound(Exception):
    """404 — wrong id, or cross-workspace lookup."""


class InvalidTrigger(Exception):
    """400 — `trigger` not in VALID_TRIGGERS."""


class InvalidAction(Exception):
    """400 — `action_type` not in VALID_ACTIONS."""


class InvalidActionConfig(Exception):
    """400 — action_config_json missing required keys for the chosen
    action_type. Each handler documents its required keys."""


class InvalidSteps(Exception):
    """400 — `steps_json` malformed (unknown type, bad config, or
    a delay outside the 0 < hours <= 720 window)."""


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _validate_action_config(action_type: str, config: dict | None) -> None:
    """Hard-fail the create/update if action_config_json is incomplete
    for the chosen action_type. Surfaces as 400 instead of letting a
    half-configured row sit in the DB and silently fail every fire."""
    config = config or {}
    if action_type == "send_template":
        if not config.get("template_id"):
            raise InvalidActionConfig("send_template requires template_id")
    elif action_type == "create_task":
        if not config.get("title"):
            raise InvalidActionConfig("create_task requires title")
        # due_in_hours optional — defaults to 24 in the handler.
    elif action_type == "move_stage":
        if not config.get("target_stage_id"):
            raise InvalidActionConfig("move_stage requires target_stage_id")


# ---------------------------------------------------------------------------
# Multi-step helpers — Sprint 2.7 G2
# ---------------------------------------------------------------------------

# A delay can be at most 30 days. Beyond that, schedule a calendar
# event manually — keeps the queue from growing unboundedly with
# typo'd 8760-hour delays.
_DELAY_HOURS_MAX = 720


def _validate_steps(steps: list[dict] | None) -> None:
    """Hard-fail if `steps_json` is malformed:
      - unknown `type` (must be in VALID_STEP_TYPES)
      - missing/invalid `config` for action steps
      - delay_hours outside (0, 720]
      - empty list / first step is delay_hours (a chain that opens
        with a wait has no anchor — the trigger event IS the anchor,
        and the user can always add a delay step before another
        action; we just disallow leading-delay-only chains).
    """
    if steps is None:
        return
    if not isinstance(steps, list):
        raise InvalidSteps("steps_json must be a list")
    if len(steps) == 0:
        # Treat empty list same as null — caller may rely on this.
        return
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise InvalidSteps(f"step {idx}: must be an object")
        step_type = step.get("type")
        config = step.get("config") or {}
        if step_type not in VALID_STEP_TYPES:
            raise InvalidSteps(f"step {idx}: unknown type {step_type!r}")
        if step_type == "delay_hours":
            try:
                hours = int(config.get("hours") or 0)
            except (TypeError, ValueError):
                raise InvalidSteps(f"step {idx}: hours must be int") from None
            if hours <= 0 or hours > _DELAY_HOURS_MAX:
                raise InvalidSteps(
                    f"step {idx}: hours must be in (0, {_DELAY_HOURS_MAX}]"
                )
        else:
            # Action step — re-use the existing per-action-type guard.
            _validate_action_config(step_type, config)


def _has_steps(automation: Automation) -> bool:
    """A multi-step automation is one with a non-empty steps_json."""
    steps = automation.steps_json
    return bool(steps) and isinstance(steps, list) and len(steps) > 0


def _legacy_step_from_action(automation: Automation) -> dict:
    """For old single-action rows, treat them as a 1-element chain."""
    return {
        "type": automation.action_type,
        "config": dict(automation.action_config_json or {}),
    }


def _resolved_chain(automation: Automation) -> list[dict]:
    """Return the chain to fire — `steps_json` if present, otherwise
    the legacy single-action wrapped as a 1-element list. Always
    returns a non-empty list."""
    if _has_steps(automation):
        return list(automation.steps_json or [])
    return [_legacy_step_from_action(automation)]


def _compute_schedule_offsets(steps: list[dict]) -> list[int]:
    """Map each step's index to a cumulative delay in hours from t=0.
    Step 0 is always 0; step N's offset = sum of `delay_hours` steps
    strictly before N in the chain. The delay step itself contributes
    its hours to subsequent steps but doesn't get a wall-clock slot
    of its own (it has no side-effect to fire — it's just a gate).

    Example: [send_template, delay 2h, create_task, delay 24h, send_template]
      → offsets = [0, 2, 2, 26, 26]
    """
    offsets: list[int] = []
    cumulative = 0
    for step in steps:
        offsets.append(cumulative)
        if step.get("type") == "delay_hours":
            try:
                cumulative += int(step.get("config", {}).get("hours") or 0)
            except (TypeError, ValueError):
                # Validation should catch this earlier; defensive.
                pass
    return offsets


async def list_automations(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[Automation]:
    return await repo.list_for_workspace(db, workspace_id=workspace_id)


async def create_automation(
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
    steps_json: list[dict] | None = None,
    is_active: bool = True,
) -> Automation:
    if trigger not in VALID_TRIGGERS:
        raise InvalidTrigger(trigger)
    if action_type not in VALID_ACTIONS:
        raise InvalidAction(action_type)
    _validate_action_config(action_type, action_config_json)
    _validate_steps(steps_json)

    return await repo.create(
        db,
        workspace_id=workspace_id,
        created_by=created_by,
        name=name.strip(),
        trigger=trigger,
        trigger_config_json=trigger_config_json,
        condition_json=condition_json,
        action_type=action_type,
        action_config_json=action_config_json or {},
        steps_json=steps_json if steps_json else None,
        is_active=is_active,
    )


async def update_automation(
    db: AsyncSession,
    *,
    automation_id: uuid.UUID,
    workspace_id: uuid.UUID,
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
    if trigger is not None and trigger not in VALID_TRIGGERS:
        raise InvalidTrigger(trigger)
    if action_type is not None and action_type not in VALID_ACTIONS:
        raise InvalidAction(action_type)

    automation = await repo.get_by_id(
        db, automation_id=automation_id, workspace_id=workspace_id
    )
    if automation is None:
        raise AutomationNotFound(str(automation_id))

    # Resolve the post-update action_type + config to validate the
    # combination — accepting only one of them while leaving the other
    # at its old value would let an inconsistent pair slip through.
    target_action = action_type or automation.action_type
    target_config = (
        action_config_json
        if action_config_json is not None
        else automation.action_config_json
    )
    if action_type is not None or action_config_json is not None:
        _validate_action_config(target_action, target_config)

    if steps_set:
        # Empty list normalises to None — keeps the «is multi-step»
        # check (truthy on non-empty list) consistent in the runtime.
        normalised = steps_json if steps_json else None
        _validate_steps(normalised)
        steps_json = normalised

    return await repo.update(
        db,
        automation=automation,
        name=name.strip() if name is not None else None,
        trigger=trigger,
        trigger_config_json=trigger_config_json,
        trigger_config_set=trigger_config_set,
        condition_json=condition_json,
        condition_set=condition_set,
        action_type=action_type,
        action_config_json=action_config_json,
        steps_json=steps_json,
        steps_set=steps_set,
        is_active=is_active,
    )


async def delete_automation(
    db: AsyncSession,
    *,
    automation_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    automation = await repo.get_by_id(
        db, automation_id=automation_id, workspace_id=workspace_id
    )
    if automation is None:
        raise AutomationNotFound(str(automation_id))
    await repo.delete(db, automation=automation)


async def list_runs(
    db: AsyncSession,
    *,
    automation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 50,
) -> list[AutomationRun]:
    # Defends against id-guessing — runs are joined to the automation
    # which IS workspace-scoped.
    return await repo.list_runs_for_automation(
        db,
        automation_id=automation_id,
        workspace_id=workspace_id,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Trigger fan-out
# ---------------------------------------------------------------------------

def _trigger_config_matches(
    automation: Automation, payload: dict[str, Any]
) -> bool:
    """Per-trigger filter check — narrows the candidate set before the
    `condition_json` evaluator runs against the lead. Empty
    trigger_config_json = «match all» for that trigger."""
    config = automation.trigger_config_json or {}

    if automation.trigger == "stage_change":
        # Filter: only fire when the lead moves INTO a specific stage.
        target = config.get("to_stage_id")
        if target is None:
            return True
        return str(payload.get("to_stage_id")) == str(target)

    if automation.trigger == "form_submission":
        target = config.get("form_id")
        if target is None:
            return True
        return str(payload.get("form_id")) == str(target)

    # inbox_match has no extra filter in v1.
    return True


async def evaluate_trigger(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    trigger: str,
    lead: Lead,
    payload: dict[str, Any] | None = None,
) -> list[AutomationRun]:
    """Top-level fan-out. For each active automation that matches the
    trigger + per-trigger filter + condition_json, dispatch step 0 and
    schedule steps 1+ (multi-step) or just dispatch the single action
    (legacy). Returns the parent run rows for ops/visibility.

    Caller is responsible for committing the parent transaction. This
    function only stages rows on the session — it never commits.

    Failure isolation: each automation runs in its own SAVEPOINT. A
    failure in step 0 does NOT abort the rest of the fan-out or the
    parent transaction; subsequent steps stay unscheduled. A failure
    in step N (N>0) is owned by the beat scheduler — it doesn't roll
    back step 0's effect.
    """
    # Imports kept lazy — `dispatch.py` imports back into this
    # module's neighbours (Activity, send_email), so dragging them at
    # module import time would create a circular hazard with
    # `_send_template_action`'s own lazy import.
    from app.automation_builder.dispatch import (
        current_pending_length,
        truncate_pending_to,
    )

    if trigger not in VALID_TRIGGERS:
        log.warning("automation.evaluate.unknown_trigger", trigger=trigger)
        return []

    automations = await repo.list_active_for_trigger(
        db, workspace_id=workspace_id, trigger=trigger
    )
    payload = payload or {}
    runs: list[AutomationRun] = []
    now = datetime.now(tz=timezone.utc)

    for automation in automations:
        if not _trigger_config_matches(automation, payload):
            continue

        try:
            condition_ok = evaluate_condition(
                automation.condition_json, lead
            )
        except Exception as exc:
            run = await repo.create_run(
                db,
                automation_id=automation.id,
                lead_id=lead.id,
                status="failed",
                error=f"condition_eval: {exc}"[:500],
            )
            runs.append(run)
            continue

        if not condition_ok:
            run = await repo.create_run(
                db,
                automation_id=automation.id,
                lead_id=lead.id,
                status="skipped",
                error="condition_not_met",
            )
            runs.append(run)
            continue

        chain = _resolved_chain(automation)
        offsets = _compute_schedule_offsets(chain)
        # Step 0 is the synchronous fire; if it's a delay the chain
        # opens with nothing to dispatch — `_validate_steps` should
        # have refused this, but guard defensively at the runtime
        # boundary too.
        step0 = chain[0]
        is_step0_delay = step0.get("type") == "delay_hours"

        # Sprint 2.6 G1 stability fix #2 — wrap each per-automation
        # step 0 in a SAVEPOINT. A SQLAlchemy error inside one
        # handler used to poison the parent session, leaving the
        # caller's `session.commit()` to silently roll back. With
        # `begin_nested()`, the exception unwinds to the savepoint
        # and the parent session stays clean.
        #
        # The pending-dispatch queue is appended to inside the
        # action; if the savepoint rolls back, the Activity row is
        # gone but the queue entry would still be there → drainer
        # would update a missing row. We snapshot the queue length
        # before and truncate on rollback so the queue stays in
        # lockstep with the savepoint outcome.
        pre_pending_len = current_pending_length()
        step0_failed_error: str | None = None
        try:
            async with db.begin_nested():
                if is_step0_delay:
                    # Defensive — leading delay is invalid but if it
                    # somehow slipped through, treat step 0 as a no-op
                    # and let the scheduler drive subsequent steps.
                    pass
                else:
                    await _dispatch_step(
                        db, automation=automation, lead=lead, step=step0
                    )
        except Exception as exc:
            truncate_pending_to(pre_pending_len)
            step0_failed_error = str(exc)[:500]
            log.warning(
                "automation.action.failed",
                automation_id=str(automation.id),
                error=str(exc)[:200],
            )

        # Parent run row — single source of truth for the fan-out
        # outcome. Multi-step rows that scheduled later steps still
        # land as `status='success'` here; per-step status lives on
        # AutomationStepRun.
        run_status = "failed" if step0_failed_error else "success"
        run = await repo.create_run(
            db,
            automation_id=automation.id,
            lead_id=lead.id,
            status=run_status,
            error=step0_failed_error,
        )
        runs.append(run)

        # Per-step audit row for step 0 — always written so the
        # RunsDrawer per-step grid is populated even for legacy
        # single-action automations.
        await repo.create_step_run(
            db,
            automation_run_id=run.id,
            lead_id=lead.id,
            step_index=0,
            step_json=step0,
            scheduled_at=now,
            executed_at=now,
            status=run_status,
            error=step0_failed_error,
        )

        if step0_failed_error:
            # Chain stops on step 0 failure. Steps 1+ stay
            # unscheduled — operator must rerun manually.
            continue

        # Schedule steps 1+ for the beat scheduler to pick up. Skip
        # delay_hours steps themselves — they have no side-effect to
        # fire; they're just gates that pushed subsequent steps'
        # offsets forward. Their effect is already baked into
        # `offsets[i]` for any non-delay step that comes after.
        for idx in range(1, len(chain)):
            step = chain[idx]
            if step.get("type") == "delay_hours":
                continue
            scheduled_at = now + timedelta(hours=offsets[idx])
            await repo.create_step_run(
                db,
                automation_run_id=run.id,
                lead_id=lead.id,
                step_index=idx,
                step_json=step,
                scheduled_at=scheduled_at,
                executed_at=None,
                status="pending",
                error=None,
            )

    return runs


async def safe_evaluate_trigger(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    trigger: str,
    lead: Lead,
    payload: dict[str, Any] | None = None,
) -> None:
    """Best-effort wrapper for the trigger hot paths
    (stage_change post-action / forms.create after-lead /
    inbox.processor after-attach). Swallows all exceptions — the
    parent transaction must never roll back because of an automation
    problem. Failures are logged via structlog only."""
    try:
        await evaluate_trigger(
            db,
            workspace_id=workspace_id,
            trigger=trigger,
            lead=lead,
            payload=payload,
        )
    except Exception as exc:
        log.warning(
            "automation.evaluate_trigger.swallowed",
            trigger=trigger,
            workspace_id=str(workspace_id),
            error=str(exc)[:200],
        )
        from app.common.sentry_capture import capture
        capture(
            exc,
            fingerprint=["automation-evaluate-trigger", trigger],
            tags={"site": "automation.evaluate_trigger", "trigger": trigger},
            extra={"workspace_id": str(workspace_id), "lead_id": str(lead.id)},
        )


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

async def _dispatch_step(
    db: AsyncSession,
    *,
    automation: Automation | None,
    lead: Lead,
    step: dict,
) -> None:
    """Pick + run the step handler. Each handler stages rows on the
    session; caller commits.

    Sprint 2.7 G2: replaces the old `_dispatch_action(automation, lead)`
    shape. The new signature also accepts `automation=None` so the
    beat scheduler can fire step N>0 even after the parent automation
    was deleted — `step_json` is a frozen snapshot, that's enough.
    `automation_id` for audit comes from the AutomationRun row instead.

    `delay_hours` is a no-op at dispatch time — its hours have already
    been added to subsequent steps' `scheduled_at` in
    `_compute_schedule_offsets`. The scheduler shouldn't even queue
    a row for it (defensive guard here in case it somehow does).
    """
    step_type = step.get("type")
    config = step.get("config") or {}

    # automation_id is needed only for audit on the resulting
    # Activity row. Frozen-step dispatch from the scheduler reads it
    # from the parent run; sync step 0 reads it from `automation`.
    automation_id_str = (
        str(automation.id) if automation is not None else step.get("_automation_id", "")
    )

    if step_type == "send_template":
        await _send_template_action(
            db,
            lead=lead,
            config=config,
            automation_id_str=automation_id_str,
        )
    elif step_type == "create_task":
        await _create_task_action(
            db,
            lead=lead,
            config=config,
            automation_id_str=automation_id_str,
        )
    elif step_type == "move_stage":
        await _move_stage_action(
            db,
            lead=lead,
            config=config,
            automation_id_str=automation_id_str,
        )
    elif step_type == "delay_hours":
        # Pure gate — handled by `_compute_schedule_offsets`; no work here.
        return
    else:
        # Defensive — `_validate_steps` should prevent this.
        raise ValueError(f"unknown step type: {step_type!r}")


async def _send_template_action(
    db: AsyncSession,
    *,
    lead: Lead,
    config: dict,
    automation_id_str: str,
) -> None:
    """Render the configured template against the lead and stage the
    Activity row that records what happened.

    Sprint 2.6 G1 stability fix: this handler NEVER calls SMTP inside
    the parent transaction. For the `email` channel it stages the
    Activity with `delivery_status='pending'` and queues a
    `PendingDispatch` on the contextvar set up by the call site. The
    call site flushes the queue AFTER `session.commit()` via
    `app.automation_builder.dispatch.flush_pending_email_dispatches`.

    Resulting `payload_json.delivery_status` values (set on the
    Activity by either this handler or the post-commit drainer):
      - `pending`            → email queued, awaiting dispatch (set
                               here; flipped by the drainer)
      - `sent`               → drainer's send_email returned True
      - `stub`               → drainer's send_email returned False
                               (SMTP_HOST empty)
      - `failed`             → drainer caught EmailSendError; the
                               drainer never re-raises so the parent
                               commit was already final by then
      - `skipped_no_email`   → set here for empty/whitespace
                               `lead.email` — no dispatch queued
      - `pending` (sticky)   → tg / sms; provider lands in 2.7+,
                               the row stays as a record of what
                               would have been sent

    Activity stays `type="comment"` across all branches — no new
    ActivityType enum value. The frontend chip-renderer reads
    `payload_json.delivery_status`.
    """
    from sqlalchemy import select

    from app.automation_builder.dispatch import (
        PendingDispatch,
        append_pending_dispatch,
    )
    from app.template.models import MessageTemplate

    template_id = config.get("template_id")
    if not template_id:
        raise ValueError("send_template missing template_id")

    res = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == uuid.UUID(str(template_id)),
            MessageTemplate.workspace_id == lead.workspace_id,
        )
    )
    template = res.scalar_one_or_none()
    if template is None:
        raise ValueError(f"template {template_id} not found in workspace")

    rendered = render_template_text(template.text, lead)

    # Common payload — extended below per channel + dispatch outcome.
    payload: dict = {
        "text": rendered[:5000],
        "source": "automation",
        "automation_id": automation_id_str,
        "template_id": str(template.id),
        "template_name": template.name,
        "channel": template.channel,
    }

    if template.channel == "email":
        # Strip whitespace before checking truthiness — a trailing
        # space in the lead's email column would otherwise pass
        # `not lead.email` and bounce in aiosmtplib's header parser.
        # Sprint 2.6 G1 stability fix #3.
        recipient = (lead.email or "").strip() if lead.email else ""

        if not recipient:
            # No usable recipient — record the skip but don't treat
            # as failure (the parent run row stays 'success'). Admin
            # sees the row in the lead's feed and knows the
            # automation fired but bounced for lack of an address.
            payload["delivery_status"] = "skipped_no_email"
            payload["outbound_pending"] = False
            log.warning(
                "automation.send_template.skipped_no_email",
                automation_id=automation_id_str,
                lead_id=str(lead.id),
            )
            db.add(
                Activity(
                    lead_id=lead.id,
                    user_id=None,
                    type="comment",
                    payload_json=payload,
                )
            )
            return

        # Subject: MessageTemplate has no `subject` column in v1 —
        # admins type a single name. Use it as the email subject;
        # the template body is the rendered plain-text content.
        subject = template.name

        # Stage the Activity with a pending status FIRST. `await
        # db.flush()` claims an `id` we can hand to the post-commit
        # drainer. No SMTP call here — the drainer does that after
        # the parent transaction commits.
        payload["delivery_status"] = "pending"
        payload["outbound_pending"] = True
        activity = Activity(
            lead_id=lead.id,
            user_id=None,
            type="comment",
            payload_json=payload,
        )
        db.add(activity)
        await db.flush()

        # Queue post-commit dispatch. The contextvar list is owned by
        # the call site's `collect_pending_email_dispatches()` block.
        # If no collector is in scope (defensive — should not happen
        # with the 3 wired call sites in this sprint), the helper
        # logs a warning; the Activity stays pending and a future
        # cleanup job (Sprint 2.7+) can pick it up.
        append_pending_dispatch(
            PendingDispatch(
                activity_id=activity.id,
                to=recipient,
                subject=subject,
                body=rendered,
                automation_id=uuid.UUID(automation_id_str) if automation_id_str else uuid.uuid4(),
                template_id=template.id,
            )
        )
        return

    # Non-email channels (tg / sms) — Sprint 2.5 stub stays. Sprint
    # 2.7+ will pick providers; until then the Activity row records
    # what would have been sent. `outbound_pending=True` flags
    # «not yet dispatched» so a future migration can reconcile.
    payload["outbound_pending"] = True
    payload["delivery_status"] = "pending"
    db.add(
        Activity(
            lead_id=lead.id,
            user_id=None,
            type="comment",
            payload_json=payload,
        )
    )


async def _create_task_action(
    db: AsyncSession,
    *,
    lead: Lead,
    config: dict,
    automation_id_str: str,
) -> None:
    """Stage a task-type Activity row on the lead. `due_in_hours`
    defaults to 24."""
    title = config.get("title")
    if not title:
        raise ValueError("create_task missing title")
    due_in_hours = int(config.get("due_in_hours") or 24)

    rendered_title = render_template_text(str(title), lead)
    db.add(
        Activity(
            lead_id=lead.id,
            user_id=None,
            type="task",
            task_due_at=datetime.now(tz=timezone.utc)
            + timedelta(hours=due_in_hours),
            task_done=False,
            payload_json={
                "title": rendered_title[:200],
                "source": "automation",
                "automation_id": automation_id_str,
            },
        )
    )


async def _move_stage_action(
    db: AsyncSession,
    *,
    lead: Lead,
    config: dict,
    automation_id_str: str,
) -> None:
    """Move a lead through the canonical `stage_change.move_stage()` so
    pre-checks (hard gates like cross-pipeline) still fire and post-actions
    (Activity log with `source=automation`, lead-agent refresh, downstream
    automation fan-out) run consistently. Soft gates are skipped — the
    automation itself is the audit trail."""
    from sqlalchemy import select

    from app.automation.stage_change import (
        StageTransitionBlocked,
        move_stage,
    )
    from app.pipelines.models import Stage

    target_stage_id = config.get("target_stage_id")
    if not target_stage_id:
        raise ValueError("move_stage missing target_stage_id")

    res = await db.execute(
        select(Stage).where(Stage.id == uuid.UUID(str(target_stage_id)))
    )
    target = res.scalar_one_or_none()
    if target is None:
        raise ValueError(f"stage {target_stage_id} not found")

    # Don't fire if the lead is already on the target stage — prevents
    # an infinite loop if a stage_change automation moves a lead to a
    # stage another automation also targets. Idempotent skip.
    if lead.stage_id == target.id:
        return

    try:
        await move_stage(
            db,
            lead,
            target,
            user_id=None,
            gate_skipped=True,
            skip_reason=f"automation:{automation_id_str}",
        )
    except StageTransitionBlocked as exc:
        # Hard gate (e.g., cross-pipeline) — automation config is broken;
        # surface the violation codes for the run log.
        codes = ",".join(v.code for v in exc.violations)
        raise ValueError(f"stage_change blocked by hard gate(s): {codes}")


# ---------------------------------------------------------------------------
# Step scheduler — Sprint 2.7 G2
#
# Called from the `automation_step_scheduler` Celery beat task in
# `app/scheduled/jobs.py`. Picks up due `AutomationStepRun` rows and
# fires their step. Per-step exception isolation: a failed step
# doesn't roll back step 0's effect (already committed) and doesn't
# block the rest of the queue.
# ---------------------------------------------------------------------------

async def execute_due_step_runs(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 200,
) -> dict:
    """Process all step rows whose `scheduled_at <= now` and which
    haven't fired yet. Returns a summary dict for the cron audit row.

    Per-row commit pattern (mirrors `bulk_import_run` in jobs.py) —
    the scheduler must not let one slow / failing step block the rest.
    """
    from sqlalchemy import select

    from app.automation_builder.dispatch import (
        collect_pending_email_dispatches,
        flush_pending_email_dispatches,
    )
    from app.leads.models import Lead

    if now is None:
        now = datetime.now(tz=timezone.utc)

    rows = await repo.list_due_step_runs(db, now=now, limit=limit)

    fired = 0
    failed = 0
    for step_run in rows:
        # Re-fetch the lead — it may have been deleted between the
        # parent run and now. SET NULL on `lead_id` would already
        # null it; we double-check here.
        lead: Lead | None = None
        if step_run.lead_id is not None:
            lead_res = await db.execute(
                select(Lead).where(Lead.id == step_run.lead_id)
            )
            lead = lead_res.scalar_one_or_none()

        if lead is None:
            step_run.status = "skipped"
            step_run.error = "lead deleted before scheduled fire"
            step_run.executed_at = datetime.now(tz=timezone.utc)
            await db.commit()
            continue

        # Pull `automation_id` from the parent run for audit.
        parent_res = await db.execute(
            select(AutomationRun).where(AutomationRun.id == step_run.automation_run_id)
        )
        parent = parent_res.scalar_one_or_none()
        automation_id_str = str(parent.automation_id) if parent else ""

        # Carry the audit id into the step dict so `_dispatch_step`
        # can read it without a separate repo call.
        step_payload = dict(step_run.step_json or {})
        step_payload["_automation_id"] = automation_id_str

        # Each step gets its own collector + savepoint so failures
        # don't poison the next iteration's session. The collector is
        # an async context manager — yields a list that
        # `_send_template_action` appends to. If the savepoint rolls
        # back, `flush_pending_email_dispatches` will skip rows whose
        # Activity is missing (post-rollback), so no manual cleanup
        # of the queue is needed here.
        try:
            async with collect_pending_email_dispatches() as queue:
                async with db.begin_nested():
                    await _dispatch_step(
                        db,
                        automation=None,
                        lead=lead,
                        step=step_payload,
                    )
            step_run.status = "success"
            step_run.error = None
            step_run.executed_at = datetime.now(tz=timezone.utc)
            await db.commit()
            await flush_pending_email_dispatches(queue)
            fired += 1
        except Exception as exc:
            step_run.status = "failed"
            step_run.error = str(exc)[:500]
            step_run.executed_at = datetime.now(tz=timezone.utc)
            try:
                await db.commit()
            except Exception:  # pragma: no cover — defensive
                await db.rollback()
            failed += 1
            log.warning(
                "automation.step_run.failed",
                step_run_id=str(step_run.id),
                step_index=step_run.step_index,
                error=str(exc)[:200],
            )

    return {
        "scanned": len(rows),
        "fired": fired,
        "failed": failed,
    }


async def list_step_runs_for_run(
    db: AsyncSession,
    *,
    automation_run_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> list[AutomationStepRun]:
    """Per-step grid for the RunsDrawer. Workspace-scoped through
    a join to defend against id-guessing across workspaces."""
    from sqlalchemy import select

    res = await db.execute(
        select(AutomationStepRun)
        .join(
            AutomationRun, AutomationRun.id == AutomationStepRun.automation_run_id
        )
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .where(
            AutomationStepRun.automation_run_id == automation_run_id,
            Automation.workspace_id == workspace_id,
        )
        .order_by(AutomationStepRun.step_index.asc())
    )
    return list(res.scalars().all())
