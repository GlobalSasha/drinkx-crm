"""Разведка: свой лид + чужой дочерний объект.

Страж на роутере проверяет доступ к лиду из пути. Он ничего не говорит о
том, принадлежит ли дочерний объект именно этому лиду. Если обработчик
ищет объект только по его id, менеджер подставит свой lead_id и чужой
contact_id — и обойдёт защиту.

    REQUIRE_TEST_DB=1 python -m pytest tests/recon_sec01_child_ids.py -q -s
"""
from __future__ import annotations

import logging
import uuid

import pytest

import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE
from tests.recon_sec01_lead_scoped import _call, _lead, _user

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


@skip_no_pg
@pytest.mark.asyncio
async def test_recon(db, workspace):
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from app.activity.models import Activity, ActivityType
    from app.contacts.models import Contact
    from app.followups.models import Followup
    from app.notes.models import LeadNote
    from app.quote.models import Quote

    me = await _user(db, workspace.id, "manager", "Me")
    peer = await _user(db, workspace.id, "manager", "Peer")
    mine = await _lead(db, workspace.id, me.id, name="Мой лид")
    theirs = await _lead(db, workspace.id, peer.id, name="Чужой лид")

    contact = Contact(workspace_id=workspace.id, lead_id=theirs.id, name="Чужой ЛПР")
    followup = Followup(
        lead_id=theirs.id, name="Чужое касание", reminder_kind="manager", status="pending"
    )
    note = LeadNote(
        workspace_id=workspace.id, lead_id=theirs.id, user_id=peer.id, text="Чужая заметка"
    )
    task = Activity(
        workspace_id=None, lead_id=theirs.id, user_id=peer.id,
        type=ActivityType.task.value, payload_json={"title": "Чужая задача"},
        body="Чужая задача", task_done=False,
    )
    quote = Quote(
        workspace_id=workspace.id, lead_id=theirs.id, created_by=peer.id,
        number="КП-999", status="draft", subtotal=0, total=0,
    )
    for row in (contact, followup, note, task, quote):
        db.add(row)
    await db.flush()

    M, T = str(mine.id), str(theirs.id)
    cases = [
        ("PATCH", f"/leads/{M}/contacts/{contact.id}", {"name": "Перехват"}),
        ("DELETE", f"/leads/{M}/contacts/{contact.id}", None),
        ("PATCH", f"/leads/{M}/followups/{followup.id}", {"name": "Перехват"}),
        ("DELETE", f"/leads/{M}/followups/{followup.id}", None),
        ("POST", f"/leads/{M}/followups/{followup.id}/complete", None),
        ("PATCH", f"/leads/{M}/notes/{note.id}", {"text": "Перехват"}),
        ("DELETE", f"/leads/{M}/notes/{note.id}", None),
        ("PATCH", f"/leads/{M}/activities/{task.id}", {"body": "Перехват"}),
        ("POST", f"/leads/{M}/activities/{task.id}/complete-task", None),
        ("DELETE", f"/leads/{M}/activities/{task.id}", None),
        ("GET", f"/leads/{M}/tasks/{task.id}/files", None),
        ("GET", f"/api/quotes/{quote.id}", None),
        ("PATCH", f"/api/quotes/{quote.id}", {"status": "sent"}),
        ("DELETE", f"/api/quotes/{quote.id}", None),
    ]

    print("\n--- свой lead_id, чужой дочерний объект; действует владелец своего лида ---")
    bad = []
    for method, path, body in cases:
        try:
            res = await _call(db, me, method, path, body)
            code = res.status_code
        except Exception as exc:  # noqa: BLE001
            code = f"EXC:{type(exc).__name__}"
        short = path.replace(M, "<мой>").replace(T, "<чужой>")
        print(f"  {method:7} {short:52} → {code}")
        if isinstance(code, int) and code < 400:
            bad.append((method, short, code))

    print(f"\nпрошло без отказа: {len(bad)}")
    for method, path, code in bad:
        print(f"  ! {method:7} {path} → {code}")
