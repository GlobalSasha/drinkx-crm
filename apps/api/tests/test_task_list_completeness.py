"""A live task must not vanish from a list because other rows came first
(audit G5).

Two defects, reproduced in tests/repro_g5_defects.py before they were fixed:

A  The lead card asked for `?type=task&limit=200`, ordered by created_at DESC,
   and threw away the cursor the backend returned. On a lead with more than
   200 task rows an older OPEN task sat on page two and never reached the
   screen.

B  `/me/tasks` ordered by due date, applied no status filter at all, and cut
   the result at 500. Five hundred completed tasks with earlier deadlines
   filled the budget, and the single open task was not in the answer.

What must hold now, and is checked below:

* open / done / overdue are selected and sorted IN THE DATABASE, before any
  limit — the fix is not a bigger number;
* the order is total — (task_done, task_due_at NULLS LAST, id) — so a keyset
  cursor neither skips nor repeats a row when due dates collide;
* counts describe the whole server-side selection, not the loaded page;
* the effective-assignee ladder (explicit -> lead owner -> author) and the
  manager/head/admin visibility rules are unchanged.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# Configures every SQLAlchemy mapper; without it a run of this file on its own
# dies resolving a relationship string to a model nothing here imports.
import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

NOW = datetime.now(timezone.utc)


# --- fixtures in miniature --------------------------------------------------

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


def _task(*, workspace_id, lead_id, user_id, text, due, done, created_at=None,
          assignee_user_id=None):
    """A task row built directly, so a test can control created_at and the
    due date independently of insert order."""
    from app.activity.models import Activity, ActivityType

    return Activity(
        workspace_id=None if lead_id is not None else workspace_id,
        lead_id=lead_id,
        user_id=user_id,
        assignee_user_id=assignee_user_id,
        type=ActivityType.task.value,
        payload_json={"title": text},
        body=text,
        task_due_at=due,
        task_done=done,
        task_completed_at=NOW if done else None,
        created_at=created_at or NOW,
    )


async def _drain(fetch, *, limit: int) -> list[dict]:
    """Walk every page the way the UI's «Показать ещё» does."""
    out: list[dict] = []
    cursor = None
    for _ in range(200):  # a bounded loop: a cursor bug must fail, not hang
        rows, cursor, _counts = await fetch(cursor=cursor, limit=limit)
        out.extend(rows)
        if cursor is None:
            return out
    raise AssertionError("pagination did not terminate")


# ---------------------------------------------------------------------------
# A. The lead card
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_an_open_task_older_than_200_others_is_on_the_first_page(db, workspace):
    """Defect A. The oldest row on the lead is the only open one."""
    from app.activity import services

    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)

    open_task = _task(
        workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
        text="ПОЗВОНИТЬ КЛИЕНТУ", due=NOW + timedelta(days=3), done=False,
        created_at=NOW - timedelta(days=400),
    )
    db.add(open_task)
    for i in range(250):
        db.add(_task(
            workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
            text=f"Сделано {i}", due=NOW - timedelta(days=300 - i), done=True,
            created_at=NOW - timedelta(days=200) + timedelta(hours=i),
        ))
    await db.flush()

    rows, next_cursor, counts = await services.list_lead_tasks(
        db, workspace_id=workspace.id, lead_id=lead.id, limit=50
    )

    assert rows[0]["id"] == open_task.id, "open work comes before finished work"
    assert next_cursor is not None, "251 tasks do not fit one page of 50"
    # The counters the tab shows are about the lead, not about the page.
    assert counts == {"total": 251, "open": 1, "done": 250, "overdue": 0}


@skip_no_pg
@pytest.mark.asyncio
async def test_paging_a_lead_returns_every_task_exactly_once(db, workspace):
    from app.activity import services

    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)
    for i in range(251):
        db.add(_task(
            workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
            text=f"Задача {i}", due=NOW + timedelta(hours=i), done=(i % 3 == 0),
        ))
    await db.flush()

    async def fetch(*, cursor, limit):
        return await services.list_lead_tasks(
            db, workspace_id=workspace.id, lead_id=lead.id,
            cursor=cursor, limit=limit,
        )

    seen = [r["id"] for r in await _drain(fetch, limit=50)]
    assert len(seen) == 251
    assert len(set(seen)) == 251, "a page boundary repeated a row"


