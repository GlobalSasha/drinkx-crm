"""Tests for lead soft-delete / Trash / restore / permanent-destroy (plan 009)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


async def _make_lead(db, workspace_id, **kwargs):
    """Create a Lead row directly via repo for test setup."""
    from app.leads import repositories as repo

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


@skip_no_pg
async def test_soft_delete_sets_deleted_at_and_deleted_by(db, workspace, user):
    """soft_delete_lead stamps deleted_at + deleted_by."""
    from app.leads import services

    lead = await _make_lead(db, workspace.id, company_name="To Trash")

    await services.soft_delete_lead(db, workspace.id, lead.id, user.id)

    from app.leads import repositories as repo

    refreshed = await repo.get_by_id(db, lead.id, workspace.id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None
    assert refreshed.deleted_by == user.id


@skip_no_pg
async def test_soft_deleted_lead_absent_from_list_and_pool(db, workspace, user):
    """A trashed lead disappears from list_leads/list_pool but not the DB."""
    from app.leads import repositories as repo, services

    assigned = await _make_lead(
        db, workspace.id, company_name="Assigned Trash",
        assignment_status="assigned", assigned_to=user.id,
    )
    pooled = await _make_lead(
        db, workspace.id, company_name="Pool Trash", assignment_status="pool",
    )

    await services.soft_delete_lead(db, workspace.id, assigned.id, user.id)
    await services.soft_delete_lead(db, workspace.id, pooled.id, user.id)

    items, total = await repo.list_leads(db, workspace.id)
    assert assigned.id not in {i.id for i in items}
    assert total == 0

    pool_items, pool_total = await repo.list_pool(db, workspace.id)
    assert pooled.id not in {i.id for i in pool_items}
    assert pool_total == 0


@skip_no_pg
async def test_soft_deleted_lead_present_in_trash(db, workspace, user):
    """list_trash returns only soft-deleted leads."""
    from app.leads import repositories as repo, services

    live = await _make_lead(db, workspace.id, company_name="Still Live")
    trashed = await _make_lead(db, workspace.id, company_name="In Trash")

    await services.soft_delete_lead(db, workspace.id, trashed.id, user.id)

    items, total = await repo.list_trash(db, workspace.id)
    ids = {i.id for i in items}
    assert trashed.id in ids
    assert live.id not in ids
    assert total == 1


@skip_no_pg
async def test_restore_clears_flags_and_returns_to_lists(db, workspace, user):
    """restore_lead clears deleted_at/deleted_by and the lead reappears
    in the active list."""
    from app.leads import repositories as repo, services

    lead = await _make_lead(db, workspace.id, company_name="Restore Me")
    await services.soft_delete_lead(db, workspace.id, lead.id, user.id)

    restored = await services.restore_lead(db, workspace.id, lead.id)
    assert restored.deleted_at is None
    assert restored.deleted_by is None

    items, total = await repo.list_leads(db, workspace.id)
    assert lead.id in {i.id for i in items}
    assert total == 1

    trash_items, trash_total = await repo.list_trash(db, workspace.id)
    assert lead.id not in {i.id for i in trash_items}
    assert trash_total == 0


@skip_no_pg
async def test_update_lead_raises_not_found_on_trashed_lead(db, workspace, user):
    """A trashed lead is not editable until restored."""
    from app.leads import services
    from app.leads.schemas import LeadUpdate

    lead = await _make_lead(db, workspace.id, company_name="Locked")
    await services.soft_delete_lead(db, workspace.id, lead.id, user.id)

    with pytest.raises(services.LeadNotFound):
        await services.update_lead(
            db, workspace.id, lead.id, LeadUpdate(city="Moscow")
        )


@skip_no_pg
async def test_destroy_lead_removes_row(db, workspace, user):
    """destroy_lead is a true hard delete — the row is gone even from Trash."""
    from app.leads import repositories as repo, services

    lead = await _make_lead(db, workspace.id, company_name="Destroy Me")
    lead_id = lead.id
    await services.soft_delete_lead(db, workspace.id, lead_id, user.id)

    await services.destroy_lead(db, workspace.id, lead_id)

    result = await repo.get_by_id(db, lead_id, workspace.id)
    assert result is None

    trash_items, trash_total = await repo.list_trash(db, workspace.id)
    assert lead_id not in {i.id for i in trash_items}
    assert trash_total == 0


@skip_no_pg
async def test_soft_delete_restore_destroy_each_write_audit_row(db, workspace, user):
    """Each lifecycle action is audited — via the router-level service +
    the audit helper, mirroring the router's call shape."""
    from app.audit.audit import log as log_audit_event
    from app.audit.models import AuditLog
    from app.leads import services

    lead = await _make_lead(db, workspace.id, company_name="Audited Lead")

    await services.soft_delete_lead(db, workspace.id, lead.id, user.id)
    await log_audit_event(
        db,
        action="lead.soft_delete",
        workspace_id=workspace.id,
        user_id=user.id,
        entity_type="lead",
        entity_id=lead.id,
    )

    await services.restore_lead(db, workspace.id, lead.id)
    await log_audit_event(
        db,
        action="lead.restore",
        workspace_id=workspace.id,
        user_id=user.id,
        entity_type="lead",
        entity_id=lead.id,
    )

    await services.destroy_lead(db, workspace.id, lead.id)
    await log_audit_event(
        db,
        action="lead.destroy",
        workspace_id=workspace.id,
        user_id=user.id,
        entity_type="lead",
        entity_id=lead.id,
    )
    await db.flush()

    result = await db.execute(
        select(AuditLog.action)
        .where(AuditLog.workspace_id == workspace.id, AuditLog.entity_id == lead.id)
        .order_by(AuditLog.created_at.asc())
    )
    actions = [row[0] for row in result.all()]
    assert actions == ["lead.soft_delete", "lead.restore", "lead.destroy"]
