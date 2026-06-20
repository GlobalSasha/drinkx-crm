"""Tests that don't need a live DB — pure helpers + schema validation.
The full HTTP flow is covered by Task 16 e2e on CI with real Postgres."""
import pytest

from app.base_update import services as svc
from app.base_update.api_schemas import ResolveConflictIn, IngestJobOut


# ---- _build_staged_files pure helper ----

def test_build_staged_files_happy_path():
    staged = svc._build_staged_files([("a.md", b"# title\nbody"), ("b.md", b"x")])
    assert [s["filename"] for s in staged] == ["a.md", "b.md"]
    assert staged[0]["text"] == "# title\nbody"


def test_build_staged_files_rejects_non_md():
    with pytest.raises(ValueError, match="только .md"):
        svc._build_staged_files([("notes.txt", b"x")])


def test_build_staged_files_rejects_empty_list():
    with pytest.raises(ValueError, match="no files"):
        svc._build_staged_files([])


def test_build_staged_files_rejects_oversize():
    big = b"a" * (svc.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds"):
        svc._build_staged_files([("a.md", big)])


def test_build_staged_files_handles_bad_utf8_gracefully():
    """A file with invalid UTF-8 bytes should decode with replacement chars, not raise."""
    staged = svc._build_staged_files([("a.md", b"valid \xff\xfe garbage")])
    assert staged[0]["filename"] == "a.md"
    assert "valid" in staged[0]["text"]


# ---- DTO validation ----

def test_resolve_conflict_in_requires_resolution():
    with pytest.raises(Exception):  # Pydantic ValidationError
        ResolveConflictIn.model_validate({})


def test_resolve_conflict_in_accepts_optional_resolved_value():
    body = ResolveConflictIn.model_validate({"resolution": "overwrite"})
    assert body.resolution == "overwrite"
    assert body.resolved_value is None
    body2 = ResolveConflictIn.model_validate({"resolution": "manual", "resolved_value": "X"})
    assert body2.resolved_value == "X"


# ---- Route registration smoke (no client, just inspect the app object) ----

def test_routes_registered_in_app():
    from app.main import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    expected = {
        "/api/base-update/jobs",
        "/api/base-update/jobs/{job_id}",
        "/api/base-update/jobs/{job_id}/conflicts",
        "/api/base-update/conflicts/{conflict_id}",
        "/api/base-update/jobs/{job_id}/apply",
    }
    missing = expected - paths
    assert not missing, f"missing routes: {missing}"


# --- FIX-5: IngestJobOut strips underscore-prefixed keys from stats_json ---

def test_ingest_job_out_strips_underscored_keys():
    from datetime import datetime, timezone
    raw = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "user_id": None,
        "status": "extracting",
        "file_count": 1,
        "source_filenames": ["a.md"],
        "stats_json": {
            "_staged_files": [{"filename": "a.md", "text": "secret content"}],
            "files": 1,
        },
        "error": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    dto = IngestJobOut.model_validate(raw)
    assert "_staged_files" not in (dto.stats_json or {})
    assert (dto.stats_json or {}).get("files") == 1


def test_ingest_job_out_all_internal_keys_stripped():
    from datetime import datetime, timezone
    raw = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "user_id": None,
        "status": "ready",
        "file_count": 2,
        "source_filenames": ["a.md", "b.md"],
        "stats_json": {"_staged_files": [], "_internal_debug": "secret", "records_created": 3},
        "error": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    dto = IngestJobOut.model_validate(raw)
    assert dto.stats_json == {"records_created": 3}


def test_ingest_job_out_only_internal_keys_becomes_none():
    from datetime import datetime, timezone
    raw = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "user_id": None,
        "status": "extracting",
        "file_count": 1,
        "source_filenames": ["a.md"],
        "stats_json": {"_staged_files": [{"filename": "a.md", "text": "secret"}]},
        "error": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    dto = IngestJobOut.model_validate(raw)
    # All keys were internal → stats_json should be None (empty dict coerced to None)
    assert dto.stats_json is None
