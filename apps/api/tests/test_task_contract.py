"""One contract for tasks, whichever screen created them (audit G3).

Three defects, all reproduced here before they were fixed:

BUG-02  `{"assignee_user_id": null}` did not clear the explicit assignee. The
        service could not tell an omitted field from an explicit null, so a
        payload containing only the clear was rejected as "nothing to change",
        and a clear sent alongside new text silently kept the old assignee.

BUG-03  A task created from a lead card required a due date; the same task
        created through POST /tasks did not. Same entity, different rules
        depending on which endpoint the screen happened to use.

Plus the access rule that must survive both fixes: a manager cannot put work
on a colleague, and cannot reach that outcome through a null either.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

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


# ---------------------------------------------------------------------------
# The three states of assignee_user_id in a PATCH
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_omitting_the_assignee_leaves_it_alone(db, workspace):
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")
    task = await services.create_task(
        db, workspace.id, head,
        text="Позвонить", task_due_at=TOMORROW, assignee_user_id=manager.id, lead_id=None,
    )

    await services.update_task_by_id(
        db, workspace.id, task.id, head,
        text="Позвонить ещё раз", task_due_at=None, assignee_user_id=None,
        assignee_provided=False,
    )
    await db.refresh(task)
    assert task.assignee_user_id == manager.id
    assert task.body == "Позвонить ещё раз"


@skip_no_pg
@pytest.mark.asyncio
async def test_a_uuid_assigns_that_person(db, workspace):
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    first = await _user(db, workspace.id, "manager", "First")
    second = await _user(db, workspace.id, "manager", "Second")
    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=first.id, lead_id=None,
    )

    await services.update_task_by_id(
        db, workspace.id, task.id, head,
        text=None, task_due_at=None, assignee_user_id=second.id,
        assignee_provided=True,
    )
    await db.refresh(task)
    assert task.assignee_user_id == second.id


@skip_no_pg
@pytest.mark.asyncio
async def test_null_clears_the_explicit_assignee_back_to_the_lead_owner(db, workspace):
    """BUG-02. The head hands a task to one manager, then takes it back to
    whoever owns the card."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    owner = await _user(db, workspace.id, "manager", "Owner")
    helper = await _user(db, workspace.id, "manager", "Helper")
    lead = await _lead(db, workspace.id, assigned_to=owner.id)
    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=helper.id, lead_id=lead.id,
    )

    await services.update_task_by_id(
        db, workspace.id, task.id, head,
        text=None, task_due_at=None, assignee_user_id=None,
        assignee_provided=True,
    )
    await db.refresh(task)
    assert task.assignee_user_id is None, "the explicit assignee was not cleared"
    assert services.effective_assignee_id(task, lead) == owner.id


