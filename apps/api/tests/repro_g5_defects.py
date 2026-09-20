"""Reproduction of the two G5 defects: an active task disappears from the UI
just because other rows were created before it.

Not named test_*: this file asserts the PRE-FIX behaviour, so it is evidence,
not a regression test. The permanent tests live in test_task_list_completeness.py
and assert the opposite. Run it explicitly against the code as it was:

    REQUIRE_TEST_DB=1 python -m pytest tests/repro_g5_defects.py -q -s

Needs the same disposable Postgres as the rest of the suite.

A. Lead card. GET /leads/{id}/activities?type=task&limit=200 is ordered by
   created_at DESC and returns a cursor. With more than 200 task rows on one
   lead, an older OPEN task falls onto page two, and the frontend hook never
   asks for page two.

B. /me/tasks. The query orders by task_due_at and cuts at 500 with no status
   filter at all. 500 completed tasks with earlier due dates fill the whole
   budget, and the one open task with a later due date never reaches the
   client.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# Importing the app configures every SQLAlchemy mapper. Without it a run of
# this file alone dies resolving a relationship string to a model no test in
# this file imports.
import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

NOW = datetime.now(timezone.utc)


async def _user(db, workspace_id, role: str, name: str):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


async def _lead(db, workspace_id, owner_id=None):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id,
        dict(company_name=f"Company {uuid.uuid4().hex[:6]}"),
        assigned_to=owner_id,
        assignment_status="assigned",
    )


def _task_row(*, workspace_id, lead_id, user_id, text, due, done, created_at):
    """An Activity row of type=task, created directly so the reproduction can
    control created_at — the column the lead-card list sorts on."""
    from app.activity.models import Activity, ActivityType

    return Activity(
        workspace_id=None if lead_id is not None else workspace_id,
        lead_id=lead_id,
        user_id=user_id,
        type=ActivityType.task.value,
        payload_json={"title": text},
        body=text,
        task_due_at=due,
        task_done=done,
        task_completed_at=NOW if done else None,
        created_at=created_at,
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_A_lead_card_loses_an_open_task_behind_page_one(db, workspace):
    """>200 tasks on one lead: the open one is older than the rest."""
    from app.activity import services

    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)

    # The open task is the oldest row, so `created_at DESC` puts it last.
    open_task = _task_row(
        workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
        text="ПОЗВОНИТЬ КЛИЕНТУ", due=NOW + timedelta(days=3), done=False,
        created_at=NOW - timedelta(days=400),
    )
    db.add(open_task)
    for i in range(250):
        db.add(_task_row(
            workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
            text=f"Сделано {i}", due=NOW - timedelta(days=300 - i), done=True,
            created_at=NOW - timedelta(days=200 - (i * 0.5)),
        ))
    await db.flush()

    items, next_cursor = await services.list_activities(
        db, workspace.id, lead.id, type_filter="task", cursor=None, limit=200,
    )

    ids = {a.id for a in items}
    print(f"\n[A] tasks on the lead : 251")
    print(f"[A] rows the UI fetches: {len(items)} (limit=200)")
    print(f"[A] next_cursor        : {next_cursor!r}")
    print(f"[A] open task in page 1: {open_task.id in ids}")
    print(f"[A] open rows on page 1: {sum(1 for a in items if not a.task_done)}")

    # The defect, stated as an assertion.
    assert len(items) == 200
    assert next_cursor is not None, "the backend does offer a second page"
    assert open_task.id not in ids, (
        "expected the open task to be off page one — if this fails the "
        "reproduction no longer describes the defect"
    )
    assert all(a.task_done for a in items), (
        "page one is entirely completed tasks: the tab shows 200 done rows "
        "and hides the only thing left to do"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_B_me_tasks_drops_the_open_task_after_500_done_ones(db, workspace):
    """500 completed tasks with earlier due dates, then one open task."""
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    lead = await _lead(db, workspace.id, me.id)

    for i in range(500):
        db.add(_task_row(
            workspace_id=workspace.id, lead_id=lead.id, user_id=me.id,
            text=f"Сделано {i}", due=NOW - timedelta(days=500 - i), done=True,
            created_at=NOW - timedelta(days=500 - i),
        ))
    open_task = _task_row(
        workspace_id=workspace.id, lead_id=lead.id, user_id=me.id,
        text="ОТПРАВИТЬ КП", due=NOW + timedelta(days=2), done=False,
        created_at=NOW,
    )
    db.add(open_task)
    await db.flush()

    result = await services.list_my_tasks(
        db, workspace_id=workspace.id, user_id=me.id
    )
    if isinstance(result, tuple):
        # Post-G5 the call returns (rows, cursor, counts). The reproduction is
        # about the shape that existed before, so say so rather than dying on
        # a TypeError three lines down.
        rows, _cursor, counts = result
        raise AssertionError(
            "the defect is fixed: /me/tasks is now paginated and returns "
            f"{len(rows)} rows with counts={counts}; the first row is "
            f"{'open' if not rows[0]['task_done'] else 'done'}"
        )
    rows = result
    ids = {r["id"] for r in rows}

    print(f"\n[B] tasks on the user  : 501")
    print(f"[B] rows returned      : {len(rows)} (hard limit 500, no cursor)")
    print(f"[B] open task returned : {open_task.id in ids}")
    print(f"[B] open rows returned : {sum(1 for r in rows if not r['task_done'])}")

    assert len(rows) == 500
    assert open_task.id not in ids, (
        "expected the open task to be cut off by the limit — if this fails "
        "the reproduction no longer describes the defect"
    )
    assert all(r["task_done"] for r in rows), (
        "every row the user gets is already done; the list is useless"
    )
