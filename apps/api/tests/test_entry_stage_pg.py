"""Воронка, где «Не отвечает» стоит самым левым (так в рабочей CRM).

Новая заявка встаёт на «Не отвечает», обработанную менеджер переводит на
«Первый контакт». Закреплено:
- «Не отвечает» и «Первый контакт» — ещё не сделки, в «застрявшие» не идут
  (27.11.2026 сводка писала «265 сделок застряли»);
- новые лиды встают на самый левый столбец, а во «Входящих» висят только
  заявки на нём (28.11.2026 после PR #248 туда вернулись 76 обработанных
  заявок с «Первого контакта»). Needs PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _pipeline(db, workspace):
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="B2B", type="sales", position=0)
    db.add(p)
    await db.flush()
    names = ["Не отвечает", "Первый контакт", "Квалификация"]
    stages = {n: Stage(pipeline_id=p.id, name=n, position=i) for i, n in enumerate(names)}
    stages["Выиграно"] = Stage(pipeline_id=p.id, name="Выиграно", position=3, is_won=True)
    db.add_all(stages.values())
    workspace.default_pipeline_id = p.id
    await db.flush()
    return p, stages


@skip_no_pg
@pytest.mark.asyncio
async def test_stuck_count_skips_entry_and_holding_stages(db, workspace, user):
    from app.company import repositories as repo
    from app.leads.models import Lead

    p, stages = await _pipeline(db, workspace)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    for name in ("Не отвечает", "Первый контакт", "Первый контакт", "Квалификация"):
        db.add(Lead(
            workspace_id=workspace.id, company_name=f"{name} {uuid.uuid4().hex[:4]}",
            assignment_status="assigned", assigned_to=user.id, assigned_at=old,
            pipeline_id=p.id, stage_id=stages[name].id, created_at=old,
        ))
    await db.flush()

    assert await repo.stuck_count(db, workspace_id=workspace.id) == 1
    assert await repo.first_stage_idle_count(db, workspace_id=workspace.id) == 3


@skip_no_pg
@pytest.mark.asyncio
async def test_new_leads_land_on_the_leftmost_stage(db, workspace):
    from app.pipelines.repositories import get_default_first_stage

    p, stages = await _pipeline(db, workspace)

    assert await get_default_first_stage(db, workspace.id) == (p.id, stages["Не отвечает"].id)


@skip_no_pg
@pytest.mark.asyncio
async def test_inbox_drops_request_moved_to_first_contact(db, workspace):
    from app.forms import inbox
    from app.forms.models import FormSubmission, WebForm
    from app.leads.models import Lead

    p, stages = await _pipeline(db, workspace)
    form = WebForm(
        workspace_id=workspace.id, name="Сайт",
        slug=f"site-{uuid.uuid4().hex[:6]}", fields_json=[],
    )
    db.add(form)
    await db.flush()
    leads = {
        name: Lead(
            workspace_id=workspace.id, company_name=name, assignment_status="pool",
            pipeline_id=p.id, stage_id=stages[stage].id,
        )
        for name, stage in (("Ждёт звонка", "Не отвечает"), ("Уже обработали", "Первый контакт"))
    }
    db.add_all(leads.values())
    await db.flush()
    for lead in leads.values():
        db.add(FormSubmission(web_form_id=form.id, lead_id=lead.id, raw_payload={}))
    await db.flush()

    items, total = await inbox.list_inbox(db, workspace_id=workspace.id, seen_at=None)
    assert [it["company_name"] for it in items] == ["Ждёт звонка"]
    assert total == 1

