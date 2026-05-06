"""Tests for Activity CRUD — nested under leads."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo

    assignment_status = kwargs.pop("assignment_status", "assigned")
    assigned_to = kwargs.pop("assigned_to", None)
    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db, workspace_id, payload,
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


async def _make_activity(db, lead_id, user_id, **kwargs):
    from app.activity import repositories as repo

    payload = dict(type="comment", payload_json={})
    payload.update(kwargs)
    return await repo.create(db, lead_id, user_id, payload)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_create_comment_activity(db, workspace, user):
    """Creating a comment activity succeeds and sets type=comment."""
    lead = await _make_lead(db, workspace.id)
    from app.activity import services

    activity = await services.create_activity(
        db, workspace.id, lead.id, user.id,
        {"type": "comment", "payload_json": {"text": "Hello"}, "body": "Hello"},
    )
    assert activity.type == "comment"
    assert activity.lead_id == lead.id
    assert activity.user_id == user.id


@skip_no_pg
async def test_create_task_activity(db, workspace, user):
    """Creating a task activity requires task_due_at."""
    lead = await _make_lead(db, workspace.id)
    due = datetime.now(timezone.utc) + timedelta(days=1)
    from app.activity import services

    activity = await services.create_activity(
        db, workspace.id, lead.id, user.id,
        {"type": "task", "payload_json": {}, "task_due_at": due},
    )
    assert activity.type == "task"
    assert activity.task_done is False


@skip_no_pg
async def test_create_task_without_due_at_raises(db, workspace, user):
    """Creating a task without task_due_at raises ValueError."""
    lead = await _make_lead(db, workspace.id)
    from app.activity import services

    with pytest.raises(ValueError, match="task_due_at"):
        await services.create_activity(
            db, workspace.id, lead.id, user.id,
            {"type": "task", "payload_json": {}},
        )


@skip_no_pg
async def test_create_reminder_activity(db, workspace, user):
    lead = await _make_lead(db, workspace.id)
    trigger = datetime.now(timezone.utc) + timedelta(hours=2)
    from app.activity import services

    activity = await services.create_activity(
        db, workspace.id, lead.id, user.id,
        {"type": "reminder", "payload_json": {}, "reminder_trigger_at": trigger},
    )
    assert activity.type == "reminder"


@skip_no_pg
async def test_create_file_activity(db, workspace, user):
    lead = await _make_lead(db, workspace.id)
    from app.activity import services

    activity = await services.create_activity(
        db, workspace.id, lead.id, user.id,
        {"type": "file", "payload_json": {}, "file_url": "https://s3/file.pdf", "file_kind": "pdf"},
    )
    assert activity.type == "file"
    assert activity.file_url == "https://s3/file.pdf"


@skip_no_pg
async def test_create_system_activity(db, workspace, user):
    lead = await _make_lead(db, workspace.id)
    from app.activity import services

    activity = await services.create_activity(
        db, workspace.id, lead.id, user.id,
        {"type": "system", "payload_json": {"event": "lead_created"}},
    )
    assert activity.type == "system"


@skip_no_pg
async def test_invalid_activity_type_raises(db, workspace, user):
    """Unknown type raises ValueError."""
    lead = await _make_lead(db, workspace.id)
    from app.activity import services

    with pytest.raises(ValueError, match="Invalid activity type"):
        await services.create_activity(
            db, workspace.id, lead.id, user.id,
            {"type": "not_a_type", "payload_json": {}},
        )


@skip_no_pg
async def test_list_activities_cursor_pagination(db, workspace, user):
    """Insert 5 activities, fetch limit=2 → next_cursor returned; page 2 has remainder."""
    lead = await _make_lead(db, workspace.id)
    from app.activity import services

    due = datetime.now(timezone.utc) + timedelta(days=1)
    for i in range(5):
        await _make_activity(db, lead.id, user.id, type="comment", payload_json={"i": i})

    items_p1, next_cursor = await services.list_activities(
        db, workspace.id, lead.id, limit=2
    )
    assert len(items_p1) == 2
    assert next_cursor is not None

    items_p2, next_cursor2 = await services.list_activities(
        db, workspace.id, lead.id, cursor=next_cursor, limit=2
    )
    assert len(items_p2) == 2

    items_p3, next_cursor3 = await services.list_activities(
        db, workspace.id, lead.id, cursor=next_cursor2, limit=2
    )
    assert len(items_p3) == 1
    assert next_cursor3 is None


@skip_no_pg
async def test_list_activities_type_filter(db, workspace, user):
    """?type=comment returns only comment activities."""
    lead = await _make_lead(db, workspace.id)

    await _make_activity(db, lead.id, user.id, type="comment", payload_json={})
    await _make_activity(db, lead.id, user.id, type="system", payload_json={})

    from app.activity import services

    items, _ = await services.list_activities(
        db, workspace.id, lead.id, type_filter="comment"
    )
    assert all(a.type == "comment" for a in items)
    assert len(items) == 1


@skip_no_pg
async def test_complete_task_sets_task_done(db, workspace, user):
    """complete_task sets task_done=True and task_completed_at."""
    lead = await _make_lead(db, workspace.id)
    due = datetime.now(timezone.utc) + timedelta(days=1)
    activity = await _make_activity(
        db, lead.id, user.id, type="task", task_due_at=due
    )

    from app.activity import services

    completed = await services.complete_task(
        db, workspace.id, lead.id, activity.id, user.id
    )
    assert completed.task_done is True
    assert completed.task_completed_at is not None


@skip_no_pg
async def test_complete_task_on_non_task_raises(db, workspace, user):
    """complete_task on a non-task activity raises ActivityWrongType."""
    lead = await _make_lead(db, workspace.id)
    activity = await _make_activity(db, lead.id, user.id, type="comment")

    from app.activity import services

    with pytest.raises(services.ActivityWrongType):
        await services.complete_task(db, workspace.id, lead.id, activity.id, user.id)


@skip_no_pg
async def test_complete_task_is_idempotent(db, workspace, user):
    """Calling complete_task twice does not raise and keeps task_done=True."""
    lead = await _make_lead(db, workspace.id)
    due = datetime.now(timezone.utc) + timedelta(days=1)
    activity = await _make_activity(db, lead.id, user.id, type="task", task_due_at=due)

    from app.activity import services

    first = await services.complete_task(db, workspace.id, lead.id, activity.id, user.id)
    second = await services.complete_task(db, workspace.id, lead.id, activity.id, user.id)

    assert second.task_done is True
    assert second.task_completed_at == first.task_completed_at
