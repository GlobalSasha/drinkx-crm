"""TASK-02 (P2-6): HTTP-level round trip for assignee_user_id semantics.

apps/api/tests/test_task_contract.py already covers the three states of
`assignee_user_id` (omitted / UUID / null) and the manager-forbidden rule at
the SERVICE layer — it calls `services.update_task_by_id(...,
assignee_provided=True/False)` directly, with `assignee_provided` handed in
by the test itself.

What is not covered anywhere: whether an actual JSON PATCH body without the
key really produces `assignee_provided=False` once it goes through
Pydantic's `TaskPatchIn` parsing at the router
(apps/api/app/activity/routers.py::update_task, model_fields_set), and
whether that state is actually durable once read back through a brand new
DB session (not just the same request-scoped session/identity map). This
file closes that gap with real HTTP calls through the ASGI app, reusing the
`call()` helper pattern from test_sec01_lead_scoped_access.py.

References for the states already proven at the service layer:
  - test_task_contract.py::test_omitting_the_assignee_leaves_it_alone
  - test_task_contract.py::test_a_uuid_assigns_that_person
  - test_task_contract.py::test_null_clears_the_explicit_assignee_back_to_the_lead_owner
  - test_task_contract.py::test_clearing_a_standalone_task_returns_it_to_its_author
  - test_task_contract.py::test_a_manager_cannot_assign_a_colleague
  - test_task_contract.py::test_a_manager_cannot_use_null_to_push_work_onto_the_lead_owner
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

TOMORROW = datetime.now(timezone.utc) + timedelta(days=1)


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


async def _lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo

    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update({k: v for k, v in kwargs.items() if k not in ("assigned_to",)})
    return await repo.create_lead(
        db, workspace_id, payload,
        assigned_to=kwargs.get("assigned_to"),
        assignment_status="assigned",
    )


async def call(db, actor, method, path, body=None):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            kwargs = {"json": body} if method in ("POST", "PATCH", "PUT") else {}
            if method in ("POST", "PATCH", "PUT") and body is None:
                kwargs = {"json": {}}
            return await c.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


async def _read_assignee_in_a_fresh_session(task_id):
    """Second, independent DB session/connection — not the request-scoped
    `db` fixture's identity map. Proves the PATCH's effect is durable, not
    an artifact of expire_on_commit/identity caching within one session."""
    from tests.conftest import _test_session_factory  # noqa: PLC0415 — только когда PG доступен
    from app.activity.models import Activity

    async with _test_session_factory() as fresh:
        row = await fresh.get(Activity, task_id)
        return row.assignee_user_id


@skip_no_pg
@pytest.mark.asyncio
async def test_http_patch_without_assignee_key_leaves_explicit_alone(db, workspace):
    """A real JSON body that never mentions assignee_user_id must not be
    parsed as "clear it" — this is the omitted/null distinction from BUG-02,
    exercised through the router's own Pydantic parsing instead of a Python
    keyword argument."""
    head = await _user(db, workspace.id, "head", "Head")
    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, assigned_to=owner.id)
    from app.activity import services

    task = await services.create_task(
        db, workspace.id, head,
        text="Позвонить", task_due_at=TOMORROW, assignee_user_id=None, lead_id=lead.id,
    )
    await db.commit()

    resp = await call(db, head, "PATCH", f"/tasks/{task.id}", body={"text": "Позвонить ещё раз"})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    # Эффективный исполнитель — по-прежнему владелец лида, а не head.
    assert out["assignee_user_id"] == str(owner.id)
    assert out["explicit_assignee_user_id"] is None

    persisted = await _read_assignee_in_a_fresh_session(task.id)
    assert persisted is None, "omitted key must not persist as an explicit assignee"


@skip_no_pg
@pytest.mark.asyncio
async def test_http_patch_with_uuid_assigns_explicitly(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    helper = await _user(db, workspace.id, "manager", "Helper")
    from app.activity import services

    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None,
    )
    await db.commit()

    resp = await call(
        db, head, "PATCH", f"/tasks/{task.id}",
        body={"assignee_user_id": str(helper.id)},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["assignee_user_id"] == str(helper.id)
    assert out["explicit_assignee_user_id"] == str(helper.id)

    persisted = await _read_assignee_in_a_fresh_session(task.id)
    assert persisted == helper.id


@skip_no_pg
@pytest.mark.asyncio
async def test_http_head_can_clear_explicit_assignee_to_null(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    owner = await _user(db, workspace.id, "manager", "Owner")
    helper = await _user(db, workspace.id, "manager", "Helper")
    lead = await _lead(db, workspace.id, assigned_to=owner.id)
    from app.activity import services

    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=helper.id, lead_id=lead.id,
    )
    await db.commit()

    resp = await call(db, head, "PATCH", f"/tasks/{task.id}", body={"assignee_user_id": None})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["explicit_assignee_user_id"] is None
    assert out["assignee_user_id"] == str(owner.id), "falls back to the lead owner"

    persisted = await _read_assignee_in_a_fresh_session(task.id)
    assert persisted is None


@skip_no_pg
@pytest.mark.asyncio
async def test_http_manager_reassigning_a_colleague_gets_403(db, workspace):
    """Router-level mapping of ActivityForbidden → 403, not just the
    service-layer exception asserted in test_task_contract.py."""
    manager = await _user(db, workspace.id, "manager", "Manager")
    colleague = await _user(db, workspace.id, "manager", "Colleague")
    from app.activity import services

    task = await services.create_task(
        db, workspace.id, manager,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None,
    )
    await db.commit()

    resp = await call(
        db, manager, "PATCH", f"/tasks/{task.id}",
        body={"assignee_user_id": str(colleague.id)},
    )
    assert resp.status_code == 403, resp.text


@skip_no_pg
@pytest.mark.asyncio
async def test_http_clearing_a_standalone_task_falls_back_to_its_author(db, workspace):
    """TASK-EXPLICIT-03: a task with no lead (`lead_id=None`) clears back to
    whoever authored it, not to some other default — through the real HTTP
    endpoint. Service-layer equivalent:
    test_task_contract.py::test_clearing_a_standalone_task_returns_it_to_its_author."""
    head = await _user(db, workspace.id, "head", "Head")
    helper = await _user(db, workspace.id, "manager", "Helper")
    from app.activity import services

    task = await services.create_task(
        db, workspace.id, head,
        text="Сдать отчёт", task_due_at=None, assignee_user_id=helper.id, lead_id=None,
    )
    await db.commit()

    resp = await call(db, head, "PATCH", f"/tasks/{task.id}", body={"assignee_user_id": None})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["explicit_assignee_user_id"] is None
    assert out["assignee_user_id"] == str(head.id), "standalone task must fall back to its author"
