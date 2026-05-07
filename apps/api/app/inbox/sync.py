"""Gmail sync orchestration — historical + incremental.

Both entry points (`history_sync_for_user` and `incremental_sync_for_all`)
are pure async functions. They are wrapped by Celery tasks in
app.scheduled.jobs which provide the per-task NullPool engine + audit row.

Per-message failures are caught and logged so one bad message never
poisons a tick.

After GmailClient refreshes its access token, the rotated JSON is
persisted back to ChannelConnection.credentials_json so the next tick
picks up the fresh token.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.config import get_settings
from app.inbox.gmail_client import GmailClient
from app.inbox.models import ChannelConnection
from app.inbox.processor import process_message

log = structlog.get_logger()


async def _persist_credentials(
    session: AsyncSession,
    *,
    conn: ChannelConnection,
    client: GmailClient,
) -> None:
    """If the client refreshed its token, write the rotated JSON back."""
    new_creds = client.refreshed_credentials_json()
    if new_creds and new_creds != conn.credentials_json:
        conn.credentials_json = new_creds
        await session.flush()


async def history_sync_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> int:
    """Pull the last `gmail_history_months` of mail for a single user.

    Returns the number of messages processed (regardless of whether the
    processor stored anything — purely a throughput counter).
    """
    s = get_settings()
    bound_log = log.bind(user_id=str(user_id))

    res = await session.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user is None:
        bound_log.warning("gmail.history_sync.user_not_found")
        return 0

    res = await session.execute(
        select(ChannelConnection).where(
            ChannelConnection.workspace_id == user.workspace_id,
            ChannelConnection.user_id == user.id,
            ChannelConnection.channel_type == "gmail",
            ChannelConnection.status == "active",
        )
    )
    conn = res.scalar_one_or_none()
    if conn is None:
        bound_log.warning("gmail.history_sync.no_connection")
        return 0

    try:
        client = GmailClient(conn.credentials_json)
    except Exception as exc:
        bound_log.exception("gmail.history_sync.client_init_failed", error=str(exc)[:200])
        conn.status = "error"
        await session.commit()
        return 0

    after_date = (
        datetime.now(timezone.utc) - timedelta(days=30 * s.gmail_history_months)
    ).strftime("%Y/%m/%d")
    query = f"after:{after_date}"

    bound_log.info("gmail.history_sync.start", query=query)
    msg_refs = await client.list_messages(query=query, max_results=2000)
    bound_log.info("gmail.history_sync.list", count=len(msg_refs))

    processed = 0
    for ref in msg_refs:
        msg_id = ref.get("id")
        if not msg_id:
            continue
        try:
            full = await client.get_message(msg_id)
            if full is None:
                continue
            await process_message(
                session,
                raw_message=full,
                user_id=user.id,
                workspace_id=user.workspace_id,
            )
            processed += 1
        except Exception as exc:
            bound_log.warning(
                "gmail.history_sync.message_failed",
                gmail_id=msg_id,
                error=str(exc)[:200],
            )
            continue

    profile = await client.get_profile()
    cursor = profile.get("historyId") if profile else None

    extra = dict(conn.extra_json or {})
    if cursor:
        extra["last_history_id"] = str(cursor)
    extra["last_history_sync_at"] = datetime.now(timezone.utc).isoformat()
    extra["last_history_processed"] = processed
    conn.extra_json = extra
    conn.last_sync_at = datetime.now(timezone.utc)
    await _persist_credentials(session, conn=conn, client=client)
    await session.commit()

    bound_log.info("gmail.history_sync.done", processed=processed, cursor=cursor)
    return processed


async def incremental_sync_for_all(session: AsyncSession) -> int:
    """Every-5-min tick: process new messages for every active gmail conn.

    Per-user failures don't kill the tick — they're caught, logged,
    and the channel is flipped to status='error' if the client itself
    can't be built.
    """
    res = await session.execute(
        select(ChannelConnection).where(
            ChannelConnection.channel_type == "gmail",
            ChannelConnection.status == "active",
        )
    )
    conns = list(res.scalars())
    if not conns:
        log.info("gmail.incremental.no_active_connections")
        return 0

    total_processed = 0
    for conn in conns:
        bound_log = log.bind(
            workspace_id=str(conn.workspace_id),
            user_id=str(conn.user_id) if conn.user_id else None,
            channel_id=str(conn.id),
        )
        try:
            n = await _incremental_for_one(session, conn=conn, bound_log=bound_log)
            total_processed += n
        except Exception as exc:
            bound_log.exception(
                "gmail.incremental.user_failed",
                error=str(exc)[:200],
            )
            await session.rollback()
            continue

    return total_processed


async def _incremental_for_one(
    session: AsyncSession,
    *,
    conn: ChannelConnection,
    bound_log,
) -> int:
    extra = dict(conn.extra_json or {})
    cursor = extra.get("last_history_id")

    try:
        client = GmailClient(conn.credentials_json)
    except Exception as exc:
        bound_log.warning("gmail.incremental.client_init_failed", error=str(exc)[:200])
        conn.status = "error"
        await session.commit()
        return 0

    if not cursor:
        # First tick after install before history sync finished — seed
        # the cursor and bail out. Real backfill is owned by
        # gmail_history_sync, dispatched from /gmail/callback.
        profile = await client.get_profile()
        if profile and profile.get("historyId"):
            extra["last_history_id"] = str(profile["historyId"])
            extra["seeded_from_profile_at"] = datetime.now(timezone.utc).isoformat()
            conn.extra_json = extra
            await _persist_credentials(session, conn=conn, client=client)
            await session.commit()
        return 0

    entries = await client.get_history(start_history_id=str(cursor))
    if not entries:
        # Even on no-op ticks, persist refreshed credentials so we don't
        # carry an expired access token across many ticks.
        await _persist_credentials(session, conn=conn, client=client)
        conn.last_sync_at = datetime.now(timezone.utc)
        await session.commit()
        return 0

    seen_ids: set[str] = set()
    new_message_ids: list[str] = []
    new_cursor = cursor
    for entry in entries:
        entry_history_id = str(entry.get("id") or "")
        if entry_history_id and (entry_history_id > new_cursor):
            new_cursor = entry_history_id
        for added in entry.get("messagesAdded") or []:
            mid = (added.get("message") or {}).get("id")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                new_message_ids.append(mid)

    bound_log.info("gmail.incremental.batch", new_messages=len(new_message_ids))

    processed = 0
    for mid in new_message_ids:
        try:
            full = await client.get_message(mid)
            if full is None:
                continue
            await process_message(
                session,
                raw_message=full,
                user_id=conn.user_id,  # may be None for workspace-level conns
                workspace_id=conn.workspace_id,
            )
            processed += 1
        except Exception as exc:
            bound_log.warning(
                "gmail.incremental.message_failed",
                gmail_id=mid,
                error=str(exc)[:200],
            )
            continue

    extra["last_history_id"] = new_cursor
    extra["last_incremental_processed"] = processed
    conn.extra_json = extra
    conn.last_sync_at = datetime.now(timezone.utc)
    await _persist_credentials(session, conn=conn, client=client)
    await session.commit()
    return processed
