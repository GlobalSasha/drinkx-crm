"""Tests for Followup CRUD — nested under leads."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_create_followup_default_status_pending(db, workspace, user):
    """A new followup has status=pending by default."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import services

    fu = await services.create_followup(
        db, workspace.id, lead.id, {"name": "Call back", "position": 0}
    )
    assert fu.lead_id == lead.id
    assert fu.status == "pending"
    assert fu.name == "Call back"


@skip_no_pg
async def test_list_followups_ordered_by_position(db, workspace, user):
    """list_followups returns followups ordered by position ASC."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import services

    await services.create_followup(db, workspace.id, lead.id, {"name": "Third", "position": 2})
    await services.create_followup(db, workspace.id, lead.id, {"name": "First", "position": 0})
    await services.create_followup(db, workspace.id, lead.id, {"name": "Second", "position": 1})

    items = await services.list_followups(db, workspace.id, lead.id)
    positions = [f.position for f in items]
    assert positions == sorted(positions)
    assert items[0].name == "First"


@skip_no_pg
async def test_update_followup(db, workspace, user):
    """PATCH updates only the provided fields."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import services

    fu = await services.create_followup(
        db, workspace.id, lead.id, {"name": "Original", "position": 0}
    )
    updated = await services.update_followup(
        db, workspace.id, lead.id, fu.id, {"name": "Updated"}
    )
    assert updated.name == "Updated"
    assert updated.position == 0  # untouched


@skip_no_pg
async def test_delete_followup(db, workspace, user):
    """Deleting a followup removes it from the list."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import repositories as repo, services

    fu = await services.create_followup(
        db, workspace.id, lead.id, {"name": "ToDelete", "position": 0}
    )
    fu_id = fu.id

    await services.delete_followup(db, workspace.id, lead.id, fu_id)
    result = await repo.get_by_id(db, fu_id, lead.id)
    assert result is None


@skip_no_pg
async def test_complete_followup_sets_done(db, workspace, user):
    """complete_followup sets status=done and completed_at."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import services

    fu = await services.create_followup(
        db, workspace.id, lead.id, {"name": "Task", "position": 0}
    )
    completed = await services.complete_followup(db, workspace.id, lead.id, fu.id)

    assert completed.status == "done"
    assert completed.completed_at is not None


@skip_no_pg
async def test_create_lead_auto_seeds_followups(db, workspace, user):
    """Creating a lead via services.create_lead auto-seeds 3 default followups."""
    from app.leads import services as leads_services
    from app.leads.schemas import LeadCreate
    from app.followups import repositories as repo

    lead = await leads_services.create_lead(db, workspace.id, user.id, LeadCreate(company_name="Seed Test"))
    followups = await repo.list_for_lead(db, lead.id)

    assert len(followups) == 3
    names = {f.name for f in followups}
    assert "Первичный контакт" in names
    assert "Discovery-звонок" in names
    assert "Отправить материалы" in names


@skip_no_pg
async def test_followup_status_enum_validation(db, workspace, user):
    """Creating a followup with an invalid status raises ValueError."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import services

    with pytest.raises(ValueError, match="status"):
        await services.create_followup(
            db, workspace.id, lead.id,
            {"name": "Bad status", "position": 0, "status": "not_a_valid_status"},
        )


@skip_no_pg
async def test_followup_reminder_kind_validation(db, workspace, user):
    """Creating a followup with an invalid reminder_kind raises ValueError."""
    lead = await _make_lead(db, workspace.id)
    from app.followups import services

    with pytest.raises(ValueError, match="reminder_kind"):
        await services.create_followup(
            db, workspace.id, lead.id,
            {"name": "Bad kind", "position": 0, "reminder_kind": "not_a_kind"},
        )
