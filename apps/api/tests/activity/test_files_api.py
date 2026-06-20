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


def test_routes_include_task_edit_delete_archive_restore():
    from app.main import app
    paths = {(r.path, tuple(sorted(getattr(r, "methods", set()) or set()))) for r in app.routes}
    activity_id_routes = {(p, m) for (p, m) in paths if "/activities/{activity_id}" in p}
    methods_seen = {m for _path, methods in activity_id_routes for m in methods}
    assert "PATCH" in methods_seen, f"PATCH missing in {activity_id_routes}"
    assert "DELETE" in methods_seen, f"DELETE missing in {activity_id_routes}"
    restore_routes = [(p, m) for (p, m) in paths if p.endswith("/restore")]
    assert any("POST" in m for _p, m in restore_routes), f"restore route missing, paths: {paths}"
    archive_routes = [(p, m) for (p, m) in paths if p.endswith("/archive")]
    assert any("GET" in m for _p, m in archive_routes), f"archive list route missing, paths: {paths}"
    reopen_routes = [(p, m) for (p, m) in paths if p.endswith("/reopen-task")]
    assert any("POST" in m for _p, m in reopen_routes), f"reopen-task route missing, paths: {paths}"


def test_task_update_in_accepts_partial():
    from app.activity.schemas import TaskUpdateIn
    a = TaskUpdateIn.model_validate({})
    assert a.body is None and a.task_due_at is None
    b = TaskUpdateIn.model_validate({"body": "новый текст"})
    assert b.body == "новый текст"