# ---------------------------------------------------------------------------
# B. /me/tasks
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_the_open_task_survives_500_completed_ones(db, workspace):
    """Defect B, exactly as specified: 500 done with earlier due dates."""
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    lead = await _lead(db, workspace.id, me.id)
    for i in range(500):
        db.add(_task(
            workspace_id=workspace.id, lead_id=lead.id, user_id=me.id,
            text=f"Сделано {i}", due=NOW - timedelta(days=500 - i), done=True,
        ))
    open_task = _task(
        workspace_id=workspace.id, lead_id=lead.id, user_id=me.id,
        text="ОТПРАВИТЬ КП", due=NOW + timedelta(days=2), done=False,
    )
    db.add(open_task)
    await db.flush()

    rows, _cursor, counts = await services.list_my_tasks(
        db, workspace_id=workspace.id, user_id=me.id, limit=100
    )

    assert rows[0]["id"] == open_task.id
    assert counts == {"total": 501, "open": 1, "done": 500, "overdue": 0}


@skip_no_pg
@pytest.mark.asyncio
async def test_a_page_cannot_be_asked_to_return_everything(db, workspace):
    """Not «raise 500 to 5000»: the page has a ceiling and a cursor."""
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    for i in range(210):
        db.add(_task(
            workspace_id=workspace.id, lead_id=None, user_id=me.id,
            text=f"Задача {i}", due=NOW + timedelta(hours=i), done=False,
        ))
    await db.flush()

    rows, cursor, counts = await services.list_my_tasks(
        db, workspace_id=workspace.id, user_id=me.id, limit=10_000
    )
    assert len(rows) == services.MAX_TASK_PAGE == 200
    assert cursor is not None
    assert counts["total"] == 210


# ---------------------------------------------------------------------------
# Ordering at the page boundary
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_identical_due_dates_across_a_page_boundary(db, workspace):
    """Requirement 8. One due date for everything: without a unique
    tie-breaker a keyset cursor drops or repeats rows at every boundary."""
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    same_due = NOW + timedelta(days=1)
    for i in range(25):
        db.add(_task(
            workspace_id=workspace.id, lead_id=None, user_id=me.id,
            text=f"Одинаковый срок {i}", due=same_due, done=False,
        ))
    await db.flush()

    async def fetch(*, cursor, limit):
        return await services.list_my_tasks(
            db, workspace_id=workspace.id, user_id=me.id, cursor=cursor, limit=limit
        )

    # Page size 1 puts a boundary between every pair of equal keys.
    for size in (1, 2, 7, 10):
        seen = [r["id"] for r in await _drain(fetch, limit=size)]
        assert len(seen) == 25, f"page size {size} lost rows"
        assert len(set(seen)) == 25, f"page size {size} repeated rows"


@skip_no_pg
@pytest.mark.asyncio
async def test_tasks_without_a_due_date_sort_last_and_are_still_reachable(db, workspace):
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    dated = [
        _task(workspace_id=workspace.id, lead_id=None, user_id=me.id,
              text=f"Со сроком {i}", due=NOW + timedelta(days=i), done=False)
        for i in range(5)
    ]
    undated = [
        _task(workspace_id=workspace.id, lead_id=None, user_id=me.id,
              text=f"Без срока {i}", due=None, done=False)
        for i in range(5)
    ]
    for row in dated + undated:
        db.add(row)
    await db.flush()

    async def fetch(*, cursor, limit):
        return await services.list_my_tasks(
            db, workspace_id=workspace.id, user_id=me.id, cursor=cursor, limit=limit
        )

    ordered = await _drain(fetch, limit=3)
    assert len(ordered) == 10
    assert [r["task_due_at"] is None for r in ordered] == [False] * 5 + [True] * 5
    assert {r["id"] for r in ordered} == {r.id for r in dated + undated}


