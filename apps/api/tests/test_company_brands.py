"""«Лиды по брендам» на /today: что считается активным и кто это видит."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from app.company import services as svc
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _stages(db, workspace_id):
    from app.pipelines.models import Pipeline, Stage

    pipeline = Pipeline(workspace_id=workspace_id, name="Sales", type="sales", position=0)
    db.add(pipeline)
    await db.flush()
    working = Stage(pipeline_id=pipeline.id, name="В работе", position=0, color="#ccc", rot_days=14)
    won = Stage(pipeline_id=pipeline.id, name="Выиграно", position=1, color="#ccc", rot_days=14, is_won=True)
    lost = Stage(pipeline_id=pipeline.id, name="Отказ", position=2, color="#ccc", rot_days=14, is_lost=True)
    db.add_all([working, won, lost])
    await db.flush()
    return pipeline, working, won, lost


async def _lead(db, workspace_id, **fields):
    from app.leads.models import Lead

    fields.setdefault("assignment_status", "pool")
    lead = Lead(workspace_id=workspace_id, company_name=f"Компания {uuid.uuid4().hex[:6]}", **fields)
    db.add(lead)
    await db.flush()
    return lead


async def _user(db, workspace_id, role):
    from app.auth.models import User

    user = User(
        workspace_id=workspace_id,
        email=f"{role}-{uuid.uuid4().hex[:6]}@example.com",
        name=role,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def _get_brands(db, actor):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/company/brands")
    finally:
        app.dependency_overrides.clear()


@skip_no_pg
async def test_counts_only_active_leads_of_this_workspace(db, workspace, user):
    from app.auth.models import Workspace

    now = datetime.now(timezone.utc)
    pipeline, working, won, lost = await _stages(db, workspace.id)
    on_stage = {"pipeline_id": pipeline.id, "stage_id": working.id}

    # Считаются: лид без этапа в базе, лид у менеджера.
    await _lead(db, workspace.id, deal_brand="AeroMilk")
    await _lead(db, workspace.id, deal_brand="AeroMilk", assignment_status="assigned", assigned_to=user.id, **on_stage)
    await _lead(db, workspace.id, deal_brand="DrinkX", **on_stage)
    await _lead(db, workspace.id)
    await _lead(db, workspace.id, **on_stage)
    await _lead(db, workspace.id, deal_equipment="S400")

    # Не считаются: у каждого бренд, который иначе исказил бы число.
    await _lead(db, workspace.id, deal_brand="AeroMilk", deleted_at=now)
    await _lead(db, workspace.id, deal_brand="AeroMilk", archived_at=now)
    await _lead(db, workspace.id, deal_brand="AeroMilk", assignment_status="deleted")
    await _lead(db, workspace.id, deal_brand="DrinkX", pipeline_id=pipeline.id, stage_id=won.id)
    await _lead(db, workspace.id, deal_brand="DrinkX", pipeline_id=pipeline.id, stage_id=lost.id)
    await _lead(db, workspace.id, deal_brand="DrinkX", won_at=now, **on_stage)
    await _lead(db, workspace.id, lost_at=now, **on_stage)

    other = Workspace(name="Чужое пространство", domain=f"{uuid.uuid4().hex[:8]}.example.com")
    db.add(other)
    await db.flush()
    await _lead(db, other.id, deal_brand="AeroMilk")

    out = await svc.brands(db, workspace_id=workspace.id)

    assert out == {"aeromilk": 2, "drinkx": 1, "no_brand": 3}


@skip_no_pg
@pytest.mark.parametrize("role", ["admin", "head"])
async def test_leadership_gets_the_numbers(db, workspace, role):
    await _lead(db, workspace.id, deal_brand="DrinkX")

    response = await _get_brands(db, await _user(db, workspace.id, role))

    assert response.status_code == 200, response.text
    assert response.json() == {"aeromilk": 0, "drinkx": 1, "no_brand": 0}


@skip_no_pg
async def test_manager_is_refused(db, workspace):
    response = await _get_brands(db, await _user(db, workspace.id, "manager"))

    assert response.status_code == 403
