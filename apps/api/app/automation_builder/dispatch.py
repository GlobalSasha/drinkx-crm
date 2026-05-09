"""Post-commit email dispatch — Sprint 2.6 G1 stability fix.

Problem the audit found: `_send_template_action` previously awaited
`aiosmtplib.send` INSIDE the parent DB transaction. SMTP RTT (≤20s
timeout) held the connection open; a network failure mid-send could
leave the session in a poisoned state. Worst case: SMTP succeeded but
the parent commit failed → email sent without a DB record (or vice
versa).

Fix shape:
  - The action handler stages the Activity row with
    `delivery_status='pending'`, flushes to claim an `id`, and appends
    a `PendingDispatch` to a contextvar-scoped list. NO SMTP call
    inside the transaction.
  - The trigger call site wraps the fan-out in
    `collect_pending_email_dispatches()`, commits the parent
    transaction, then drains the list via
    `flush_pending_email_dispatches(pending)`.
  - The drainer opens a NEW short-lived session, calls `send_email`
    per row (catching `EmailSendError`), and updates the matching
    Activity's payload `delivery_status` to `sent` / `stub` /
    `failed`. The drainer never raises — a dispatch failure must
    not roll back the lead/automation data that already committed.

Threading the list via `ContextVar` avoids signature churn on the
existing `safe_evaluate_trigger` / `_dispatch_action` /
`_send_template_action` chain. The contextvar is set by the call
site's `async with` block; intermediate awaits propagate via asyncio
context inheritance.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import AsyncIterator

import structlog
from sqlalchemy import select

from app.activity.models import Activity
from app.db import get_session_factory
from app.email.sender import EmailSendError, send_email

log = structlog.get_logger()


@dataclass
class PendingDispatch:
    """One template-render that needs to be sent post-commit. The
    Activity row already exists in the DB with `delivery_status=
    'pending'`; the drainer updates it after the SMTP call returns."""
    activity_id: uuid.UUID
    to: str
    subject: str
    body: str
    automation_id: uuid.UUID
    template_id: uuid.UUID


_pending: ContextVar[list[PendingDispatch] | None] = ContextVar(
    "_pending_email_dispatches", default=None
)


def append_pending_dispatch(dispatch: PendingDispatch) -> bool:
    """Append a `PendingDispatch` to the active context's list, if
    set. Returns True when appended, False when no collector is in
    scope (the action handler logs a warning in that case — the
    Activity stays in `delivery_status='pending'` indefinitely until
    a future cleanup job picks it up).

    Defensive: never raises — the SMTP-after-commit refactor is
    safety-critical, but a missing collector should not break the
    transaction.
    """
    items = _pending.get()
    if items is None:
        log.warning(
            "automation.dispatch.no_collector_in_scope",
            activity_id=str(dispatch.activity_id),
        )
        return False
    items.append(dispatch)
    return True


def truncate_pending_to(length: int) -> None:
    """Roll back any `PendingDispatch` entries appended past `length`.
    Used by `evaluate_trigger` when an action handler raises inside a
    SAVEPOINT — the Activity row gets rolled back, so the queued
    dispatch must also be dropped (otherwise the drainer would try to
    update an Activity that no longer exists).

    Defensive: no-op when no collector is in scope.
    """
    items = _pending.get()
    if items is None:
        return
    if len(items) > length:
        del items[length:]


def current_pending_length() -> int:
    """Snapshot the active list's length — used by `evaluate_trigger`
    to remember the pre-action position so it can truncate on failure."""
    items = _pending.get()
    return len(items) if items is not None else 0


@asynccontextmanager
async def collect_pending_email_dispatches() -> AsyncIterator[list[PendingDispatch]]:
    """Set up a per-call-site dispatch list. Yield it for the caller
    to drain after commit. Token-based context reset on exit so nested
    fan-outs (in theory unreachable today, but defensive) don't leak
    items into the parent scope."""
    items: list[PendingDispatch] = []
    token = _pending.set(items)
    try:
        yield items
    finally:
        _pending.reset(token)


async def flush_pending_email_dispatches(
    pending: list[PendingDispatch],
) -> None:
    """Drain the collected dispatches in a NEW session. For each
    entry: call `send_email`, catch `EmailSendError` and never
    re-raise, then update the Activity row's `payload_json`.

    Caller is responsible for invoking this AFTER the parent
    transaction has committed. The new session here owns its own
    transaction boundary — the parent's success / failure no longer
    matters at this point, and a dispatch failure on this side must
    not bubble back to the caller.
    """
    if not pending:
        return

    factory = get_session_factory()
    # One session for the batch — keeps it short. Per-row tx via
    # `session.commit()` after each Activity update so a single
    # SMTP failure / DB hiccup doesn't lose other rows.
    async with factory() as session:
        for dispatch in pending:
            sent_status: str
            error: str | None = None

            try:
                sent = await send_email(
                    to=dispatch.to,
                    subject=dispatch.subject,
                    body=dispatch.body,
                )
                sent_status = "sent" if sent else "stub"
            except EmailSendError as exc:
                sent_status = "failed"
                error = str(exc)[:300]
                log.warning(
                    "automation.dispatch.send_failed",
                    activity_id=str(dispatch.activity_id),
                    error=error,
                )
            except Exception as exc:
                # Catch-all defense. A bug in send_email or a
                # surprise (e.g. settings cache returning unexpected
                # shape) must not abort the rest of the batch.
                sent_status = "failed"
                error = f"unexpected: {exc}"[:300]
                log.warning(
                    "automation.dispatch.unexpected_error",
                    activity_id=str(dispatch.activity_id),
                    error=error,
                )

            try:
                res = await session.execute(
                    select(Activity).where(Activity.id == dispatch.activity_id)
                )
                activity = res.scalar_one_or_none()
                if activity is None:
                    # Parent commit must have rolled back after we
                    # appended the dispatch — log and skip. This is
                    # the «commit failed but we already queued»
                    # branch the spec calls out.
                    log.warning(
                        "automation.dispatch.activity_missing",
                        activity_id=str(dispatch.activity_id),
                    )
                    continue
                payload = dict(activity.payload_json or {})
                payload["delivery_status"] = sent_status
                payload["outbound_pending"] = False
                if error is not None:
                    payload["delivery_error"] = error
                activity.payload_json = payload
                await session.commit()
            except Exception as exc:
                log.warning(
                    "automation.dispatch.activity_update_failed",
                    activity_id=str(dispatch.activity_id),
                    error=str(exc)[:300],
                )
                # Roll back this row's session state so the next
                # iteration starts clean. Don't re-raise.
                try:
                    await session.rollback()
                except Exception:
                    pass
