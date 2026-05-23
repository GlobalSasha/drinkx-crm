"""Unit tests for update_task / archive_task / restore_task service logic.

No live DB — uses MagicMock for the session + monkeypatched repo helpers."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.activity import services as svc
from app.activity.models import ActivityType


def _fake_activity(*, type_=ActivityType.task.value):
    return SimpleNamespace(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        lead_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        type=type_,
        body="старая",
        task_due_at=None,
        archived_at=None,
        payload_json={"title": "старая"},
    )


@pytest.mark.asyncio
async def test_update_task_empty_payload_raises(monkeypatch):
    db = MagicMock()
    db.flush = AsyncMock()
    with pytest.raises(ValueError, match="at least one"):
        await svc.update_task(
            db,
            workspace_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            activity_id=uuid.uuid4(),
            body=None,
            task_due_at=None,
        )


@pytest.mark.asyncio
async def test_update_task_whitespace_body_raises(monkeypatch):
    db = MagicMock()
    db.flush = AsyncMock()
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=_fake_activity()))
    with pytest.raises(ValueError, match="cannot be empty"):
        await svc.update_task(
            db,
            workspace_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            activity_id=uuid.uuid4(),
            body="   ",
            task_due_at=None,
        )


@pytest.mark.asyncio
async def test_update_task_rejects_non_task_activity(monkeypatch):
    db = MagicMock()
    db.flush = AsyncMock()
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=_fake_activity(type_=ActivityType.comment.value)))
    with pytest.raises(ValueError, match="only task"):
        await svc.update_task(
            db,
            workspace_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            activity_id=uuid.uuid4(),
            body="новый",
            task_due_at=None,
        )


@pytest.mark.asyncio
async def test_update_task_writes_body_and_title(monkeypatch):
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    activity = _fake_activity()
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=activity))
    result = await svc.update_task(
        db,
        workspace_id=uuid.uuid4(),
        lead_id=activity.lead_id,
        activity_id=activity.id,
        body="новый текст",
        task_due_at=None,
    )
    assert result.body == "новый текст"
    assert result.payload_json["title"] == "новый текст"


@pytest.mark.asyncio
async def test_archive_task_rejects_non_task_activity(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=_fake_activity(type_=ActivityType.file.value)))
    with pytest.raises(ValueError, match="only task"):
        await svc.archive_task(
            db,
            workspace_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            activity_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_archive_task_raises_when_not_found(monkeypatch):
    from app.activity.services import ActivityNotFound

    db = MagicMock()
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=None))
    with pytest.raises(ActivityNotFound):
        await svc.archive_task(
            db,
            workspace_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            activity_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_archive_task_sets_archived_at(monkeypatch):
    db = MagicMock()
    activity = _fake_activity()
    activity.archived_at = None
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=activity))
    result = await svc.archive_task(
        db,
        workspace_id=uuid.uuid4(),
        lead_id=activity.lead_id,
        activity_id=activity.id,
    )
    assert result.archived_at is not None


@pytest.mark.asyncio
async def test_archive_task_is_idempotent(monkeypatch):
    """Archiving an already-archived task is a no-op (returns the row unchanged)."""
    from datetime import datetime, timezone

    db = MagicMock()
    pre_archived_at = datetime.now(timezone.utc)
    activity = _fake_activity()
    activity.archived_at = pre_archived_at
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=activity))
    result = await svc.archive_task(
        db,
        workspace_id=uuid.uuid4(),
        lead_id=activity.lead_id,
        activity_id=activity.id,
    )
    assert result.archived_at == pre_archived_at  # unchanged


@pytest.mark.asyncio
async def test_restore_task_clears_archived_at(monkeypatch):
    from datetime import datetime, timezone

    db = MagicMock()
    activity = _fake_activity()
    activity.archived_at = datetime.now(timezone.utc)
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(svc.repo, "get_by_id", AsyncMock(return_value=activity))
    result = await svc.restore_task(
        db,
        workspace_id=uuid.uuid4(),
        lead_id=activity.lead_id,
        activity_id=activity.id,
    )
    assert result.archived_at is None


@pytest.mark.asyncio
async def test_restore_task_rejects_non_task_activity(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(svc, "_get_lead_or_raise", AsyncMock(return_value=None))
    monkeypatch.setattr(
        svc.repo,
        "get_by_id",
        AsyncMock(return_value=_fake_activity(type_=ActivityType.comment.value)),
    )
    with pytest.raises(ValueError, match="only task"):
        await svc.restore_task(
            db,
            workspace_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            activity_id=uuid.uuid4(),
        )
