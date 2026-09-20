"""Второй проход: корректные тела там, где чужого остановила только валидация."""
from __future__ import annotations
import logging, uuid
import pytest
from httpx import ASGITransport, AsyncClient
import app.main  # noqa
from tests.conftest import POSTGRES_AVAILABLE
from tests.recon_sec01_lead_scoped import _user, _lead, _call

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="pg")


@skip_no_pg
@pytest.mark.asyncio
async def test_probe(db, workspace):
    logging.getLogger("httpx").setLevel(logging.WARNING)
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    lead = await _lead(db, workspace.id, owner.id)

    from app.notes.models import LeadNote
    note = LeadNote(
        workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
        text="Секретная заметка",
    )
    db.add(note)
    await db.flush()

    L = str(lead.id)
    cases = [
        ("POST", f"/leads/{L}/notes", {"text": "Я тут был"}),
        ("PATCH", f"/leads/{L}/notes/{note.id}", {"text": "Переписал чужое"}),
        ("DELETE", f"/leads/{L}/notes/{note.id}", None),
        ("POST", f"/leads/{L}/contacts", {"name": "Подставной ЛПР"}),
        ("POST", f"/leads/{L}/followups", {"name": "Чужое касание"}),
    ]
    print("\n--- корректное тело, действует чужой менеджер ---")
    for method, path, body in cases:
        try:
            res = await _call(db, stranger, method, path, body)
            code = res.status_code
            detail = ""
            if code >= 400:
                try:
                    detail = str(res.json())[:70]
                except Exception:
                    detail = res.text[:70]
        except Exception as exc:
            code, detail = f"EXC:{type(exc).__name__}", str(exc)[:70]
        print(f"  {method:7} {path.replace(L, '<lead>'):48} → {code} {detail}")

    await db.refresh(note)
    print(f"\n  заметка владельца после чужого PATCH: {note.text!r}")
