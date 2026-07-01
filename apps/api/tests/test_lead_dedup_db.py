"""Lead duplicate DETECTION against a real Postgres (Odoo dedup pattern).

`test_lead_dedup.py` exercises `find_duplicates` with a mocked session, so the
actual SQL — workspace scoping, archived exclusion, the OR-combined keys
(phone_e164 / company_id / email_domain_criterion), self-exclusion and the
dupe-bomb guard — never runs. These DB-backed tests close that gap (the merge
side already had `test_lead_merge.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.companies.models import Company
from app.leads.models import Lead
from app.leads.dedup import DUP_LIMIT, find_duplicates

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


def _lead(workspace_id, **kw):
    base = dict(workspace_id=workspace_id, company_name="Acme", assignment_status="pool", tags_json=[])
    base.update(kw)
    return Lead(**base)


async def _persist(db, *leads):
    db.add_all(leads)
    await db.flush()


@skip_no_pg
async def test_matches_on_phone(db, workspace):
    master = _lead(workspace.id, phone="89161234567")
    dup = _lead(workspace.id, company_name="Acme LLC", phone="+7 916 123-45-67")  # same E.164
    other = _lead(workspace.id, company_name="Other", phone="89990000000")
    await _persist(db, master, dup, other)

    res = await find_duplicates(db, master)
    ids = {lead.id for lead in res}
    assert dup.id in ids
    assert other.id not in ids
    assert master.id not in ids  # never matches itself


@skip_no_pg
async def test_matches_on_email_domain_but_not_freemail(db, workspace):
    master = _lead(workspace.id, email="ivan@acme.ru")
    same_domain = _lead(workspace.id, company_name="Acme LLC", email="petr@acme.ru")
    freemail = _lead(workspace.id, company_name="Gmail Co", email="someone@gmail.com")
    await _persist(db, master, same_domain, freemail)

    res = await find_duplicates(db, master)
    ids = {lead.id for lead in res}
    assert same_domain.id in ids
    assert freemail.id not in ids  # free-mail domain is not a dedup signal


@skip_no_pg
async def test_matches_on_company(db, workspace):
    company = Company(workspace_id=workspace.id, name="Acme", normalized_name="acme")
    db.add(company)
    await db.flush()
    master = _lead(workspace.id, company_id=company.id)
    dup = _lead(workspace.id, company_name="Acme (dup)", company_id=company.id)
    await _persist(db, master, dup)

    res = await find_duplicates(db, master)
    assert dup.id in {lead.id for lead in res}


@skip_no_pg
async def test_excludes_archived(db, workspace):
    master = _lead(workspace.id, phone="89161234567")
    archived = _lead(
        workspace.id,
        company_name="Archived dup",
        phone="89161234567",
        archived_at=datetime.now(timezone.utc),
    )
    await _persist(db, master, archived)

    res = await find_duplicates(db, master)
    assert archived.id not in {lead.id for lead in res}


@skip_no_pg
async def test_excludes_trashed(db, workspace):
    # A soft-deleted (Trash) lead must not be suggested as a merge candidate (plan 009).
    master = _lead(workspace.id, phone="89161234567")
    trashed = _lead(
        workspace.id,
        company_name="Trashed dup",
        phone="89161234567",
        deleted_at=datetime.now(timezone.utc),
    )
    await _persist(db, master, trashed)

    res = await find_duplicates(db, master)
    assert trashed.id not in {lead.id for lead in res}


@skip_no_pg
async def test_scoped_to_workspace(db, workspace):
    from app.auth.models import Workspace

    other_ws = Workspace(name="Other WS", plan="pro", sprint_capacity_per_week=20)
    db.add(other_ws)
    await db.flush()

    master = _lead(workspace.id, email="ivan@acme.ru")
    foreign = _lead(other_ws.id, company_name="Acme Foreign", email="petr@acme.ru")
    await _persist(db, master, foreign)

    res = await find_duplicates(db, master)
    assert foreign.id not in {lead.id for lead in res}


@skip_no_pg
async def test_dupe_bomb_suppressed(db, workspace):
    # A key shared by a whole crowd (>= DUP_LIMIT) is noise, not a match.
    master = _lead(workspace.id, email="ivan@acme.ru")
    crowd = [
        _lead(workspace.id, company_name=f"Acme {i}", email=f"user{i}@acme.ru")
        for i in range(DUP_LIMIT)
    ]
    await _persist(db, master, *crowd)

    res = await find_duplicates(db, master)
    assert res == []
