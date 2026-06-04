"""Lead merge (Odoo _merge_opportunity pattern) — DB-backed."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.conftest import POSTGRES_AVAILABLE
from app.leads.models import Lead
from app.activity.models import Activity
from app.contacts.models import Contact
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.leads.dedup import MergeError, merge_leads

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


def _lead(workspace_id, **kw):
    base = dict(workspace_id=workspace_id, company_name="Acme", assignment_status="pool", tags_json=[])
    base.update(kw)
    return Lead(**base)


@skip_no_pg
async def test_merge_basic(db, workspace):
    master = _lead(workspace.id, company_name="Acme", tags_json=["a"])
    dup = _lead(
        workspace.id,
        company_name="Acme Dup",
        email="ivan@acme.ru",
        phone="89161234567",
        city="Москва",
        tags_json=["b"],
    )
    db.add_all([master, dup])
    await db.flush()

    db.add(Activity(lead_id=dup.id, type="comment", body="hi"))
    db.add(Contact(lead_id=dup.id, workspace_id=workspace.id, name="Ivan"))
    await db.flush()

    result = await merge_leads(
        db, workspace_id=workspace.id, master_id=master.id, duplicate_ids=[dup.id], user_id=None
    )

    # Master filled empty fields from the dup (+ normalized keys via @validates).
    assert result.id == master.id
    assert master.email == "ivan@acme.ru"
    assert master.email_normalized == "ivan@acme.ru"
    assert master.email_domain_criterion == "acme.ru"
    assert master.phone_e164 == "+79161234567"
    assert master.city == "Москва"
    assert set(master.tags_json) == {"a", "b"}

    # Dup archived + pointed at the survivor (soft, reversible).
    assert dup.archived_at is not None
    assert dup.merged_into_id == master.id

    # History re-pointed to master; nothing left on the dup.
    master_acts = (
        await db.execute(select(Activity).where(Activity.lead_id == master.id))
    ).scalars().all()
    types = [a.type for a in master_acts]
    assert "comment" in types   # moved
    assert "system" in types    # audit trail
    master_contacts = (
        await db.execute(select(Contact).where(Contact.lead_id == master.id))
    ).scalars().all()
    assert any(c.name == "Ivan" for c in master_contacts)
    dup_acts = (
        await db.execute(select(Activity).where(Activity.lead_id == dup.id))
    ).scalars().all()
    assert dup_acts == []


@skip_no_pg
async def test_merge_keeps_master_nonempty_fields(db, workspace):
    master = _lead(workspace.id, email="master@acme.ru", city="СПб")
    dup = _lead(workspace.id, email="dup@acme.ru", city="Москва")
    db.add_all([master, dup])
    await db.flush()

    await merge_leads(
        db, workspace_id=workspace.id, master_id=master.id, duplicate_ids=[dup.id], user_id=None
    )
    # Master already had email + city → keep them, don't overwrite from dup.
    assert master.email == "master@acme.ru"
    assert master.city == "СПб"


@skip_no_pg
async def test_merge_repoints_followups(db, workspace):
    master = _lead(workspace.id)
    dup = _lead(workspace.id, company_name="Acme Dup")
    db.add_all([master, dup])
    await db.flush()

    db.add(Followup(lead_id=dup.id, name="Позвонить ЛПР"))
    await db.flush()

    await merge_leads(
        db, workspace_id=workspace.id, master_id=master.id, duplicate_ids=[dup.id], user_id=None
    )

    # The dup's open follow-up now belongs to the master (history re-pointed).
    master_followups = (
        await db.execute(select(Followup).where(Followup.lead_id == master.id))
    ).scalars().all()
    assert any(f.name == "Позвонить ЛПР" for f in master_followups)
    dup_followups = (
        await db.execute(select(Followup).where(Followup.lead_id == dup.id))
    ).scalars().all()
    assert dup_followups == []


@skip_no_pg
async def test_merge_no_valid_dups_raises(db, workspace):
    master = _lead(workspace.id)
    db.add(master)
    await db.flush()
    with pytest.raises(MergeError):
        await merge_leads(
            db, workspace_id=workspace.id, master_id=master.id,
            duplicate_ids=[uuid.uuid4()], user_id=None,
        )


@skip_no_pg
async def test_merge_unknown_master_raises(db, workspace):
    with pytest.raises(MergeError):
        await merge_leads(
            db, workspace_id=workspace.id, master_id=uuid.uuid4(),
            duplicate_ids=[uuid.uuid4()], user_id=None,
        )
