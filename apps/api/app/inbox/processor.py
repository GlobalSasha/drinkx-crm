"""Per-message processing — parse Gmail dict → match → store.

This is the Group 2 placeholder. Group 3 fills in:
  - gmail message → from/to/subject/body/date/direction parsing
  - matcher → MatchResult
  - dedup via Activity.gmail_message_id (added in Group 3 migration)
  - high-confidence path: create Activity(type='email')
  - low-confidence / no-match path: create InboxItem + AI suggestion task

For Group 2 the function simply returns False (= "no work done") so the
sync orchestrator can call it without DB-side effects. Tests for the
real implementation live in Group 7.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


async def process_message(
    session: AsyncSession,
    *,
    raw_message: dict[str, Any],
    user_id: UUID,
    workspace_id: UUID,
) -> bool:
    """Group 3 will implement. Currently a no-op that logs once per call."""
    log.debug(
        "inbox.process_message.stub",
        user_id=str(user_id),
        gmail_id=raw_message.get("id"),
    )
    return False
