"""Ownership/role guard on per-lead task mutations (plan 010).

Mirrors the comment-edit authorization rule: the task's creator, or an
admin/head, may mutate it. Any other manager gets ActivityForbidden."""
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


async def _make_task(db, lead_id, user_id, **kwargs):
    from app.activity import repositories as repo

    due = kwargs.pop("task_due_at", datetime.now(timezone.utc) + timedelta(days=1))
    payload = dict(type="task", payload_json={}, task_due_at=due)
    payload.update(kwargs)
    return await repo.create(db, lead_id, user_id, payload)


async def _make_comment(db, lead_id, user_id, **kwargs):
    from app.activity import repositories as repo

    payload = dict(type="comment", payload_json={}, body="a comment")
    payload.update(kwargs)
    return await repo.create(db, lead_id, user_id, payload)


async def _other_manager(db, workspace_id):
    """A second manager in the same workspace, distinct from `user`."""
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"peer-{uuid.uuid4().hex[:8]}@test.com",
        name="Peer Manager",
        role="manager",
    )
    db.add(u)
    await db.flush()
    return u


async def _head_user(db, workspace_id):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"head-{uuid.uuid4().hex[:8]}@test.com",
        name="Head",
        role="head",
    )
    db.add(u)
    await db.flush()
    return u


# ---------------------------------------------------------------------------
# Owner may mutate their own task
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_owner_can_complete_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)

    completed = await services.complete_task(db, workspace.id, lead.id, task.id, user)
    assert completed.task_done is True


@skip_no_pg
async def test_owner_can_edit_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)

    updated = await services.update_task(
        db,
        workspace_id=workspace.id,
        lead_id=lead.id,
        activity_id=task.id,
        actor=user,
        body="new text",
        task_due_at=None,
    )
    assert updated.body == "new text"


@skip_no_pg
async def test_owner_can_archive_and_restore_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)

    archived = await services.archive_task(
        db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=user
    )
    assert archived.archived_at is not None

    restored = await services.restore_task(
        db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=user
    )
    assert restored.archived_at is None


@skip_no_pg
async def test_owner_can_reopen_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    await services.complete_task(db, workspace.id, lead.id, task.id, user)

    reopened = await services.reopen_task(
        db, workspace.id, lead.id, task.id, actor=user
    )
    assert reopened.task_done is False


# ---------------------------------------------------------------------------
# A different manager (non-owner, non-admin, non-head) is forbidden
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_non_owner_manager_cannot_complete_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.complete_task(db, workspace.id, lead.id, task.id, peer)


@skip_no_pg
async def test_non_owner_manager_cannot_edit_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.update_task(
            db,
            workspace_id=workspace.id,
            lead_id=lead.id,
            activity_id=task.id,
            actor=peer,
            body="hijacked",
            task_due_at=None,
        )


@skip_no_pg
async def test_non_owner_manager_cannot_archive_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.archive_task(
            db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=peer
        )


@skip_no_pg
async def test_non_owner_manager_cannot_restore_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    await services.archive_task(
        db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=user
    )
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.restore_task(
            db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=peer
        )


@skip_no_pg
async def test_non_owner_manager_cannot_reopen_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    await services.complete_task(db, workspace.id, lead.id, task.id, user)
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.reopen_task(db, workspace.id, lead.id, task.id, actor=peer)


# ---------------------------------------------------------------------------
# admin / head may act on another user's task
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_admin_can_complete_another_users_task(db, workspace, user, admin_user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)

    completed = await services.complete_task(db, workspace.id, lead.id, task.id, admin_user)
    assert completed.task_done is True


@skip_no_pg
async def test_head_can_edit_another_users_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    head = await _head_user(db, workspace.id)

    updated = await services.update_task(
        db,
        workspace_id=workspace.id,
        lead_id=lead.id,
        activity_id=task.id,
        actor=head,
        body="head edit",
        task_due_at=None,
    )
    assert updated.body == "head edit"


@skip_no_pg
async def test_head_can_archive_another_users_task(db, workspace, user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    head = await _head_user(db, workspace.id)

    archived = await services.archive_task(
        db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=head
    )
    assert archived.archived_at is not None


@skip_no_pg
async def test_admin_can_restore_another_users_task(db, workspace, user, admin_user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    await services.archive_task(
        db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=user
    )

    restored = await services.restore_task(
        db, workspace_id=workspace.id, lead_id=lead.id, activity_id=task.id, actor=admin_user
    )
    assert restored.archived_at is None


@skip_no_pg
async def test_admin_can_reopen_another_users_task(db, workspace, user, admin_user):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    task = await _make_task(db, lead.id, user.id)
    await services.complete_task(db, workspace.id, lead.id, task.id, user)

    reopened = await services.reopen_task(db, workspace.id, lead.id, task.id, actor=admin_user)
    assert reopened.task_done is False


# ---------------------------------------------------------------------------
# The guard fires before the type check (no existence/type oracle for a
# non-owner hitting a comment id via the task endpoints)
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_non_owner_hitting_comment_via_task_endpoint_gets_forbidden_not_type_error(
    db, workspace, user
):
    """A non-owner calling update_task on a comment-type activity id should
    get ActivityForbidden (403), not the ValueError "only task activities"
    (400) — the authorization check must run before the type inspection."""
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    comment = await _make_comment(db, lead.id, user.id)
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.update_task(
            db,
            workspace_id=workspace.id,
            lead_id=lead.id,
            activity_id=comment.id,
            actor=peer,
            body="hijacked",
            task_due_at=None,
        )


@skip_no_pg
async def test_non_owner_hitting_comment_via_archive_endpoint_gets_forbidden_not_type_error(
    db, workspace, user
):
    from app.activity import services

    lead = await _make_lead(db, workspace.id)
    comment = await _make_comment(db, lead.id, user.id)
    peer = await _other_manager(db, workspace.id)

    with pytest.raises(services.ActivityForbidden):
        await services.archive_task(
            db, workspace_id=workspace.id, lead_id=lead.id, activity_id=comment.id, actor=peer
        )