@skip_no_pg
@pytest.mark.asyncio
async def test_open_and_done_never_interleave_across_pages(db, workspace):
    """A done task with an early deadline must not push an open one down."""
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    for i in range(20):
        db.add(_task(
            workspace_id=workspace.id, lead_id=None, user_id=me.id,
            text=f"Закрыта {i}", due=NOW - timedelta(days=100 + i), done=True,
        ))
        db.add(_task(
            workspace_id=workspace.id, lead_id=None, user_id=me.id,
            text=f"Открыта {i}", due=NOW + timedelta(days=i), done=False,
        ))
    await db.flush()

    async def fetch(*, cursor, limit):
        return await services.list_my_tasks(
            db, workspace_id=workspace.id, user_id=me.id, cursor=cursor, limit=limit
        )

    flags = [r["task_done"] for r in await _drain(fetch, limit=6)]
    assert flags == [False] * 20 + [True] * 20


# ---------------------------------------------------------------------------
# Filters and counts
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_status_filters_run_in_the_database_and_counts_cover_everything(db, workspace):
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    rows = [
        ("Просрочена", NOW - timedelta(days=1), False),
        ("Ещё не горит", NOW + timedelta(days=1), False),
        ("Без срока", None, False),
        ("Закрыта", NOW - timedelta(days=2), True),
    ]
    for text, due, done in rows:
        db.add(_task(workspace_id=workspace.id, lead_id=None, user_id=me.id,
                     text=text, due=due, done=done))
    await db.flush()

    async def page(status: str, limit: int = 50):
        return await services.list_my_tasks(
            db, workspace_id=workspace.id, user_id=me.id, status=status, limit=limit
        )

    all_rows, _c, counts = await page("all")
    assert {r["text"] for r in all_rows} == {t for t, _, _ in rows}
    assert counts == {"total": 4, "open": 3, "done": 1, "overdue": 1}

    open_rows, _c, open_counts = await page("open")
    assert {r["text"] for r in open_rows} == {"Просрочена", "Ещё не горит", "Без срока"}
    # The chips stay labelled with the full picture while one of them is on.
    assert open_counts == counts

    done_rows, _c, _ = await page("done")
    assert {r["text"] for r in done_rows} == {"Закрыта"}

    overdue_rows, _c, _ = await page("overdue")
    assert {r["text"] for r in overdue_rows} == {"Просрочена"}

    # And the filter really is in SQL: a page of one still returns the
    # matching row, not the first row of the unfiltered set.
    first_overdue, _c, _ = await page("overdue", limit=1)
    assert [r["text"] for r in first_overdue] == ["Просрочена"]


@skip_no_pg
@pytest.mark.asyncio
async def test_counts_do_not_shrink_to_the_page(db, workspace):
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    for i in range(30):
        db.add(_task(workspace_id=workspace.id, lead_id=None, user_id=me.id,
                     text=f"Задача {i}", due=NOW + timedelta(hours=i),
                     done=(i < 10)))
    await db.flush()

    rows, cursor, counts = await services.list_my_tasks(
        db, workspace_id=workspace.id, user_id=me.id, limit=5
    )
    assert len(rows) == 5 and cursor is not None
    assert counts["total"] == 30 and counts["done"] == 10 and counts["open"] == 20


@skip_no_pg
@pytest.mark.asyncio
async def test_a_cursor_from_nowhere_is_rejected(db, workspace):
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    with pytest.raises(services.TaskCursorInvalid):
        await services.list_my_tasks(
            db, workspace_id=workspace.id, user_id=me.id, cursor="nonsense"
        )


