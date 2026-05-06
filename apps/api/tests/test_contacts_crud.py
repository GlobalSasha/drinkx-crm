"""Tests for Contact CRUD — nested under leads."""
from __future__ import annotations

import uuid

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
    from app.leads import repositories as repo

    assignment_status = kwargs.pop("assignment_status", "assigned")
    assigned_to = kwargs.pop("assigned_to", None)
    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db, workspace_id, payload,
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


async def _make_contact(db, lead_id, **kwargs):
    from app.contacts import repositories as repo

    payload = dict(name=f"Contact {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create(db, lead_id, payload)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_create_contact_for_lead(db, workspace, user):
    """Creating a contact returns a Contact with the correct lead_id."""
    lead = await _make_lead(db, workspace.id, company_name="Acme")
    from app.contacts import services

    contact = await services.create_contact(
        db, workspace.id, lead.id,
        {"name": "Ivan Petrov", "role_type": "champion", "email": "ivan@example.com"},
    )

    assert contact.lead_id == lead.id
    assert contact.name == "Ivan Petrov"
    assert contact.role_type == "champion"


@skip_no_pg
async def test_list_contacts_isolation(db, workspace, user):
    """Contacts of lead A are not returned when listing for lead B."""
    lead_a = await _make_lead(db, workspace.id, company_name="Lead A")
    lead_b = await _make_lead(db, workspace.id, company_name="Lead B")

    await _make_contact(db, lead_a.id, name="Contact A")
    await _make_contact(db, lead_b.id, name="Contact B")

    from app.contacts import services

    contacts_a = await services.list_contacts(db, workspace.id, lead_a.id)
    ids = {c.id for c in contacts_a}
    assert all(c.lead_id == lead_a.id for c in contacts_a)
    # None of lead B's contacts appear
    contacts_b = await services.list_contacts(db, workspace.id, lead_b.id)
    assert all(c.lead_id == lead_b.id for c in contacts_b)
    assert not ids.intersection({c.id for c in contacts_b})


@skip_no_pg
async def test_update_contact(db, workspace, user):
    """PATCH updates only the provided fields."""
    lead = await _make_lead(db, workspace.id)
    contact = await _make_contact(db, lead.id, name="Original", phone="111")

    from app.contacts import services

    updated = await services.update_contact(
        db, workspace.id, lead.id, contact.id, {"name": "Updated"}
    )
    assert updated.name == "Updated"
    assert updated.phone == "111"  # untouched


@skip_no_pg
async def test_delete_contact(db, workspace, user):
    """Deleting a contact makes it unfindable."""
    lead = await _make_lead(db, workspace.id)
    contact = await _make_contact(db, lead.id, name="ToDelete")
    contact_id = contact.id

    from app.contacts import repositories as repo, services

    await services.delete_contact(db, workspace.id, lead.id, contact_id)
    result = await repo.get_by_id(db, contact_id, lead.id)
    assert result is None


@skip_no_pg
async def test_contact_404_for_different_workspace(db, workspace, user):
    """Accessing a lead from a different workspace raises LeadNotFound."""
    from app.auth.models import Workspace
    from app.contacts import services
    from app.leads.services import LeadNotFound

    ws_b = Workspace(name="Other WS", plan="free")
    db.add(ws_b)
    await db.flush()

    lead = await _make_lead(db, workspace.id)

    with pytest.raises(LeadNotFound):
        await services.list_contacts(db, ws_b.id, lead.id)


@skip_no_pg
async def test_contact_role_type_validation_rejects_invalid(db, workspace, user):
    """Creating a contact with an invalid role_type raises ValueError."""
    from app.contacts import services

    lead = await _make_lead(db, workspace.id)

    with pytest.raises(ValueError, match="role_type"):
        await services.create_contact(
            db, workspace.id, lead.id,
            {"name": "Bad", "role_type": "not_a_real_role"},
        )


@skip_no_pg
async def test_contact_verified_status_validation(db, workspace, user):
    """Creating a contact with an invalid verified_status raises ValueError."""
    from app.contacts import services

    lead = await _make_lead(db, workspace.id)

    with pytest.raises(ValueError, match="verified_status"):
        await services.create_contact(
            db, workspace.id, lead.id,
            {"name": "Bad", "verified_status": "unknown_status"},
        )