@skip_no_pg
@pytest.mark.asyncio
async def test_null_together_with_new_text_applies_both(db, workspace):
    """BUG-02's quieter half: the text changed, the assignee did not."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    owner = await _user(db, workspace.id, "manager", "Owner")
    helper = await _user(db, workspace.id, "manager", "Helper")
    lead = await _lead(db, workspace.id, assigned_to=owner.id)
    task = await services.create_task(
        db, workspace.id, head,
        text="Старый текст", task_due_at=TOMORROW, assignee_user_id=helper.id, lead_id=lead.id,
    )

    await services.update_task_by_id(
        db, workspace.id, task.id, head,
        text="Новый текст", task_due_at=None, assignee_user_id=None,
        assignee_provided=True,
    )
    await db.refresh(task)
    assert task.body == "Новый текст"
    assert task.assignee_user_id is None


@skip_no_pg
@pytest.mark.asyncio
async def test_clearing_a_standalone_task_returns_it_to_its_author(db, workspace):
    """No lead means no owner to fall back to, so the author takes it back.

    Chosen deliberately over leaving it unassigned: a task nobody is
    responsible for disappears from every list.
    """
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    helper = await _user(db, workspace.id, "manager", "Helper")
    task = await services.create_task(
        db, workspace.id, head,
        text="Без лида", task_due_at=TOMORROW, assignee_user_id=helper.id, lead_id=None,
    )

    await services.update_task_by_id(
        db, workspace.id, task.id, head,
        text=None, task_due_at=None, assignee_user_id=None,
        assignee_provided=True,
    )
    await db.refresh(task)
    assert task.assignee_user_id is None
    assert services.effective_assignee_id(task, None) == head.id


@skip_no_pg
@pytest.mark.asyncio
async def test_an_empty_patch_is_rejected(db, workspace):
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None,
    )
    with pytest.raises(ValueError):
        await services.update_task_by_id(
            db, workspace.id, task.id, head,
            text=None, task_due_at=None, assignee_user_id=None, assignee_provided=False,
        )


# ---------------------------------------------------------------------------
# A manager must not reach a colleague, by any of the three states
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_assign_a_colleague(db, workspace):
    from app.activity import services

    manager = await _user(db, workspace.id, "manager", "Manager")
    colleague = await _user(db, workspace.id, "manager", "Colleague")
    task = await services.create_task(
        db, workspace.id, manager,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None,
    )
    with pytest.raises(services.ActivityForbidden):
        await services.update_task_by_id(
            db, workspace.id, task.id, manager,
            text=None, task_due_at=None, assignee_user_id=colleague.id,
            assignee_provided=True,
        )


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_use_null_to_push_work_onto_the_lead_owner(db, workspace):
    """The back door the clear could have opened.

    Clearing on a lead task hands it to whoever owns the card. If a manager
    could do that, `null` would be delegation under another name.
    """
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")
    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, assigned_to=owner.id)
    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=manager.id, lead_id=lead.id,
    )

    with pytest.raises(services.ActivityForbidden):
        await services.update_task_by_id(
            db, workspace.id, task.id, manager,
            text=None, task_due_at=None, assignee_user_id=None,
            assignee_provided=True,
        )
    await db.refresh(task)
    assert task.assignee_user_id == manager.id, "the assignment was cleared anyway"


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_may_still_edit_the_text_of_their_own_task(db, workspace):
    """The clearing rule must not cost managers what they could already do."""
    from app.activity import services

    manager = await _user(db, workspace.id, "manager", "Manager")
    task = await services.create_task(
        db, workspace.id, manager,
        text="Старый", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None,
    )
    await services.update_task_by_id(
        db, workspace.id, task.id, manager,
        text="Новый", task_due_at=None, assignee_user_id=None, assignee_provided=False,
    )
    await db.refresh(task)
    assert task.body == "Новый"


@skip_no_pg
@pytest.mark.asyncio
async def test_assigning_to_a_user_from_another_workspace_is_rejected(db, workspace):
    from app.activity import services
    from app.auth.models import Workspace

    other_ws = Workspace(name="Other", plan="pro", sprint_capacity_per_week=20)
    db.add(other_ws)
    await db.flush()

    head = await _user(db, workspace.id, "head", "Head")
    outsider = await _user(db, other_ws.id, "manager", "Outsider")
    task = await services.create_task(
        db, workspace.id, head,
        text="Задача", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None,
    )
    with pytest.raises(services.TaskAssigneeInvalid):
        await services.update_task_by_id(
            db, workspace.id, task.id, head,
            text=None, task_due_at=None, assignee_user_id=outsider.id,
            assignee_provided=True,
        )


# ---------------------------------------------------------------------------
# One creation contract
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_lead_task_can_be_created_without_a_due_date(db, workspace):
    """BUG-03. The lead card allows saving without a date; the API behind it
    used to refuse, while POST /tasks accepted the same thing."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    lead = await _lead(db, workspace.id, assigned_to=head.id)

    activity = await services.create_activity(
        db, workspace.id, lead.id, head,
        {"type": "task", "body": "Без срока", "payload_json": {"title": "Без срока"}},
    )
    assert activity.task_due_at is None


@skip_no_pg
@pytest.mark.asyncio
async def test_both_creation_paths_agree_about_a_missing_due_date(db, workspace):
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    lead = await _lead(db, workspace.id, assigned_to=head.id)

    via_lead_card = await services.create_activity(
        db, workspace.id, lead.id, head,
        {"type": "task", "body": "Из карточки", "payload_json": {"title": "Из карточки"}},
    )
    via_tasks_page = await services.create_task(
        db, workspace.id, head,
        text="Со страницы задач", task_due_at=None, assignee_user_id=None, lead_id=lead.id,
    )
    assert via_lead_card.task_due_at is None
    assert via_tasks_page.task_due_at is None


@skip_no_pg
@pytest.mark.asyncio
async def test_an_empty_task_text_is_still_refused(db, workspace):
    """Optional due date must not turn into optional everything."""
    from app.activity import services

    head = await _user(db, workspace.id, "head", "Head")
    lead = await _lead(db, workspace.id, assigned_to=head.id)
    with pytest.raises(ValueError):
        await services.create_activity(
            db, workspace.id, lead.id, head,
            {"type": "task", "body": "   ", "payload_json": {"title": "   "}},
        )


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_creating_a_lead_task_still_gets_it_themselves(db, workspace):
    """Pre-existing protection, re-checked because the due date rule moved."""
    from app.activity import services

    manager = await _user(db, workspace.id, "manager", "Manager")
    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, assigned_to=owner.id)

    activity = await services.create_activity(
        db, workspace.id, lead.id, manager,
        {"type": "task", "body": "Моя задача", "payload_json": {"title": "Моя задача"}},
    )
    assert activity.assignee_user_id == manager.id