# ---------------------------------------------------------------------------
# Semantics that must survive the rewrite
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_task_without_a_lead_is_listed(db, workspace):
    from app.activity import services

    me = await _user(db, workspace.id, "manager", "Me")
    standalone = _task(workspace_id=workspace.id, lead_id=None, user_id=me.id,
                       text="Позвонить в банк", due=None, done=False)
    db.add(standalone)
    await db.flush()

    rows, _c, counts = await services.list_my_tasks(
        db, workspace_id=workspace.id, user_id=me.id
    )
    assert [r["id"] for r in rows] == [standalone.id]
    assert rows[0]["lead_id"] is None
    assert counts["total"] == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_the_assignee_ladder_is_unchanged(db, workspace):
    """Explicit assignee -> lead owner -> author, and the raw value stays
    visible so the lead card's «Поручить» select can tell them apart."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    owner = await _user(db, workspace.id, "manager", "Owner")
    doer = await _user(db, workspace.id, "manager", "Doer")
    lead = await _lead(db, workspace.id, owner.id)
    ownerless = await _lead(db, workspace.id, None)

    explicit = _task(workspace_id=workspace.id, lead_id=lead.id, user_id=head.id,
                     text="Явный", due=NOW, done=False, assignee_user_id=doer.id)
    by_owner = _task(workspace_id=workspace.id, lead_id=lead.id, user_id=head.id,
                     text="По владельцу", due=NOW, done=False)
    by_author = _task(workspace_id=workspace.id, lead_id=ownerless.id, user_id=head.id,
                      text="По автору", due=NOW, done=False)
    for row in (explicit, by_owner, by_author):
        db.add(row)
    await db.flush()

    rows, _c, _counts = await services.list_lead_tasks(
        db, workspace_id=workspace.id, lead_id=lead.id
    )
    by_text = {r["text"]: r for r in rows}
    assert by_text["Явный"]["assignee_user_id"] == doer.id
    assert by_text["Явный"]["assignee_name"] == "Doer"
    assert by_text["Явный"]["explicit_assignee_user_id"] == doer.id
    assert by_text["По владельцу"]["assignee_user_id"] == owner.id
    assert by_text["По владельцу"]["assignee_name"] == "Owner"
    # Nothing was written on the row: the card must keep showing «владелец
    # лида» rather than pre-selecting the owner as an explicit assignee.
    assert by_text["По владельцу"]["explicit_assignee_user_id"] is None

    ownerless_rows, _c, _counts = await services.list_lead_tasks(
        db, workspace_id=workspace.id, lead_id=ownerless.id
    )
    assert ownerless_rows[0]["assignee_user_id"] == head.id
    assert ownerless_rows[0]["explicit_assignee_user_id"] is None


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_still_does_not_see_a_colleagues_tasks(db, workspace):
    """G3's visibility rule, re-checked against the paginated query."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Kirill")
    peer = await _user(db, workspace.id, "manager", "Peer")

    for i in range(30):
        db.add(_task(workspace_id=workspace.id, lead_id=None, user_id=head.id,
                     text=f"Кириллу {i}", due=NOW + timedelta(hours=i),
                     done=False, assignee_user_id=manager.id))
        db.add(_task(workspace_id=workspace.id, lead_id=None, user_id=head.id,
                     text=f"Петру {i}", due=NOW + timedelta(hours=i),
                     done=False, assignee_user_id=peer.id))
    await db.flush()

    async def fetch(*, cursor, limit):
        return await services.list_tasks(
            db, workspace_id=workspace.id, actor=manager, cursor=cursor, limit=limit
        )

    rows = await _drain(fetch, limit=7)
    assert len(rows) == 30
    assert all(r["text"].startswith("Кириллу") for r in rows)

    _page1, _c, counts = await services.list_tasks(
        db, workspace_id=workspace.id, actor=manager, limit=5
    )
    assert counts["total"] == 30, "the counter must not leak the other manager's work"

    head_rows = await _drain(
        lambda *, cursor, limit: services.list_tasks(
            db, workspace_id=workspace.id, actor=head, cursor=cursor, limit=limit
        ),
        limit=25,
    )
    assert len(head_rows) == 60


@skip_no_pg
@pytest.mark.asyncio
async def test_the_lead_tab_shows_the_whole_leads_work_not_just_the_readers(db, workspace):
    """The card is a view of the lead, not of the person reading it — the
    behaviour it had before G5, kept."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    owner = await _user(db, workspace.id, "manager", "Owner")
    other = await _user(db, workspace.id, "manager", "Other")
    lead = await _lead(db, workspace.id, owner.id)

    db.add(_task(workspace_id=workspace.id, lead_id=lead.id, user_id=head.id,
                 text="На владельце", due=NOW, done=False))
    db.add(_task(workspace_id=workspace.id, lead_id=lead.id, user_id=head.id,
                 text="На другом", due=NOW, done=False, assignee_user_id=other.id))
    await db.flush()

    rows, _c, counts = await services.list_lead_tasks(
        db, workspace_id=workspace.id, lead_id=lead.id
    )
    assert {r["text"] for r in rows} == {"На владельце", "На другом"}
    assert counts["total"] == 2
