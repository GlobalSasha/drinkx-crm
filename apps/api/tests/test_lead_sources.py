"""Lead-source dictionary (Sprint CEO G1) — DB-backed."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.conftest import POSTGRES_AVAILABLE

# Trigger ORM mapper configuration (Lead string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401

# Module-level so create_all (session fixture) registers the lead_sources table.
from app.lead_sources.models import DEFAULT_LEAD_SOURCES, LeadSource  # noqa: F401
from app.lead_sources import repositories as repo
from app.lead_sources import services as svc
from app.lead_sources.schemas import LeadSourceCreateIn, LeadSourceUpdateIn

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


@skip_no_pg
async def test_seed_defaults_is_idempotent(db, workspace):
    created = await repo.seed_defaults(db, workspace_id=workspace.id)
    assert created == len(DEFAULT_LEAD_SOURCES)

    # Second call adds nothing — no duplicate rows.
    again = await repo.seed_defaults(db, workspace_id=workspace.id)
    assert again == 0

    n = (
        await db.execute(
            select(func.count()).select_from(LeadSource).where(
                LeadSource.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert n == len(DEFAULT_LEAD_SOURCES)

    # Яндекс Директ is the paid + system seed.
    direct = (
        await db.execute(
            select(LeadSource).where(
                LeadSource.workspace_id == workspace.id, LeadSource.name == "Яндекс Директ"
            )
        )
    ).scalar_one()
    assert direct.is_paid is True
    assert direct.is_system is True


@skip_no_pg
async def test_create_then_name_conflict(db, workspace):
    src = await svc.create_source(
        db, workspace_id=workspace.id, payload=LeadSourceCreateIn(name="Партнёр", is_paid=False)
    )
    assert src.is_system is False
    assert src.is_active is True

    with pytest.raises(svc.LeadSourceNameConflict):
        await svc.create_source(
            db, workspace_id=workspace.id, payload=LeadSourceCreateIn(name="Партнёр")
        )


@skip_no_pg
async def test_list_active_only(db, workspace):
    await svc.create_source(db, workspace_id=workspace.id, payload=LeadSourceCreateIn(name="A"))
    b = await svc.create_source(db, workspace_id=workspace.id, payload=LeadSourceCreateIn(name="B"))
    await svc.update_source(
        db, source_id=b.id, workspace_id=workspace.id, payload=LeadSourceUpdateIn(is_active=False)
    )

    all_sources = await svc.list_sources(db, workspace_id=workspace.id)
    active = await svc.list_sources(db, workspace_id=workspace.id, active_only=True)
    assert {s.name for s in all_sources} == {"A", "B"}
    assert {s.name for s in active} == {"A"}


@skip_no_pg
async def test_delete_system_blocked_but_custom_ok(db, workspace):
    await repo.seed_defaults(db, workspace_id=workspace.id)
    direct = await repo.get_by_name(db, workspace_id=workspace.id, name="Яндекс Директ")
    with pytest.raises(svc.LeadSourceIsSystem):
        await svc.delete_source(db, source_id=direct.id, workspace_id=workspace.id)

    custom = await svc.create_source(
        db, workspace_id=workspace.id, payload=LeadSourceCreateIn(name="Сарафан")
    )
    await svc.delete_source(db, source_id=custom.id, workspace_id=workspace.id)
    assert await repo.get_by_name(db, workspace_id=workspace.id, name="Сарафан") is None
