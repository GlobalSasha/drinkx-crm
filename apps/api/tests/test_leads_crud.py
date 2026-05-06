"""Tests for Lead CRUD + Lead Pool API (Sprint 1.2 Task 2)."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_lead(db, workspace_id, **kwargs):
    """Create a Lead row directly via repo for test setup."""
    from app.leads import repositories as repo

    # Pop special kwargs that are repo-level keyword-only args
    assignment_status = kwargs.pop("assignment_status", "assigned")
    assigned_to = kwargs.pop("assigned_to", None)

    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db,
        workspace_id,
        payload,
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_create_lead_assigns_to_creator(db, workspace, user):
    """POST-equivalent: created lead is assigned to the creator."""
    from app.leads import services
    from app.leads.schemas import LeadCreate

    payload = LeadCreate(company_name="Acme Corp")
    lead = await services.create_lead(db, workspace.id, user.id, payload)

    assert lead.assignment_status == "assigned"
    assert lead.assigned_to == user.id
    assert lead.workspace_id == workspace.id
    assert lead.assigned_at is not None


@skip_no_pg
async def test_list_leads_filters_by_stage(db, workspace, user, pipeline):
    """Leads in stage A are not returned when filtering by stage B."""
    _, stage = pipeline
    # 2 leads in the stage, 1 without
    l1 = await _make_lead(db, workspace.id, company_name="StageA-1", stage_id=stage.id)
    l2 = await _make_lead(db, workspace.id, company_name="StageA-2", stage_id=stage.id)
    l3 = await _make_lead(db, workspace.id, company_name="NoStage")

    from app.leads import repositories as repo

    items, total = await repo.list_leads(db, workspace.id, stage_id=stage.id)
    ids = {i.id for i in items}
    assert l1.id in ids
    assert l2.id in ids
    assert l3.id not in ids
    assert total == 2


@skip_no_pg
async def test_list_leads_filters_by_segment_city_priority_deal_type(db, workspace, user):
    """Combined filter returns only exact-match leads."""
    await _make_lead(db, workspace.id, company_name="Match",
                     segment="HoReCa", city="Moscow", priority="A", deal_type="qsr")
    await _make_lead(db, workspace.id, company_name="NoMatch",
                     segment="Retail", city="SPb", priority="B", deal_type="enterprise_direct")

    from app.leads import repositories as repo

    items, total = await repo.list_leads(
        db, workspace.id,
        segment="HoReCa", city="Moscow", priority="A", deal_type="qsr",
    )
    assert total == 1
    assert items[0].company_name == "Match"


@skip_no_pg
async def test_list_leads_searches_by_q(db, workspace, user):
    """Substring search on company_name works."""
    await _make_lead(db, workspace.id, company_name="Alpha Beverages")
    await _make_lead(db, workspace.id, company_name="Beta Corp")

    from app.leads import repositories as repo

    items, total = await repo.list_leads(db, workspace.id, q="beverag")
    assert total == 1
    assert items[0].company_name == "Alpha Beverages"


@skip_no_pg
async def test_list_leads_pagination(db, workspace, user):
    """page_size=2, 5 leads → correct pages and total."""
    for i in range(5):
        await _make_lead(db, workspace.id, company_name=f"Lead {i}")

    from app.leads import repositories as repo

    page1, total = await repo.list_leads(db, workspace.id, page=1, page_size=2)
    page2, _ = await repo.list_leads(db, workspace.id, page=2, page_size=2)
    page3, _ = await repo.list_leads(db, workspace.id, page=3, page_size=2)

    assert total >= 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) >= 1


@skip_no_pg
async def test_get_lead_404_for_other_workspace(db, workspace, user):
    """Lead in workspace A must not be visible from workspace B."""
    from app.auth.models import Workspace
    from app.leads import repositories as repo

    ws_b = Workspace(name="WS-B", plan="free")
    db.add(ws_b)
    await db.flush()

    lead = await _make_lead(db, workspace.id, company_name="Private Lead")

    result = await repo.get_by_id(db, lead.id, ws_b.id)
    assert result is None


@skip_no_pg
async def test_update_lead_applies_only_provided_fields(db, workspace, user):
    """PATCH partial update does not clobber unset fields."""
    lead = await _make_lead(db, workspace.id, company_name="Original", city="Kazan", segment="HoReCa")

    from app.leads import repositories as repo
    from app.leads.schemas import LeadUpdate

    patch = LeadUpdate(city="Moscow")
    updated = await repo.update_lead(db, lead, {"city": "Moscow"})

    assert updated.city == "Moscow"
    assert updated.company_name == "Original"
    assert updated.segment == "HoReCa"


@skip_no_pg
async def test_delete_lead(db, workspace, user):
    """Deleting a lead makes get_by_id return None."""
    lead = await _make_lead(db, workspace.id, company_name="To Delete")
    lead_id = lead.id

    from app.leads import repositories as repo

    await repo.delete_lead(db, lead)

    result = await repo.get_by_id(db, lead_id, workspace.id)
    assert result is None


# ---------------------------------------------------------------------------
# Pool tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_list_pool_only_returns_pool_status(db, workspace, user):
    """list_pool returns only assignment_status='pool' leads."""
    await _make_lead(db, workspace.id, company_name="Pool1", assignment_status="pool")
    await _make_lead(db, workspace.id, company_name="Pool2", assignment_status="pool")
    await _make_lead(db, workspace.id, company_name="Assigned", assignment_status="assigned", assigned_to=user.id)

    from app.leads import repositories as repo

    items, total = await repo.list_pool(db, workspace.id)
    assert total == 2
    assert all(i.assignment_status == "pool" for i in items)


@skip_no_pg
async def test_list_pool_orders_by_fit_score_then_created(db, workspace):
    """Ordering: fit_score DESC NULLS LAST, then created_at ASC."""
    from app.leads.models import Lead

    # Insert with specific fit_scores; ordering is by fit_score then created_at
    l_high = Lead(workspace_id=workspace.id, company_name="High", assignment_status="pool", fit_score=8.00)
    db.add(l_high)
    await db.flush()

    l_low = Lead(workspace_id=workspace.id, company_name="Low", assignment_status="pool", fit_score=5.00)
    db.add(l_low)
    await db.flush()

    l_null = Lead(workspace_id=workspace.id, company_name="Null", assignment_status="pool", fit_score=None)
    db.add(l_null)
    await db.flush()

    from app.leads import repositories as repo

    items, _ = await repo.list_pool(db, workspace.id)
    names = [i.company_name for i in items]
    assert names.index("High") < names.index("Low")
    assert names.index("Low") < names.index("Null")


# ---------------------------------------------------------------------------
# Claim tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_claim_lead_pool_to_assigned(db, workspace, user):
    """Claiming a pool lead sets assigned_to and assignment_status=assigned."""
    lead = await _make_lead(db, workspace.id, company_name="ClaimMe", assignment_status="pool")

    from app.leads import repositories as repo

    claimed = await repo.claim_lead(db, lead.id, workspace.id, user.id)
    assert claimed is not None
    assert claimed.assignment_status == "assigned"
    assert claimed.assigned_to == user.id
    assert claimed.assigned_at is not None


@skip_no_pg
async def test_claim_lead_already_claimed_returns_409(db, workspace, user, admin_user):
    """Second claim of the same lead raises LeadAlreadyClaimed (→ 409)."""
    lead = await _make_lead(db, workspace.id, company_name="AlreadyClaimed", assignment_status="pool")

    from app.leads import repositories as repo, services

    # First claim
    await repo.claim_lead(db, lead.id, workspace.id, user.id)

    # Second claim attempt
    with pytest.raises(services.LeadAlreadyClaimed):
        await services.claim_lead(db, workspace.id, admin_user.id, lead.id)


# ---------------------------------------------------------------------------
# Sprint tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_sprint_claims_n_leads(db, workspace, user):
    """Sprint with limit=10 claims exactly 10 leads from a pool of 30."""
    for i in range(30):
        await _make_lead(db, workspace.id, company_name=f"Pool {i}",
                         assignment_status="pool", city="Moscow")

    from app.leads import repositories as repo

    claimed = await repo.claim_sprint(
        db, workspace.id, user.id,
        cities=["Moscow"], limit=10,
    )
    assert len(claimed) == 10
    assert all(l.assignment_status == "assigned" for l in claimed)
    assert all(l.assigned_to == user.id for l in claimed)


@skip_no_pg
async def test_sprint_respects_workspace_capacity_when_limit_none(db, workspace, user):
    """When limit=None, sprint falls back to workspace.sprint_capacity_per_week (20)."""
    for i in range(30):
        await _make_lead(db, workspace.id, company_name=f"Pool {i}",
                         assignment_status="pool", city="Sochi")

    from app.leads import services

    # workspace.sprint_capacity_per_week = 20 (set in conftest fixture)
    claimed = await services.claim_sprint(
        db, workspace.id, user.id,
        cities=["Sochi"], segment=None, limit=None,
    )
    assert len(claimed) == 20


@skip_no_pg
async def test_sprint_filters_by_cities(db, workspace, user):
    """Sprint only claims leads from the specified cities."""
    for i in range(5):
        await _make_lead(db, workspace.id, company_name=f"Moscow {i}",
                         assignment_status="pool", city="Moscow")
    for i in range(5):
        await _make_lead(db, workspace.id, company_name=f"SPb {i}",
                         assignment_status="pool", city="Saint Petersburg")

    from app.leads import repositories as repo

    claimed = await repo.claim_sprint(
        db, workspace.id, user.id,
        cities=["Moscow"], limit=10,
    )
    assert all(l.city == "Moscow" for l in claimed)


@skip_no_pg
async def test_sprint_filters_by_segment(db, workspace, user):
    """Sprint with segment= filters correctly."""
    for i in range(5):
        await _make_lead(db, workspace.id, company_name=f"HoReCa {i}",
                         assignment_status="pool", city="Moscow", segment="HoReCa")
    for i in range(5):
        await _make_lead(db, workspace.id, company_name=f"Retail {i}",
                         assignment_status="pool", city="Moscow", segment="Retail")

    from app.leads import repositories as repo

    claimed = await repo.claim_sprint(
        db, workspace.id, user.id,
        cities=["Moscow"], segment="HoReCa", limit=10,
    )
    assert all(l.segment == "HoReCa" for l in claimed)


@skip_no_pg
async def test_sprint_concurrent_no_double_claim(workspace, user, admin_user):
    """Two concurrent sprints on an overlapping pool → no lead claimed twice.

    This test requires FOR UPDATE SKIP LOCKED support (Postgres-only).
    Uses its own committed sessions to avoid cross-connection isolation issues.
    """
    from tests.conftest import _test_session_factory
    from app.leads.models import Lead
    from app.leads import repositories as repo

    ws_id = workspace.id
    user_id = user.id
    admin_id = admin_user.id

    # Setup: insert pool leads and commit so all connections can see them
    lead_ids = []
    async with _test_session_factory() as setup_session:
        for i in range(10):
            lead = Lead(
                workspace_id=ws_id,
                company_name=f"Concurrent {i}",
                assignment_status="pool",
                city="Novosibirsk",
            )
            setup_session.add(lead)
        await setup_session.flush()
        await setup_session.commit()

    async def sprint_for(uid):
        async with _test_session_factory() as session:
            return await repo.claim_sprint(
                session, ws_id, uid,
                cities=["Novosibirsk"], limit=8,
            )

    results = await asyncio.gather(
        sprint_for(user_id),
        sprint_for(admin_id),
    )
    all_ids = [lead.id for batch in results for lead in batch]
    # No duplicates — each lead claimed at most once
    assert len(all_ids) == len(set(all_ids))
    # Together they cannot claim more than the 10 available
    assert len(all_ids) <= 10

    # Cleanup committed data
    async with _test_session_factory() as cleanup:
        from sqlalchemy import delete
        await cleanup.execute(
            delete(Lead).where(Lead.workspace_id == ws_id, Lead.city == "Novosibirsk")
        )
        await cleanup.commit()


# ---------------------------------------------------------------------------
# Transfer tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_transfer_changes_assigned_to(db, workspace, user, admin_user):
    """Transferring a lead changes assigned_to and sets transferred_from."""
    lead = await _make_lead(
        db, workspace.id, company_name="Transfer Me",
        assignment_status="assigned", assigned_to=user.id,
    )

    from app.leads import services

    transferred = await services.transfer_lead(
        db,
        workspace.id,
        current_user_id=user.id,
        current_user_role=user.role,
        lead_id=lead.id,
        to_user_id=admin_user.id,
        comment="passing on",
    )

    assert transferred.assigned_to == admin_user.id
    assert transferred.transferred_from == user.id
    assert transferred.transferred_at is not None


@skip_no_pg
async def test_transfer_other_workspace_user_400(db, workspace, user):
    """Transferring to a user in a different workspace raises TransferTargetInvalid."""
    from app.auth.models import User, Workspace
    from app.leads import services

    ws_other = Workspace(name="Other WS", plan="free")
    db.add(ws_other)
    await db.flush()

    other_user = User(
        workspace_id=ws_other.id,
        email=f"other-{uuid.uuid4().hex[:8]}@test.com",
        name="Other",
        role="manager",
    )
    db.add(other_user)
    await db.flush()

    lead = await _make_lead(
        db, workspace.id, company_name="Cross WS Lead",
        assignment_status="assigned", assigned_to=user.id,
    )

    with pytest.raises(services.TransferTargetInvalid):
        await services.transfer_lead(
            db,
            workspace.id,
            current_user_id=user.id,
            current_user_role=user.role,
            lead_id=lead.id,
            to_user_id=other_user.id,
            comment=None,
        )


@skip_no_pg
async def test_transfer_lead_not_owned_403(db, workspace, user, admin_user):
    """Non-owner, non-admin transfer raises LeadNotOwnedByUser."""
    from app.auth.models import User
    from app.leads import services

    # A third manager in the same workspace
    third = User(
        workspace_id=workspace.id,
        email=f"third-{uuid.uuid4().hex[:8]}@test.com",
        name="Third",
        role="manager",
    )
    db.add(third)
    await db.flush()

    lead = await _make_lead(
        db, workspace.id, company_name="Owned Lead",
        assignment_status="assigned", assigned_to=user.id,
    )

    with pytest.raises(services.LeadNotOwnedByUser):
        await services.transfer_lead(
            db,
            workspace.id,
            current_user_id=third.id,
            current_user_role="manager",
            lead_id=lead.id,
            to_user_id=admin_user.id,
            comment=None,
        )
