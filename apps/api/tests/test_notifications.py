"""Tests for app.notifications — Sprint 1.5 group 1."""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


# ---------------------------------------------------------------------------
# notify() — row shape
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_notify_writes_correct_row_shape(db, workspace, user):
    """`notify()` should stage a Notification row with the exact fields supplied."""
    from app.notifications.services import notify

    row = await notify(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        kind="lead_transferred",
        title="Передан лид: Acme",
        body="hello",
    )

    assert row.id is not None
    assert row.workspace_id == workspace.id
    assert row.user_id == user.id
    assert row.kind == "lead_transferred"
    assert row.title == "Передан лид: Acme"
    assert row.body == "hello"
    assert row.lead_id is None
    assert row.read_at is None
    assert row.created_at is not None


@skip_no_pg
async def test_notify_truncates_long_title(db, workspace, user):
    """Titles longer than 200 chars are truncated to fit the column."""
    from app.notifications.services import notify

    long_title = "A" * 500
    row = await notify(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        kind="system",
        title=long_title,
    )
    assert len(row.title) == 200


# ---------------------------------------------------------------------------
# list_for_user / mark_read / cross-user guard
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_list_returns_only_callers_rows(db, workspace, user, admin_user):
    """A user only sees their own notifications."""
    from app.notifications.services import list_for_user, notify

    await notify(db, workspace_id=workspace.id, user_id=user.id, kind="system", title="mine")
    await notify(db, workspace_id=workspace.id, user_id=admin_user.id, kind="system", title="theirs")

    items, total, _ = await list_for_user(db, user_id=user.id)
    titles = [i.title for i in items]
    assert "mine" in titles
    assert "theirs" not in titles
    assert total == 1


@skip_no_pg
async def test_list_unread_filter(db, workspace, user):
    """unread=True filters out already-read rows."""
    from app.notifications.services import (
        list_for_user,
        mark_read,
        notify,
    )

    r1 = await notify(db, workspace_id=workspace.id, user_id=user.id, kind="system", title="one")
    await notify(db, workspace_id=workspace.id, user_id=user.id, kind="system", title="two")

    await mark_read(db, notification_id=r1.id, user_id=user.id)

    items, total, unread_count = await list_for_user(db, user_id=user.id, unread=True)
    assert total == 1
    assert unread_count == 1
    assert items[0].title == "two"


@skip_no_pg
async def test_mark_read_cross_user_guard_returns_none(db, workspace, user, admin_user):
    """mark_read() must NOT mutate a row that belongs to another user."""
    from app.notifications.services import mark_read, notify

    other_row = await notify(
        db, workspace_id=workspace.id, user_id=admin_user.id, kind="system", title="theirs"
    )

    # `user` (manager) tries to mark `admin_user`'s notification as read
    result = await mark_read(db, notification_id=other_row.id, user_id=user.id)
    assert result is None

    # The row must still be unread
    await db.refresh(other_row)
    assert other_row.read_at is None


@skip_no_pg
async def test_mark_read_sets_read_at(db, workspace, user):
    """Marking own notification stamps read_at."""
    from app.notifications.services import mark_read, notify

    row = await notify(db, workspace_id=workspace.id, user_id=user.id, kind="system", title="r")
    assert row.read_at is None

    updated = await mark_read(db, notification_id=row.id, user_id=user.id)
    assert updated is not None
    assert updated.read_at is not None


@skip_no_pg
async def test_mark_all_read_only_affects_caller(db, workspace, user, admin_user):
    """mark_all_read flips all of caller's unread, leaves others untouched."""
    from app.notifications.services import list_for_user, mark_all_read, notify

    await notify(db, workspace_id=workspace.id, user_id=user.id, kind="system", title="m1")
    await notify(db, workspace_id=workspace.id, user_id=user.id, kind="system", title="m2")
    other = await notify(
        db, workspace_id=workspace.id, user_id=admin_user.id, kind="system", title="theirs"
    )

    affected = await mark_all_read(db, user_id=user.id)
    assert affected == 2

    # Caller has zero unread
    _, _, unread_count = await list_for_user(db, user_id=user.id, unread=True)
    assert unread_count == 0

    # Other user untouched
    await db.refresh(other)
    assert other.read_at is None
