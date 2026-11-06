"""«Входящие» — список необработанных заявок, а не архив.

Заявка уходит из списка, когда её лида удалили или перевели дальше
первого этапа воронки (2026-11-02: тесты и переведённый в «Встречу»
лид висели во входящих). Needs PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


@skip_no_pg
@pytest.mark.asyncio
async def test_inbox_keeps_only_leads_on_first_stage(db, workspace):
    from app.forms import inbox
    from app.forms.models import FormSubmission, WebForm
    from app.leads.models import Lead
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="B2B", type="sales", position=0)
    db.add(p)
    await db.flush()
    first = Stage(pipeline_id=p.id, name="Первый контакт", position=0)
    meeting = Stage(pipeline_id=p.id, name="Встреча", position=1)
    db.add_all([first, meeting])
    form = WebForm(
        workspace_id=workspace.id, name="Сайт",
        slug=f"site-{uuid.uuid4().hex[:6]}", fields_json=[],
    )
    db.add(form)
    await db.flush()

    def lead(name, stage, deleted=False):
        return Lead(
            workspace_id=workspace.id, company_name=name, assignment_status="pool",
            pipeline_id=p.id, stage_id=stage.id,
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )

    waiting = lead("Ждёт звонка", first)
    moved = lead("Уже на встрече", meeting)
    deleted = lead("ТЕСТ", first, deleted=True)
    db.add_all([waiting, moved, deleted])
    await db.flush()
    for l in (waiting, moved, deleted):
        db.add(FormSubmission(web_form_id=form.id, lead_id=l.id, raw_payload={}))
    # Клиент отправил форму второй раз — карточка всё равно одна.
    db.add(FormSubmission(web_form_id=form.id, lead_id=waiting.id, raw_payload={}))
    await db.flush()

    items, total = await inbox.list_inbox(db, workspace_id=workspace.id, seen_at=None)
    assert [it["company_name"] for it in items] == ["Ждёт звонка"]
    assert total == 1
    assert await inbox.count_new(db, workspace_id=workspace.id, seen_at=None) == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_repeat_request_after_delete_is_a_new_lead(db, workspace):
    """Клиент, чей лид удалили, написал снова: это новый лид, и он виден во
    «Входящих». Живой лид с той же почтой, наоборот, новым не становится."""
    from app.forms import inbox
    from app.forms.lead_factory import create_lead_from_submission
    from app.forms.models import FormSubmission, WebForm
    from app.leads.models import Lead

    form = WebForm(
        workspace_id=workspace.id, name="Сайт",
        slug=f"site-{uuid.uuid4().hex[:6]}", fields_json=[],
    )
    db.add(form)
    await db.flush()
    payload = {"company_name": "Ромашка", "email": "client@romashka.ru"}

    async def submit():
        lead = await create_lead_from_submission(
            db, form=form, payload=payload, source_domain=None
        )
        db.add(FormSubmission(web_form_id=form.id, lead_id=lead.id, raw_payload=payload))
        await db.flush()
        return lead

    first = await submit()
    assert (await submit()).id == first.id  # живой лид: заявка к нему же

    first.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    second = await submit()
    assert second.id != first.id
    assert second.deleted_at is None

    assert (await db.get(Lead, first.id)).deleted_at is not None
    items, total = await inbox.list_inbox(db, workspace_id=workspace.id, seen_at=None)
    assert total == 1 and items[0]["lead_id"] == second.id
