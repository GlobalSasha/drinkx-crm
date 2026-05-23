"""Tests that don't need a live DB — pure helpers + route registration.
The full HTTP→storage flow runs only with Postgres + Supabase config (CI)."""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.activity.files_router import TaskFileOut


def test_routes_registered():
    from app.main import app
    paths = {r.path for r in app.routes}
    expected = {
        "/leads/{lead_id}/tasks/{task_id}/files",
        "/activities/{activity_id}/download",
        "/activities/{activity_id}/file",
    }
    missing = expected - paths
    assert not missing, f"missing routes: {missing}"


def test_task_file_out_extracts_payload_fields():
    a = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type="file",
        body="caption",
        file_kind="pdf",
        payload_json={
            "parent_task_id": "22222222-2222-2222-2222-222222222222",
            "file_name": "x.pdf",
            "file_size": 42,
        },
        created_at=datetime.now(timezone.utc),
    )
    dto = TaskFileOut.from_activity(a)
    assert dto.file_name == "x.pdf"
    assert dto.file_size == 42
    assert str(dto.parent_task_id) == "22222222-2222-2222-2222-222222222222"


def test_task_file_out_handles_missing_payload():
    a = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type="file",
        body=None,
        file_kind=None,
        payload_json=None,
        created_at=datetime.now(timezone.utc),
    )
    dto = TaskFileOut.from_activity(a)
    assert dto.file_name == "unknown"
    assert dto.file_size == 0
    assert dto.parent_task_id is None


def test_task_file_out_handles_invalid_parent_uuid():
    a = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type="file",
        body=None,
        file_kind=None,
        payload_json={"parent_task_id": "not-a-uuid", "file_name": "x.pdf", "file_size": 10},
        created_at=datetime.now(timezone.utc),
    )
    dto = TaskFileOut.from_activity(a)
    assert dto.parent_task_id is None
