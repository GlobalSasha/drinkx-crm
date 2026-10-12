"""HTTP boundaries for individually granted manager access to free leads."""
from datetime import UTC, datetime

import pytest

from tests.test_lead_assignment import _make_lead
from tests.test_sec01_lead_scoped_access import _user, call, skip_no_pg

pytestmark = [skip_no_pg, pytest.mark.asyncio]


@pytest.mark.parametrize("role", ["admin", "head"])
async def test_management_grants_and_revokes_with_audit(db, workspace, role):
    from sqlalchemy import select

    from app.audit.models import AuditLog

    actor = await _user(db, workspace.id, role, "Actor")
    manager = await _user(db, workspace.id, "manager", "Manager")
    assert manager.can_access_lead_pool is False
    path = f"/users/{manager.id}/lead-pool-access"
    for enabled in (True, False):
        response = await call(db, actor, "PATCH", path, {"can_access_lead_pool": enabled})
        assert response.status_code == 200, response.text
        assert response.json()["can_access_lead_pool"] is enabled
    result = await db.execute(select(AuditLog).where(AuditLog.entity_id == manager.id))
    assert len(result.scalars().all()) == 2
    listing = await call(db, actor, "GET", "/users")
    assert next(u for u in listing.json()["items"] if u["id"] == str(manager.id))["can_access_lead_pool"] is False


async def test_permission_update_rejects_manager_nonmanager_and_foreign_workspace(db, workspace):
    from app.auth.models import Workspace

    manager = await _user(db, workspace.id, "manager", "Manager")
    head = await _user(db, workspace.id, "head", "Head")
    foreign_ws = Workspace(name="Other")
    db.add(foreign_ws)
    await db.flush()
    foreign = await _user(db, foreign_ws.id, "manager", "Foreign")
    body = {"can_access_lead_pool": True}
    for actor, target, expected in ((manager, manager, 403), (head, head, 400), (head, foreign, 404)):
        response = await call(db, actor, "PATCH", f"/users/{target.id}/lead-pool-access", body)
        assert response.status_code == expected, response.text
    assert foreign.can_access_lead_pool is False


async def test_manager_pool_grant_and_revoke_keep_owned_leads(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    head = await _user(db, workspace.id, "head", "Head")
    free = await _make_lead(db, workspace.id)
    owned = await _make_lead(db, workspace.id, assigned_to=manager.id, assignment_status="assigned")
    for path in ("/leads/pool", "/leads/pool/facets"):
        assert (await call(db, manager, "GET", path)).status_code == 403
    assert (await call(db, manager, "GET", f"/leads/{free.id}")).status_code == 404
    assert (await call(db, manager, "POST", f"/leads/{free.id}/claim")).status_code in (403, 404)
    permission_path = f"/users/{manager.id}/lead-pool-access"
    assert (await call(db, head, "PATCH", permission_path, {"can_access_lead_pool": True})).status_code == 200
    await db.refresh(manager, attribute_names=["workspace"])
    me = await call(db, manager, "GET", "/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["can_access_lead_pool"] is True
    for path in ("/leads/pool", "/leads/pool/facets", f"/leads/{free.id}"):
        response = await call(db, manager, "GET", path)
        assert response.status_code == 200, response.text
    response = await call(db, head, "PATCH", permission_path, {"can_access_lead_pool": False})
    assert response.status_code == 200
    assert (await call(db, manager, "GET", "/leads/pool")).status_code == 403
    assert (await call(db, manager, "GET", f"/leads/{free.id}")).status_code == 404
    assert (await call(db, manager, "GET", f"/leads/{owned.id}")).status_code == 200


async def test_grant_opens_only_free_card_and_self_claim(db, workspace):
    from app.auth.models import Workspace

    manager = await _user(db, workspace.id, "manager", "Manager")
    other = await _user(db, workspace.id, "manager", "Other")
    manager.can_access_lead_pool = other.can_access_lead_pool = True
    free = await _make_lead(db, workspace.id)
    theirs = await _make_lead(db, workspace.id, assigned_to=other.id, assignment_status="assigned")
    foreign_ws = Workspace(name="Foreign")
    db.add(foreign_ws)
    await db.flush()
    foreign = await _make_lead(db, foreign_ws.id)
    trashed = await _make_lead(db, workspace.id)
    trashed.deleted_at = datetime.now(UTC)
    await db.flush()
    for lead in (theirs, foreign, trashed):
        assert (await call(db, manager, "GET", f"/leads/{lead.id}")).status_code == 404
        assert (await call(db, manager, "POST", f"/leads/{lead.id}/claim")).status_code == 404
    for method, suffix, body in (
        ("PATCH", "", {"company_name": "Changed"}),
        ("DELETE", "", None),
        ("GET", "/tasks", None),
        ("GET", "/contacts", None),
        ("GET", "/notes", None),
        ("GET", "/enrichment", None),
    ):
        response = await call(db, manager, method, f"/leads/{free.id}{suffix}", body)
        assert response.status_code == 404, response.text
    # Management operations never inherit the pool permission.
    for path in ("/leads/assign", "/leads/sprint"):
        assert (await call(db, manager, "POST", path, {})).status_code == 403
    response = await call(db, manager, "POST", f"/leads/{free.id}/claim")
    assert response.status_code == 200, response.text
    assert response.json()["assigned_to"] == str(manager.id)
    assert (await call(db, other, "POST", f"/leads/{free.id}/claim")).status_code == 404
    assert (await call(db, manager, "PATCH", f"/leads/{free.id}", {"company_name": "Mine"})).status_code == 200


async def test_atomic_claim_rejects_second_winner_and_deleted(db, workspace):
    from app.leads.repositories import claim_lead

    first = await _user(db, workspace.id, "manager", "First")
    second = await _user(db, workspace.id, "manager", "Second")
    free = await _make_lead(db, workspace.id)
    assert await claim_lead(db, free.id, workspace.id, first.id) is not None
    assert await claim_lead(db, free.id, workspace.id, second.id) is None
    deleted = await _make_lead(db, workspace.id)
    deleted.deleted_at = datetime.now(UTC)
    await db.flush()
    assert await claim_lead(db, deleted.id, workspace.id, second.id) is None


async def test_simultaneous_claim_has_exactly_one_winner(db, workspace):
    import asyncio

    from app.leads.repositories import claim_lead
    from tests.conftest import _test_session_factory

    first = await _user(db, workspace.id, "manager", "First")
    second = await _user(db, workspace.id, "manager", "Second")
    lead = await _make_lead(db, workspace.id)
    await db.commit()  # Separate claim transactions must see the seed rows.

    async def attempt(user_id):
        async with _test_session_factory() as session:
            result = await claim_lead(session, lead.id, workspace.id, user_id)
            await session.commit()
            return result is not None

    outcomes = await asyncio.gather(attempt(first.id), attempt(second.id))
    assert outcomes.count(True) == 1
    await db.refresh(lead)
    assert lead.assigned_to in (first.id, second.id)
    assert lead.assignment_status == "assigned"


async def test_pool_status_with_owner_is_never_exposed(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    owner = await _user(db, workspace.id, "manager", "Owner")
    manager.can_access_lead_pool = True
    free = await _make_lead(db, workspace.id)
    malformed = await _make_lead(db, workspace.id, assigned_to=owner.id, assignment_status="pool")
    response = await call(db, manager, "GET", "/leads/pool")
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["items"]} == {str(free.id)}
    response = await call(db, manager, "GET", "/leads/pool/facets")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert (await call(db, manager, "GET", f"/leads/{malformed.id}")).status_code == 404
