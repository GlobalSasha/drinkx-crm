"""«Мои лиды» на телефоне: список отдаёт срок ближайшей открытой задачи,
признак открытой задачи и телефон основного контакта (22.11.2026)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="Requires Postgres")


async def _lead(db, workspace_id, user_id, name):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id, {"company_name": name},
        assigned_to=user_id, assignment_status="assigned",
    )


async def _task(db, lead, *, due=None, done=False, archived=False):
    from app.activity.models import Activity

    db.add(Activity(
        lead_id=lead.id, workspace_id=lead.workspace_id, type="task",
        payload_json={}, task_due_at=due, task_done=done,
        archived_at=datetime.now(timezone.utc) if archived else None,
        body="t",
    ))
    await db.flush()


@skip_no_pg
async def test_list_returns_nearest_open_task_and_contact_phone(db, workspace, user):
    from app.contacts.models import Contact
    from app.leads import repositories as repo

    now = datetime.now(timezone.utc).replace(microsecond=0)
    a = await _lead(db, workspace.id, user.id, "A")
    b = await _lead(db, workspace.id, user.id, "B")
    c = await _lead(db, workspace.id, user.id, "C")

    # A: nearest open task wins; done and archived ones are ignored.
    await _task(db, a, due=now + timedelta(days=3))
    await _task(db, a, due=now + timedelta(days=1))
    await _task(db, a, due=now - timedelta(days=5), done=True)
    await _task(db, a, due=now - timedelta(days=9), archived=True)
    # B: open task without a due date.
    await _task(db, b, due=None)
    # C: no tasks; primary contact with a phone.
    contact = Contact(
        id=uuid.uuid4(), workspace_id=workspace.id, lead_id=c.id,
        name="Иван", phone="+79001234567",
    )
    db.add(contact)
    await db.flush()
    c.primary_contact_id = contact.id
    await db.flush()

    items, _ = await repo.list_leads(db, workspace.id, page_size=50)
    by_id = {i.id: i for i in items}

    assert by_id[a.id].next_task_due_at == now + timedelta(days=1)
    assert by_id[a.id].has_open_task is True
    assert by_id[b.id].next_task_due_at is None
    assert by_id[b.id].has_open_task is True
    assert by_id[c.id].has_open_task is False
    assert by_id[c.id].primary_contact_phone == "+79001234567"


@skip_no_pg
async def test_list_item_schema_serializes_new_fields(db, workspace, user):
    from app.leads import repositories as repo
    from app.leads.schemas import LeadListItemOut

    lead = await _lead(db, workspace.id, user.id, "D")
    await _task(db, lead, due=datetime(2026, 12, 1, tzinfo=timezone.utc))
    items, _ = await repo.list_leads(db, workspace.id)
    out = LeadListItemOut.model_validate(next(i for i in items if i.id == lead.id))
    assert out.has_open_task is True
    assert out.next_task_due_at == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert out.primary_contact_phone is None
