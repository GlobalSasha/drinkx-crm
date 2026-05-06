"""Tests for stage-transition rule engine (Sprint 1.2 Task 3, ADR-003/012)."""
from __future__ import annotations

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


async def _make_stage(db, pipeline_id, *, position=0, name=None, is_won=False, is_lost=False):
    """Create a Stage row for test setup."""
    from app.pipelines.models import Stage

    s = Stage(
        pipeline_id=pipeline_id,
        name=name or f"Stage-pos{position}-{uuid.uuid4().hex[:4]}",
        position=position,
        color="#aabbcc",
        rot_days=7,
        is_won=is_won,
        is_lost=is_lost,
    )
    db.add(s)
    await db.flush()
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_move_to_first_stage(db, workspace, user, pipeline):
    """Lead with stage_id=NULL → moves to position-0 stage; stage_change activity logged."""
    from app.automation.stage_change import move_stage
    from app.activity.models import Activity
    from sqlalchemy import select

    p, _ = pipeline
    stage = await _make_stage(db, p.id, position=0, name="Первый этап")
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)
    assert lead.stage_id is None

    result = await move_stage(db, lead, stage, user.id)

    assert result.stage_id == stage.id

    activities = (await db.execute(
        select(Activity).where(Activity.lead_id == lead.id, Activity.type == "stage_change")
    )).scalars().all()
    assert len(activities) == 1


@skip_no_pg
async def test_move_creates_activity_with_payload(db, workspace, user, pipeline):
    """Activity payload contains from/to ids, names, position, gate_skipped."""
    from app.automation.stage_change import move_stage
    from app.activity.models import Activity
    from sqlalchemy import select

    p, from_s = pipeline
    to_s = await _make_stage(db, p.id, position=0, name="Target Stage")

    lead = await _make_lead(db, workspace.id, pipeline_id=p.id, stage_id=from_s.id)
    await move_stage(db, lead, to_s, user.id)

    activity = (await db.execute(
        select(Activity).where(Activity.lead_id == lead.id, Activity.type == "stage_change")
    )).scalar_one()

    payload = activity.payload_json
    assert payload["from_stage_id"] == str(from_s.id)
    assert payload["from_stage_name"] == from_s.name
    assert payload["to_stage_id"] == str(to_s.id)
    assert payload["to_stage_name"] == to_s.name
    assert payload["to_position"] == to_s.position
    assert payload["gate_skipped"] is False
    assert payload["skip_reason"] is None


@skip_no_pg
async def test_move_stage_wrong_pipeline_blocked(db, workspace, user, pipeline):
    """Target stage from different pipeline → StageTransitionBlocked with stage_wrong_pipeline (cannot skip)."""
    from app.automation.stage_change import move_stage, StageTransitionBlocked
    from app.pipelines.models import Pipeline

    p, _ = pipeline

    # Create a second pipeline
    p2 = Pipeline(workspace_id=workspace.id, name="Other Pipeline", type="sales", position=1)
    db.add(p2)
    await db.flush()
    other_stage = await _make_stage(db, p2.id, position=0, name="Other Stage")

    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)

    # Cannot skip pipeline mismatch
    with pytest.raises(StageTransitionBlocked) as exc_info:
        await move_stage(db, lead, other_stage, user.id, gate_skipped=True, skip_reason="force")

    violations = exc_info.value.violations
    assert len(violations) == 1
    assert violations[0].code == "stage_wrong_pipeline"


@skip_no_pg
async def test_move_to_stage_6_without_economic_buyer_blocked(db, workspace, user, pipeline):
    """No contact with role_type=economic_buyer → blocked when moving to stage position>=6."""
    from app.automation.stage_change import move_stage, StageTransitionBlocked

    p, _ = pipeline
    stage6 = await _make_stage(db, p.id, position=6, name="Договор / пилот")
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)

    with pytest.raises(StageTransitionBlocked) as exc_info:
        await move_stage(db, lead, stage6, user.id)

    codes = [v.code for v in exc_info.value.violations]
    assert "economic_buyer_required" in codes


@skip_no_pg
async def test_move_to_stage_6_with_economic_buyer_allowed(db, workspace, user, pipeline):
    """Contact with role_type=economic_buyer exists → allowed to move to stage position>=6."""
    from app.automation.stage_change import move_stage
    from app.contacts.models import Contact

    p, _ = pipeline
    stage6 = await _make_stage(db, p.id, position=6, name="Договор / пилот")
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)

    contact = Contact(lead_id=lead.id, name="Ivan EB", role_type="economic_buyer")
    db.add(contact)
    await db.flush()

    result = await move_stage(db, lead, stage6, user.id)
    assert result.stage_id == stage6.id


@skip_no_pg
async def test_move_to_stage_6_blocked_can_skip_with_reason(db, workspace, user, pipeline):
    """gate_skipped=True + skip_reason → succeeds even without economic buyer."""
    from app.automation.stage_change import move_stage

    p, _ = pipeline
    stage6 = await _make_stage(db, p.id, position=6, name="Договор / пилот")
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)

    result = await move_stage(db, lead, stage6, user.id, gate_skipped=True, skip_reason="forcing for demo")
    assert result.stage_id == stage6.id


@skip_no_pg
async def test_move_skip_without_reason_raises_value_error(db, workspace, user, pipeline):
    """gate_skipped=True + skip_reason=None → ValueError before any DB access."""
    from app.automation.stage_change import move_stage

    p, _ = pipeline
    stage = await _make_stage(db, p.id, position=6, name="Договор / пилот")
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)

    with pytest.raises(ValueError, match="skip_reason"):
        await move_stage(db, lead, stage, user.id, gate_skipped=True, skip_reason=None)


@skip_no_pg
async def test_move_to_won_stage_sets_won_at(db, workspace, user, pipeline):
    """Entering is_won=True stage → lead.won_at populated."""
    from app.automation.stage_change import move_stage

    p, _ = pipeline
    won_stage = await _make_stage(db, p.id, position=10, name="Закрыто (won)", is_won=True)
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)
    assert lead.won_at is None

    before = datetime.now(timezone.utc)
    result = await move_stage(db, lead, won_stage, user.id)

    assert result.won_at is not None
    assert result.won_at >= before
    assert result.lost_at is None


@skip_no_pg
async def test_move_to_lost_stage_sets_lost_at_and_reason(db, workspace, user, pipeline):
    """Service param lost_reason is persisted; lead.lost_at set on lost stage."""
    from app.leads import services

    p, _ = pipeline
    lost_stage = await _make_stage(db, p.id, position=11, name="Закрыто (lost)", is_lost=True)
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id)
    assert lead.lost_at is None

    before = datetime.now(timezone.utc)
    result = await services.move_lead_stage(
        db,
        workspace.id,
        user.id,
        lead.id,
        lost_stage.id,
        lost_reason="Ушли к конкурентам",
    )

    assert result.lost_at is not None
    assert result.lost_at >= before
    assert result.lost_reason == "Ушли к конкурентам"
    assert result.won_at is None


@skip_no_pg
async def test_archived_lead_cannot_move(db, workspace, user, pipeline):
    """lead.archived_at set → StageTransitionInvalid raised."""
    from app.automation.stage_change import move_stage, StageTransitionInvalid

    p, stage = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p.id,
                             archived_at=datetime.now(timezone.utc))

    with pytest.raises(StageTransitionInvalid, match="archived"):
        await move_stage(db, lead, stage, user.id)
