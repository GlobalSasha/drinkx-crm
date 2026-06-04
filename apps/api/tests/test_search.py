"""Global search — the file result arm (DB-backed, needs pg_trgm).

Global search shipped with no tests (the trgm mode needs the pg_trgm extension,
which the create_all test DB lacked until conftest started installing it). These
cover the new `file` arm in both modes plus a company-hit regression check.
"""
from __future__ import annotations

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.activity.models import Activity, ActivityType
from app.companies.models import Company
from app.leads.models import Lead
from app.search.repositories import search

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


def _lead(workspace_id, **kw):
    base = dict(workspace_id=workspace_id, company_name="Acme", assignment_status="pool", tags_json=[])
    base.update(kw)
    return Lead(**base)


def _file(lead_id, *, file_name, extracted_text=None):
    payload = {"file_name": file_name, "parent_task_id": "t1"}
    if extracted_text is not None:
        payload["extracted_text"] = extracted_text
    return Activity(
        lead_id=lead_id,
        type=ActivityType.file.value,
        file_url=f"lead-files/{file_name}",
        file_kind="pdf",
        payload_json=payload,
    )


@skip_no_pg
async def test_search_file_by_filename(db, workspace):
    lead = _lead(workspace.id, company_name="ООО Ромашка")
    db.add(lead)
    await db.flush()
    db.add(_file(lead.id, file_name="Контракт-2026.pdf"))
    await db.flush()

    rows, mode = await search(db, workspace_id=workspace.id, q="Контракт", limit=20)
    assert mode == "trgm"
    files = [r for r in rows if r["type"] == "file"]
    assert any(r["title"] == "Контракт-2026.pdf" for r in files)
    hit = next(r for r in files if r["title"] == "Контракт-2026.pdf")
    assert hit["subtitle"] == "ООО Ромашка"          # which lead the file belongs to
    assert hit["url"] == f"/leads/{lead.id}?tab=tasks"


@skip_no_pg
async def test_search_file_by_content(db, workspace):
    lead = _lead(workspace.id)
    db.add(lead)
    await db.flush()
    db.add(_file(lead.id, file_name="doc.pdf", extracted_text="Договор поставки кофейных станций"))
    await db.flush()

    # A word that only appears in the extracted text, not the filename.
    rows, _ = await search(db, workspace_id=workspace.id, q="кофейных", limit=20)
    assert any(r["type"] == "file" and r["title"] == "doc.pdf" for r in rows)


@skip_no_pg
async def test_search_file_ilike_mode(db, workspace):
    lead = _lead(workspace.id)
    db.add(lead)
    await db.flush()
    db.add(_file(lead.id, file_name="report.pdf", extracted_text="quarterly numbers"))
    await db.flush()

    # 2-char query → ilike mode (no trigram); still matches content.
    rows, mode = await search(db, workspace_id=workspace.id, q="qu", limit=20)
    assert mode == "ilike"
    assert any(r["type"] == "file" and r["title"] == "report.pdf" for r in rows)


@skip_no_pg
async def test_search_file_scoped_to_workspace(db, workspace):
    from app.auth.models import Workspace

    other = Workspace(name="Other", plan="pro", sprint_capacity_per_week=20)
    db.add(other)
    await db.flush()
    foreign_lead = _lead(other.id, company_name="Foreign")
    db.add(foreign_lead)
    await db.flush()
    db.add(_file(foreign_lead.id, file_name="secret.pdf", extracted_text="конфиденциально"))
    await db.flush()

    rows, _ = await search(db, workspace_id=workspace.id, q="конфиденциально", limit=20)
    assert not any(r["type"] == "file" for r in rows)


@skip_no_pg
async def test_search_company_hit_still_works(db, workspace):
    # Regression: the existing arms keep working after adding the file arm.
    db.add(Company(workspace_id=workspace.id, name="Ромашка Трейд", normalized_name="ромашка трейд"))
    await db.flush()

    rows, mode = await search(db, workspace_id=workspace.id, q="Ромашка", limit=20)
    assert mode == "trgm"
    assert any(r["type"] == "company" and "Ромашка" in r["title"] for r in rows)
