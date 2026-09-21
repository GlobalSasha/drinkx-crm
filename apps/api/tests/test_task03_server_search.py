"""TASK-03 (P2-7) oracle: GET /tasks needs server-side `q` / `due_from` /
`due_to`, applied in the database before counts and before the keyset limit
-- exactly like `status` already is (G5).

This file is the ACCEPTANCE ORACLE, written before the parameters exist.
Every test that exercises `q`/`due_from`/`due_to` is expected to FAIL against
the current code (repro: tests/repro_task03_search.py) and must PASS once
TASK-03 is implemented per
scratchpad/program/contracts/TASK-03_TASK_CONTRACT.md and
scratchpad/program/TASK-03/TASK_SELECTION_CONTRACT.md.

Numbering matches the acceptance freeze in the work order:

  TASK-SEARCH-01  a match past the first page is found via `q`
  TASK-SEARCH-02  q + due_from/due_to + status combine; NULL due; Unicode
                  case-insensitivity; `%` / `_` are literal characters
  TASK-SEARCH-03  cursor pagination with `q` set returns every match exactly
                  once; counts describe the whole q/due-filtered selection
  TASK-SEARCH-04  a manager's `q` never surfaces another workspace's or a
                  colleague's tasks (items or counts); head/admin see all
  TASK-SEARCH-05  DEFERRED to the frontend oracle (stale useInfiniteQuery
                  response after a filter change) -- placeholder only, see
                  the docstring on test_deferred_frontend_stale_response.
  TASK-SEARCH-06  allowed control: omitting `q` leaves order and rows exactly
                  as before (G5 contract, unchanged) -- and is the same
                  negative case as -01 on the CURRENT, unfixed code.
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


# --- fixtures in miniature, matching the style of test_task_list_completeness.py ---

async def _workspace(db):
    from app.auth.models import Workspace

    ws = Workspace(name=f"WS {uuid.uuid4().hex[:6]}", plan="pro", sprint_capacity_per_week=20)
    db.add(ws)
    await db.flush()
    return ws


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


async def _lead(db, workspace_id, owner_id, company_name: str):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id,
        dict(company_name=company_name),
        assigned_to=owner_id,
        assignment_status="assigned",
    )


def _task(*, workspace_id, user_id, text, due=None, done=False, lead_id=None,
          assignee_user_id=None):
    from app.activity.models import Activity, ActivityType

    return Activity(
        workspace_id=None if lead_id is not None else workspace_id,
        lead_id=lead_id,
        user_id=user_id,
        assignee_user_id=assignee_user_id if assignee_user_id is not None else user_id,
        type=ActivityType.task.value,
        payload_json={"title": text},
        body=text,
        task_due_at=due,
        task_done=done,
        created_at=NOW,
    )


async def _get(db, actor, path: str, params: dict | None = None):
    """Real HTTP request through the app, same pattern as
    tests/test_lead_tasks_access.py -- the rule under test lives on the
    router/service, not in a function a direct call would bypass.

    `params` goes through httpx's own query-string encoding (it, not a
    hand-built f-string, is what safely encodes `+`/`|`/Cyrillic in a
    cursor or search term)."""
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path, params=params)
    finally:
        app.dependency_overrides.clear()


async def _drain_q(db, actor, *, q: str, limit: int = 50) -> list[dict]:
    """Walk every page of GET /tasks?q=... the way «Показать ещё» does."""
    out: list[dict] = []
    cursor = None
    for _ in range(200):
        params = {"limit": limit, "q": q}
        if cursor:
            params["cursor"] = cursor
        res = await _get(db, actor, "/tasks", params=params)
        assert res.status_code == 200, res.text
        body = res.json()
        out.append(body)
        cursor = body["next_cursor"]
        if cursor is None:
            return out
    raise AssertionError("pagination with q did not terminate")


# ---------------------------------------------------------------------------
# TASK-SEARCH-01 -- a distant match is found via q
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_search_finds_a_match_far_down_the_sort_order(db, workspace):
    """1250 open tasks; only the marker task matches `q`, and it has the
    latest due date of the set, so it is last in the unfiltered order. With
    `q` wired server-side it must be on the FIRST page regardless."""
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    for i in range(1249):
        db.add(_task(
            workspace_id=workspace.id, user_id=manager.id,
            text=f"Рутинная задача {i}", due=NOW + timedelta(hours=i),
        ))
    marker_task = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"Согласовать контракт - {MARKER}",
        due=NOW + timedelta(hours=1249) + timedelta(days=1),
    )
    db.add(marker_task)
    await db.flush()

    res = await _get(db, manager, f"/tasks?limit=50&q={MARKER}")
    assert res.status_code == 200, res.text
    body = res.json()
    ids = {i["id"] for i in body["items"]}
    assert str(marker_task.id) in ids, "q must be applied in the database, before the limit"
    # Only the matching row(s) should be present.
    assert ids == {str(marker_task.id)}


# ---------------------------------------------------------------------------
# TASK-SEARCH-02 -- combinations, NULL due, Unicode case, literal % / _
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_search_is_unicode_case_insensitive(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    t = _task(workspace_id=workspace.id, user_id=manager.id, text="Позвонить Клиенту", due=NOW)
    db.add(t)
    await db.flush()

    for needle in ("позвонить", "ПОЗВОНИТЬ", "КлиЕнту"):
        res = await _get(db, manager, f"/tasks?q={needle}")
        ids = {i["id"] for i in res.json()["items"]}
        assert str(t.id) in ids, f"case-insensitive match failed for {needle!r}"


@skip_no_pg
@pytest.mark.asyncio
async def test_search_matches_a_task_with_null_due_date(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    t = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"Без срока {MARKER}", due=None,
    )
    db.add(t)
    await db.flush()

    res = await _get(db, manager, f"/tasks?q={MARKER}")
    ids = {i["id"] for i in res.json()["items"]}
    assert str(t.id) in ids


@skip_no_pg
@pytest.mark.asyncio
async def test_percent_and_underscore_are_literal_not_wildcards(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    literal = _task(workspace_id=workspace.id, user_id=manager.id, text="Скидка 100% клиенту")
    other = _task(workspace_id=workspace.id, user_id=manager.id, text="Скидка 100 клиенту огромная")
    db.add_all([literal, other])
    await db.flush()

    res = await _get(db, manager, "/tasks?q=100%25")  # literal "100%", url-escaped
    ids = {i["id"] for i in res.json()["items"]}
    assert ids == {str(literal.id)}, "`%` in the query must be a literal character, not a wildcard"

    underscored = _task(workspace_id=workspace.id, user_id=manager.id, text="network_switch готов")
    unrelated = _task(workspace_id=workspace.id, user_id=manager.id, text="networkXswitch готов")
    db.add_all([underscored, unrelated])
    await db.flush()

    res2 = await _get(db, manager, "/tasks?q=network_switch")
    ids2 = {i["id"] for i in res2.json()["items"]}
    assert str(underscored.id) in ids2
    assert str(unrelated.id) not in ids2, "`_` must be literal, not SQL's single-char wildcard"


@skip_no_pg
@pytest.mark.asyncio
async def test_search_combines_with_due_range_and_status(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    in_range_open = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"В диапазоне {MARKER}", due=NOW + timedelta(days=2),
    )
    out_of_range = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"Вне диапазона {MARKER}", due=NOW + timedelta(days=30),
    )
    in_range_done = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"Сделано в диапазоне {MARKER}", due=NOW + timedelta(days=3), done=True,
    )
    db.add_all([in_range_open, out_of_range, in_range_done])
    await db.flush()

    due_from = (NOW).isoformat()
    due_to = (NOW + timedelta(days=5)).isoformat()
    res = await _get(
        db, manager, "/tasks",
        params={"q": MARKER, "due_from": due_from, "due_to": due_to, "status": "open"},
    )
    assert res.status_code == 200, res.text
    ids = {i["id"] for i in res.json()["items"]}
    assert ids == {str(in_range_open.id)}, (
        "q, due_from/due_to and status must all narrow the same query, in the DB"
    )


# ---------------------------------------------------------------------------
# TASK-SEARCH-03 -- full pagination under q; counts over the filtered set
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_paging_under_q_returns_each_match_exactly_once_and_counts_match(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    N = 137
    for i in range(N):
        db.add(_task(
            workspace_id=workspace.id, user_id=manager.id,
            text=f"{MARKER} номер {i}", due=NOW + timedelta(hours=i),
            done=(i % 5 == 0),
        ))
    # Noise that must never be counted or returned.
    for i in range(80):
        db.add(_task(
            workspace_id=workspace.id, user_id=manager.id,
            text=f"Шум {i}", due=NOW + timedelta(hours=i),
        ))
    await db.flush()

    pages = await _drain_q(db, manager, q=MARKER, limit=10)
    all_ids = [row["id"] for page in pages for row in page["items"]]
    assert len(all_ids) == N, "every matching row must be returned across pages"
    assert len(set(all_ids)) == N, "a page boundary skipped or repeated a row"

    # counts on every page describe the WHOLE q-filtered selection (G5 rule:
    # computed before the status filter, same as today -- now also before
    # nothing narrower than q/due).
    for page in pages:
        assert page["counts"]["total"] == N
        assert page["counts"]["open"] + page["counts"]["done"] == N


# ---------------------------------------------------------------------------
# TASK-SEARCH-04 -- workspace / role isolation under q
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_q_does_not_leak_another_workspace_or_a_colleagues_tasks(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    colleague = await _user(db, workspace.id, "manager", "Коллега")
    other_ws = await _workspace(db)
    stranger = await _user(db, other_ws.id, "manager", "Чужой")

    mine = _task(workspace_id=workspace.id, user_id=manager.id, text=f"Моя {MARKER}")
    colleague_task = _task(workspace_id=workspace.id, user_id=colleague.id, text=f"Коллеги {MARKER}")
    other_ws_task = _task(workspace_id=other_ws.id, user_id=stranger.id, text=f"Чужого пространства {MARKER}")
    db.add_all([mine, colleague_task, other_ws_task])
    await db.flush()

    res = await _get(db, manager, f"/tasks?q={MARKER}")
    body = res.json()
    ids = {i["id"] for i in body["items"]}
    assert ids == {str(mine.id)}
    assert body["counts"]["total"] == 1, "counts under q must not include a colleague's or another workspace's rows"

    head = await _user(db, workspace.id, "head", "Руководитель")
    res_head = await _get(db, head, f"/tasks?q={MARKER}")
    ids_head = {i["id"] for i in res_head.json()["items"]}
    assert ids_head == {str(mine.id), str(colleague_task.id)}, "head sees the whole workspace under q"
    assert str(other_ws_task.id) not in ids_head


# ---------------------------------------------------------------------------
# TASK-SEARCH-05 -- DEFERRED (frontend)
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "TASK-SEARCH-05 is a frontend concern (stale useInfiniteQuery page "
        "mixing with a new filter value) and is deferred to the frontend "
        "oracle (UX-01 per the task contract). Expectation to encode there: "
        "changing q/due/status must reset pagination (new queryKey) so a "
        "page fetched under the old filter is never shown blended with rows "
        "fetched under the new one. No vitest/node_modules available in "
        "this QA worktree (audit-qa8) to author it now."
    )
)
def test_deferred_frontend_stale_response_placeholder():
    pass


# ---------------------------------------------------------------------------
# TASK-SEARCH-06 -- allowed control: omitting q changes nothing (G5 order)
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_without_q_rows_and_order_are_unchanged(db, workspace):
    """Regression guard for the G5 order (task_done ASC, task_due_at ASC
    NULLS LAST, id DESC): adding q/due_from/due_to must not perturb the
    endpoint when they are absent. On the CURRENT code this passes trivially
    (nothing is wired yet) and after the fix it must still pass -- q/due are
    additive filters, not a replacement for the default query."""
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    for i in range(12):
        db.add(_task(
            workspace_id=workspace.id, user_id=manager.id,
            text=f"Задача {i}", due=NOW + timedelta(hours=i), done=(i % 4 == 0),
        ))
    await db.flush()

    res = await _get(db, manager, "/tasks?limit=50")
    body = res.json()
    ids_in_order = [i["id"] for i in body["items"]]
    # G5 order: open before done, i.e. every id with done=False precedes
    # every id with done=True in this response.
    done_flags = [i["task_done"] for i in body["items"]]
    first_done_index = done_flags.index(True) if True in done_flags else len(done_flags)
    assert all(not d for d in done_flags[:first_done_index]), "open tasks must precede done tasks"
    assert len(ids_in_order) == 12
    assert body["counts"]["total"] == 12


# ---------------------------------------------------------------------------
# QA addendum -- empty / whitespace-only q is "no filter", same rows and
# order as omitting q entirely (TASK_SELECTION_CONTRACT.md §3: "Пустой или
# пробельный `q` -- это отсутствие фильтра, а не поиск пустой строки").
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_blank_q_is_treated_as_no_filter(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    for i in range(9):
        db.add(_task(
            workspace_id=workspace.id, user_id=manager.id,
            text=f"Задача {i}", due=NOW + timedelta(hours=i), done=(i % 3 == 0),
        ))
    await db.flush()

    baseline = await _get(db, manager, "/tasks?limit=50")
    baseline_body = baseline.json()

    for blank in ("", "   ", "\t\n "):
        res = await _get(db, manager, "/tasks", params={"limit": 50, "q": blank})
        assert res.status_code == 200, res.text
        body = res.json()
        assert [i["id"] for i in body["items"]] == [i["id"] for i in baseline_body["items"]], (
            f"blank q={blank!r} must not narrow or reorder the selection"
        )
        assert body["counts"] == baseline_body["counts"]


# ---------------------------------------------------------------------------
# Hardening addendum -- naive `due_from`/`due_to` are read as UTC, and `q` has
# the same 200-character ceiling as the lead search (docs/TASK_LISTS.md §6).
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_naive_due_bounds_are_read_as_utc(db, workspace):
    """A bound without an offset (`2026-09-21T00:00:00`) is valid ISO but
    means nothing until someone reads a timezone into it. The server reads
    UTC -- so the naive bound selects exactly what the same instant with an
    explicit `+00:00` selects, and no 422."""
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    inside = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"В окне {MARKER}", due=NOW + timedelta(hours=2),
    )
    before = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"До окна {MARKER}", due=NOW - timedelta(hours=2),
    )
    after = _task(
        workspace_id=workspace.id, user_id=manager.id,
        text=f"После окна {MARKER}", due=NOW + timedelta(days=2),
    )
    db.add_all([inside, before, after])
    await db.flush()

    lo, hi = NOW, NOW + timedelta(days=1)
    aware = await _get(db, manager, "/tasks", params={
        "q": MARKER, "due_from": lo.isoformat(), "due_to": hi.isoformat(),
    })
    naive = await _get(db, manager, "/tasks", params={
        "q": MARKER,
        "due_from": lo.replace(tzinfo=None).isoformat(),
        "due_to": hi.replace(tzinfo=None).isoformat(),
    })
    assert naive.status_code == 200, naive.text
    assert {i["id"] for i in naive.json()["items"]} == {str(inside.id)}
    assert [i["id"] for i in naive.json()["items"]] == [i["id"] for i in aware.json()["items"]]
    assert naive.json()["counts"] == aware.json()["counts"]


@skip_no_pg
@pytest.mark.asyncio
async def test_overlong_q_is_rejected(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Менеджер")
    ok = await _get(db, manager, "/tasks", params={"q": "я" * 200})
    assert ok.status_code == 200, ok.text
    too_long = await _get(db, manager, "/tasks", params={"q": "я" * 201})
    assert too_long.status_code == 422
