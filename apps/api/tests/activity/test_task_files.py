"""Service-level tests using a mocked session pattern. No Postgres required."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.activity import files as svc
from app.activity.models import ActivityType


class _FakeActivity(SimpleNamespace):
    """Lightweight stand-in for Activity ORM instances — no mapper needed."""


def _flushing_db(set_id_to=None):
    """A MagicMock db whose .flush() mutates the most-recently-added object's id."""
    added = []
    db = MagicMock()
    db.add = lambda obj: added.append(obj)

    async def fake_flush():
        if added and set_id_to is not None:
            added[-1].id = set_id_to
    db.flush = fake_flush
    db.refresh = AsyncMock()
    db._added = added
    return db


@pytest.mark.asyncio
async def test_upload_persists_activity_and_writes_to_storage(monkeypatch):
    activity_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    db = _flushing_db(set_id_to=activity_id)

    fake_client = SimpleNamespace(upload=AsyncMock())
    monkeypatch.setattr(svc, "get_storage_client", lambda: fake_client)
    # Patch Activity constructor to avoid SQLAlchemy mapper resolution for Lead
    monkeypatch.setattr(svc, "Activity", _FakeActivity)

    ws = uuid.UUID("22222222-2222-2222-2222-222222222222")
    lead = uuid.UUID("33333333-3333-3333-3333-333333333333")
    user = uuid.UUID("44444444-4444-4444-4444-444444444444")
    parent = uuid.UUID("55555555-5555-5555-5555-555555555555")

    activity = await svc.upload_task_file(
        db,
        workspace_id=ws, lead_id=lead, user_id=user, parent_task_id=parent,
        filename="Invoice v3.pdf", content=b"%PDF-1.7 ...", content_type="application/pdf",
        kind="pdf", caption="коммерческое",
    )
    assert activity.type == ActivityType.file.value
    assert activity.payload_json["parent_task_id"] == str(parent)
    assert activity.payload_json["file_name"] == "Invoice v3.pdf"
    assert activity.payload_json["file_size"] == len(b"%PDF-1.7 ...")
    assert activity.file_kind == "pdf"
    assert activity.body == "коммерческое"
    assert activity.file_url == f"{ws}/{lead}/{activity_id}/invoice-v3.pdf"
    fake_client.upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_propagates_storage_error(monkeypatch):
    from app.storage.client import StorageError
    activity_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    db = _flushing_db(set_id_to=activity_id)
    fake_client = SimpleNamespace(upload=AsyncMock(side_effect=StorageError("upload failed [500]: x")))
    monkeypatch.setattr(svc, "get_storage_client", lambda: fake_client)
    monkeypatch.setattr(svc, "Activity", _FakeActivity)

    with pytest.raises(StorageError):
        await svc.upload_task_file(
            db,
            workspace_id=uuid.uuid4(), lead_id=uuid.uuid4(), user_id=uuid.uuid4(),
            parent_task_id=uuid.uuid4(),
            filename="x.pdf", content=b"x", content_type="application/pdf", kind="pdf", caption=None,
        )


@pytest.mark.asyncio
async def test_delete_swallows_storage_failure(monkeypatch):
    from app.storage.client import StorageError
    db = MagicMock()
    db.delete = AsyncMock()
    fake_client = SimpleNamespace(delete=AsyncMock(side_effect=StorageError("500")))
    monkeypatch.setattr(svc, "get_storage_client", lambda: fake_client)
    activity = SimpleNamespace(
        type=ActivityType.file.value,
        file_url="ws/lead/act/file.pdf",
        id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
    )
    await svc.delete_file_activity(db, activity)  # must not raise
    fake_client.delete.assert_awaited_once()
    db.delete.assert_awaited_once_with(activity)


@pytest.mark.asyncio
async def test_signed_download_url_rejects_non_file_activity():
    activity = SimpleNamespace(type="comment", file_url="ws/lead/act/file.pdf")
    with pytest.raises(ValueError):
        await svc.signed_download_url(activity)
