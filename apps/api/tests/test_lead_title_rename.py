"""Название карточки лида: менеджер правит его и у лида, привязанного к
компании; переименование компании не затирает название, изменённое вручную."""
from __future__ import annotations

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.companies.models import Company
from app.companies.schemas import CompanyUpdate
from app.companies.services import update_company
from app.leads.models import Lead
from app.leads.schemas import LeadUpdate
from app.leads.services import update_lead

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _linked_lead(db, workspace_id, name="Анжелика"):
    company = Company(workspace_id=workspace_id, name=name, normalized_name=name.lower())
    db.add(company)
    await db.flush()
    lead = Lead(workspace_id=workspace_id, company_name=name, company_id=company.id,
                assignment_status="pool", tags_json=[])
    db.add(lead)
    await db.flush()
    return company, lead


@skip_no_pg
async def test_linked_lead_title_can_be_renamed(db, workspace):
    _, lead = await _linked_lead(db, workspace.id)

    out = await update_lead(db, workspace.id, lead.id,
                            LeadUpdate(company_name="  Анжелика — кофейня, 3 точки  "))

    assert out.company_name == "Анжелика — кофейня, 3 точки"


@skip_no_pg
async def test_empty_title_is_rejected(db, workspace):
    _, lead = await _linked_lead(db, workspace.id)

    with pytest.raises(ValueError):
        await update_lead(db, workspace.id, lead.id, LeadUpdate(company_name="   "))
    await db.refresh(lead)
    assert lead.company_name == "Анжелика"


@skip_no_pg
async def test_company_rename_keeps_hand_edited_titles(db, workspace):
    company, untouched = await _linked_lead(db, workspace.id, name="Кофе Хаус")
    edited = Lead(workspace_id=workspace.id, company_name="Кофе Хаус — 12 точек, QSR",
                  company_id=company.id, assignment_status="pool", tags_json=[])
    db.add(edited)
    await db.flush()

    await update_company(db, workspace_id=workspace.id, company_id=company.id,
                         data=CompanyUpdate(name="Coffee House"))

    await db.refresh(untouched)
    await db.refresh(edited)
    assert untouched.company_name == "Coffee House"
    assert edited.company_name == "Кофе Хаус — 12 точек, QSR"
