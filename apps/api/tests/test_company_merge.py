"""Company merge — folds a source company into a target (DB-backed).

`app/companies/merge.py::merge_into` is destructive (archives the source,
re-points its leads + contacts, transfers INN/KPP, snapshots historical lead
names) and was shipped without tests. Mirrors the lead-merge test pattern.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.companies.models import Company
from app.contacts.models import Contact
from app.leads.models import Lead
from app.pipelines.models import Stage
from app.companies.merge import InnConflict, MergeNotPossible, merge_into

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


def _company(workspace_id, name, **kw):
    return Company(workspace_id=workspace_id, name=name, normalized_name=name.lower(), **kw)


def _lead(workspace_id, **kw):
    base = dict(workspace_id=workspace_id, company_name="Acme", assignment_status="pool", tags_json=[])
    base.update(kw)
    return Lead(**base)


@skip_no_pg
async def test_merge_basic_repoints_and_archives(db, workspace, admin_user, pipeline):
    pipeline_obj, stage = pipeline
    src = _company(workspace.id, "Acme Old")
    tgt = _company(workspace.id, "Acme")
    db.add_all([src, tgt])
    await db.flush()

    lead = _lead(workspace.id, company_name="Acme Old", company_id=src.id, stage_id=stage.id)
    db.add(lead)
    await db.flush()
    contact = Contact(workspace_id=workspace.id, lead_id=lead.id, name="Иван", company_id=src.id)
    db.add(contact)
    await db.flush()

    result = await merge_into(
        db, workspace_id=workspace.id, user_id=admin_user.id, source_id=src.id, target_id=tgt.id
    )

    assert result.id == tgt.id
    # Source archived.
    assert src.is_archived is True
    assert src.archived_at is not None
    # Active lead re-pointed + renamed to the target's name.
    await db.refresh(lead)
    assert lead.company_id == tgt.id
    assert lead.company_name == "Acme"
    # Contact re-pointed.
    await db.refresh(contact)
    assert contact.company_id == tgt.id


@skip_no_pg
async def test_merge_same_id_raises(db, workspace):
    c = _company(workspace.id, "Acme")
    db.add(c)
    await db.flush()
    with pytest.raises(MergeNotPossible):
        await merge_into(db, workspace_id=workspace.id, user_id=None, source_id=c.id, target_id=c.id)


@skip_no_pg
async def test_merge_missing_raises(db, workspace):
    tgt = _company(workspace.id, "Acme")
    db.add(tgt)
    await db.flush()
    with pytest.raises(MergeNotPossible):
        await merge_into(
            db, workspace_id=workspace.id, user_id=None, source_id=uuid.uuid4(), target_id=tgt.id
        )


@skip_no_pg
async def test_merge_inn_conflict_blocks_without_force(db, workspace):
    src = _company(workspace.id, "Acme Old", inn="7700000001")
    tgt = _company(workspace.id, "Acme", inn="7700000002")
    db.add_all([src, tgt])
    await db.flush()
    with pytest.raises(InnConflict):
        await merge_into(
            db, workspace_id=workspace.id, user_id=None, source_id=src.id, target_id=tgt.id
        )
    # force=True overrides the guard.
    result = await merge_into(
        db, workspace_id=workspace.id, user_id=None, source_id=src.id, target_id=tgt.id, force=True
    )
    assert result.id == tgt.id
    assert src.is_archived is True


@skip_no_pg
async def test_merge_transfers_inn_and_kpp(db, workspace):
    src = _company(workspace.id, "Acme Old", inn="7700000001", kpp="770001001")
    tgt = _company(workspace.id, "Acme")  # no INN
    db.add_all([src, tgt])
    await db.flush()

    await merge_into(
        db, workspace_id=workspace.id, user_id=None, source_id=src.id, target_id=tgt.id
    )
    assert tgt.inn == "7700000001"
    assert tgt.kpp == "770001001"


@skip_no_pg
async def test_merge_terminal_lead_keeps_name_snapshot(db, workspace, pipeline):
    pipeline_obj, active_stage = pipeline
    won_stage = Stage(pipeline_id=pipeline_obj.id, name="Закрыто (won)", position=9, is_won=True)
    db.add(won_stage)
    await db.flush()

    src = _company(workspace.id, "Acme Old")
    tgt = _company(workspace.id, "Acme")
    db.add_all([src, tgt])
    await db.flush()

    won_lead = _lead(
        workspace.id, company_name="Acme Old", company_id=src.id, stage_id=won_stage.id
    )
    db.add(won_lead)
    await db.flush()

    await merge_into(
        db, workspace_id=workspace.id, user_id=None, source_id=src.id, target_id=tgt.id
    )
    await db.refresh(won_lead)
    # company_id moves, but the historical (won) name snapshot is preserved.
    assert won_lead.company_id == tgt.id
    assert won_lead.company_name == "Acme Old"
