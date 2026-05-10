"""Audit helper — single emit point.

`log()` stages an AuditLog row on the caller's session. Same transaction
boundary as the action being audited: if the parent commit rolls back,
so does the audit row (no orphan logs of failed actions).

Defensive: never raises. If the row can't be staged for any reason,
the failure is logged via structlog and the parent op continues.
"""
from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog

_log = structlog.get_logger()


async def log(
    session: AsyncSession,
    *,
    action: str,
    workspace_id: UUID,
    user_id: UUID | None = None,
    entity_type: str = "",
    entity_id: UUID | None = None,
    delta: dict | None = None,
) -> None:
    """Write one audit row. Never raises."""
    try:
        row = AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type or "",
            entity_id=entity_id,
            delta_json=delta,
        )
        session.add(row)
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning(
            "audit.log_failed",
            action=action,
            entity_type=entity_type,
            error=str(exc)[:200],
        )
        from app.common.sentry_capture import capture
        capture(
            exc,
            fingerprint=["audit-log-swallow", action],
            tags={"site": "audit.log", "action": action},
        )
