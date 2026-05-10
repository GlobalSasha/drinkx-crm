"""Automation Builder domain services — Sprint 2.5 G1.

Three concerns:
  1. CRUD on automations (validate trigger/action enums, scope to workspace).
  2. `evaluate_trigger(trigger_type, ctx)` — fan-out from existing hot
     paths (stage_change post-action, form lead-factory after-create,
     inbox processor after-attach). Workspace-scoped, condition-aware,
     append-only run history.
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
    VALID_TRIGGERS,
    Automation,
    AutomationRun,
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
    is_active: bool = True,
) -> Automation:
    if trigger not in VALID_TRIGGERS:
        raise InvalidTrigger(trigger)
    if action_type not in VALID_ACTIONS:
        raise InvalidAction(action_type)
    _validate_action_config(action_type, action_config_json)

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
    trigger + per-trigger filter + condition_json, dispatch the action
    and append a run row. Returns the run rows for ops/visibility.

    Caller is responsible for committing the parent transaction. This
    function only stages rows on the session — it never commits.

    Failure isolation: each automation runs in its own try/except. A
    failure in one automation does NOT abort the rest of the fan-out
    or the parent transaction. Failed runs append with status='failed'
    and an `error` string."""
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

        # Sprint 2.6 G1 stability fix #2 — wrap each per-automation
        # action in a SAVEPOINT. A SQLAlchemy error inside one
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
        try:
            async with db.begin_nested():
                await _dispatch_action(
                    db, automation=automation, lead=lead
                )
        except Exception as exc:
            truncate_pending_to(pre_pending_len)
            run = await repo.create_run(
                db,
                automation_id=automation.id,
                lead_id=lead.id,
                status="failed",
                error=str(exc)[:500],
            )
            runs.append(run)
            log.warning(
                "automation.action.failed",
                automation_id=str(automation.id),
                error=str(exc)[:200],
            )
            continue

        run = await repo.create_run(
            db,
            automation_id=automation.id,
            lead_id=lead.id,
            status="success",
        )
        runs.append(run)

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

async def _dispatch_action(
    db: AsyncSession, *, automation: Automation, lead: Lead
) -> None:
    """Pick + run the action handler. Each handler stages rows on the
    session; caller commits."""
    if automation.action_type == "send_template":
        await _send_template_action(
            db, automation=automation, lead=lead
        )
    elif automation.action_type == "create_task":
        await _create_task_action(
            db, automation=automation, lead=lead
        )
    elif automation.action_type == "move_stage":
        await _move_stage_action(
            db, automation=automation, lead=lead
        )
    else:
        # Defensive — service-layer validation should prevent this.
        raise ValueError(
            f"unknown action_type: {automation.action_type}"
        )


async def _send_template_action(
    db: AsyncSession, *, automation: Automation, lead: Lead
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

    config = automation.action_config_json or {}
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
        "automation_id": str(automation.id),
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
                automation_id=str(automation.id),
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
                automation_id=automation.id,
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
    db: AsyncSession, *, automation: Automation, lead: Lead
) -> None:
    """Stage a task-type Activity row on the lead. `due_in_hours`
    defaults to 24."""
    config = automation.action_config_json or {}
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
                "automation_id": str(automation.id),
            },
        )
    )


async def _move_stage_action(
    db: AsyncSession, *, automation: Automation, lead: Lead
) -> None:
    """Direct stage flip. v1 bypasses the gate engine in
    `app/automation/stage_change.py` — automations are admin-curated
    and gates would defeat the purpose. Logs an `automation_move`
    payload on the resulting stage_change Activity so the audit trail
    is clear that a human didn't move it."""
    from sqlalchemy import select

    from app.pipelines.models import Stage

    config = automation.action_config_json or {}
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

    from_stage_id = lead.stage_id
    lead.stage_id = target.id
    db.add(
        Activity(
            lead_id=lead.id,
            user_id=None,
            type="stage_change",
            payload_json={
                "from_stage_id": str(from_stage_id) if from_stage_id else None,
                "to_stage_id": str(target.id),
                "source": "automation",
                "automation_id": str(automation.id),
            },
        )
    )
