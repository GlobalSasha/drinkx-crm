"""Reproduction for TASK-03 (P2-7): GET /tasks has no server-side search or
due-date range, so a task far down the sort order is unreachable without
walking every page - and the client-side filter on the /tasks page only ever
sees the pages already loaded.

Not named test_*: this file asserts CURRENT (pre-fix) behaviour and is
evidence for the QA work order, not a regression test. Run it explicitly:

    REQUIRE_TEST_DB=1 TEST_DB_ALLOWED_NAMES=drinkx_test,drinkx_ci,drinkx_migrations_test,drinkx_ci7 \
    TEST_DATABASE_URL=postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_ci7 \
    .venv/bin/python -m pytest tests/repro_task03_search.py -p no:randomly -q -s

Needs the same disposable Postgres as the rest of the suite (drinkx_ci7 only).

Fixture: a manager with 1250 open tasks. 1249 of them have due dates spread
over the next ~52 days; exactly one, whose text contains the marker
"Уникальный-маркер-7f3a", has the LATEST due date of the set. Under the
accepted G5 order (task_done ASC, task_due_at ASC NULLS LAST, id DESC), the
marker task sorts dead last among open tasks - page 1 of 50 (the page the
/tasks screen requests) and even page 1 of 200 (the endpoint's ceiling) will
not contain it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 -- configures SQLAlchemy mappers
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

NOW = datetime.now(timezone.utc)
MARKER = "Уникальный-маркер-7f3a"


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


def _task(*, workspace_id, user_id, text, due, done=False):
    from app.activity.models import Activity, ActivityType

    return Activity(
        workspace_id=workspace_id,
        lead_id=None,
        user_id=user_id,
        assignee_user_id=user_id,
        type=ActivityType.task.value,
        payload_json={"title": text},
        body=text,
        task_due_at=due,
        task_done=done,
        created_at=NOW,
    )


async def _get(db, actor, path: str):
    """Real HTTP request, same pattern as tests/test_lead_tasks_access.py."""
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.clear()


@skip_no_pg
@pytest.mark.asyncio
async def test_repro_marker_task_absent_from_first_page(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")

    # 1249 open tasks, due dates spread over the next ~52 days.
    for i in range(1249):
        db.add(_task(
            workspace_id=workspace.id, user_id=manager.id,
            text=f"Рутинная задача {i}",
            due=NOW + timedelta(hours=i),
        ))
    # The one task anyone is actually looking for - latest due date of all.
    marker_task = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"Согласовать контракт - {MARKER}",
        due=NOW + timedelta(hours=1249) + timedelta(days=1),
    )
    db.add(marker_task)
    await db.flush()

    # 1. Page the UI actually requests (limit=50, see TASKS_PAGE in
    #    apps/web/lib/hooks/use-tasks.ts) does not contain it.
    res = await _get(db, manager, "/tasks?limit=50")
    assert res.status_code == 200
    body = res.json()
    assert body["counts"]["total"] == 1250
    ids_page1 = {i["id"] for i in body["items"]}
    assert str(marker_task.id) not in ids_page1, (
        "expected FAIL-worthy repro: marker task is NOT on the first page of 50"
    )

    # 2. Even at the endpoint's own ceiling (limit=200) it is still absent.
    res200 = await _get(db, manager, "/tasks?limit=200")
    ids_page1_200 = {i["id"] for i in res200.json()["items"]}
    assert str(marker_task.id) not in ids_page1_200, (
        "expected FAIL-worthy repro: marker task is NOT on the first page of 200"
    )

    # 3. There is no `q` parameter to ask the server for it directly. Record
    #    what the endpoint ACTUALLY does with an unknown query param: FastAPI
    #    ignores query params that are not declared on the handler, so `q` is
    #    silently dropped - it is neither a 422 nor an error, just a no-op.
    res_q = await _get(
        db, manager, f"/tasks?limit=50&q={MARKER}"
    )
    assert res_q.status_code == 200, (
        "recorded fact: unknown `q` param does not 422, FastAPI drops it silently"
    )
    ids_with_ignored_q = {i["id"] for i in res_q.json()["items"]}
    assert ids_with_ignored_q == ids_page1, (
        "recorded fact: `q` has zero effect on the result - it is not wired to anything"
    )
    assert str(marker_task.id) not in ids_with_ignored_q

    # 4. Client-side view of the same problem: the /tasks page's search box
    #    filters only `allRows` (the pages already fetched via
    #    useInfiniteQuery). With page size 50 and the marker on a page nobody
    #    has fetched yet, the client-side .filter() in page.tsx would find
    #    nothing - reproduced here by applying the identical predicate
    #    (case-insensitive substring on text) to only the fetched page.
    query_lower = MARKER.lower()
    client_visible_hits = [
        row for row in body["items"]
        if query_lower in row["text"].lower()
        or query_lower in (row.get("lead_company_name") or "").lower()
    ]
    assert client_visible_hits == [], (
        "recorded fact: client-side filter over the loaded page(s) alone "
        "would not find the marker task without pressing <<Показать ещё>> "
        "24+ times first"
    )
