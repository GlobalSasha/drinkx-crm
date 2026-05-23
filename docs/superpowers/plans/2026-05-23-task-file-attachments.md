# Task File Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manager attaches files (pdf / image / doc / xlsx / txt / audio, ≤25 MB) to a task in the lead card; files live in a private Supabase Storage bucket; the task's tab shows attachments + a search box that filters tasks by filename and body text.

**Architecture:** Files are persisted in a private Supabase Storage bucket `lead-files` at the path `{workspace_id}/{lead_id}/{activity_id}/{filename}`. Each upload creates an `Activity(type="file")` row with `file_url` (storage path), `file_kind`, and `payload_json={"parent_task_id": "<task-activity-id>", "file_name": ..., "file_size": ...}`. Download is via a 5-minute backend-signed URL. The TasksTab queries attachments by `parent_task_id`; search is server-side ILIKE on `payload_json->>'file_name'` and the parent task's `body`.

**Tech Stack:** FastAPI multipart + httpx (Supabase Storage REST), SQLAlchemy 2 async, Next.js 15 + TanStack Query, brand-token Tailwind.

**Locked decisions** (from earlier session, do NOT reopen):
- Storage = Supabase Storage, **bucket name `lead-files`**, private (no public access).
- Binding = each file is an `Activity(type="file")` row with `payload_json.parent_task_id` linking it to a task-Activity. No schema migration needed.
- Search v1 = **filename + body text only** (content extraction — PDF text, audio STT — explicitly deferred).
- Limits: ≤25 MB per file, type whitelist (see Task 4).

**Spec source for posterity:** `docs/BACKLOG.md` item #1.

---

## Conventions baked in (do not deviate)

1. **`supabase-py` is NOT installed and shouldn't be** — adds a heavy dep we don't need. Use raw `httpx.AsyncClient` against Supabase Storage REST (`POST /storage/v1/object/{bucket}/{path}`, `POST /storage/v1/object/sign/{bucket}/{path}`). The service-role key (`SUPABASE_SECRET_KEY`) is already in `app.config`.
2. **`Activity.file_url` stores the storage PATH** (`{workspace_id}/{lead_id}/{activity_id}/{slug}`), NOT a signed URL. Signed URLs are generated on demand by the backend (5-minute TTL) and returned via a separate GET endpoint so they never go stale in the DB.
3. **Auth on upload/download endpoints:** `current_user` (regular dependency from `app.auth.dependencies`) — anyone with access to the lead can attach / view. Workspace scoping is enforced by `_get_lead_or_raise`.
4. **Frontend never talks to Supabase Storage directly** for these files — always through our API (avoids RLS complexity for the bucket; the bucket stays private with no policies, only the service-role key reads/writes).
5. **`Activity.body` for task-files holds the manager's optional caption** (e.g. "коммерческое предложение v3"); `payload_json.file_name` holds the original upload filename. Search hits BOTH.
6. **One file per Activity row.** Multiple files for a task = multiple `Activity(type="file")` rows with the same `parent_task_id`. Keeps the model simple and matches how the existing `Activity.file_url` column was designed.
7. **Cleanup is best-effort, not transactional.** Deleting an Activity tries to delete the storage object; failure is logged, never raised. An orphan-purger cron sweeps weekly.
8. **Branch:** all work lands on `feat/task-file-attachments` (already created from `main` after #66 merged).

---

## File Structure

### Backend — new
- `apps/api/app/storage/__init__.py` — package marker.
- `apps/api/app/storage/client.py` — `SupabaseStorageClient` (async httpx wrapper for upload / sign / delete).
- `apps/api/app/storage/paths.py` — pure helper to compute the storage key + slugify filename.
- `apps/api/app/activity/files.py` — task-file domain logic: orchestrates upload (storage + Activity row), produces signed-URL response shape, deletes file activity + storage object.
- `apps/api/app/activity/files_router.py` — new router for `POST /leads/{lead_id}/tasks/{task_id}/files`, `GET /activities/{id}/download`, `DELETE /activities/{id}/file`, `GET /leads/{lead_id}/tasks/{task_id}/files`.
- `apps/api/alembic/versions/20260523_0037_activity_payload_parent_task_index.py` — small migration: GIN expression index on `activities((payload_json->>'parent_task_id'))` so the task→files lookup is fast.

### Backend — modified
- `apps/api/app/config.py` — add `supabase_storage_bucket: str = "lead-files"` setting.
- `apps/api/app/activity/services.py` — add `list_task_files(...)` and `delete_file_activity(...)` (the latter calls storage cleanup).
- `apps/api/app/activity/repositories.py` — add `find_by_payload_parent_task_id` query helper.
- `apps/api/app/main.py` — register the new files router.
- `apps/api/app/scheduled/jobs.py` — `purge_orphan_storage_files` Celery task (sweeps `lead-files` for objects with no Activity).
- `apps/api/app/scheduled/celery_app.py` — beat entry for the purger (weekly).
- `apps/api/.env.example` — document `SUPABASE_STORAGE_BUCKET`.

### Backend — tests (new)
- `apps/api/tests/storage/__init__.py`, `apps/api/tests/storage/test_paths.py` — pure path/slug logic.
- `apps/api/tests/storage/test_client.py` — httpx-mocked storage client.
- `apps/api/tests/activity/test_task_files.py` — service-layer smoke + ILIKE search.

### Frontend — new
- `apps/web/lib/hooks/use-task-files.ts` — `useTaskFiles`, `useUploadTaskFile`, `useDownloadTaskFile`, `useDeleteTaskFile`.
- `apps/web/components/lead-card/TaskFilesList.tsx` — list of files under a task with download + delete buttons.
- `apps/web/components/lead-card/TaskFileDropzone.tsx` — drag-drop + file input UI (mirrors `UploadStep.tsx`).

### Frontend — modified
- `apps/web/lib/types.ts` — `TaskFileOut` type.
- `apps/web/components/lead-card/TasksTab.tsx` — render `<TaskFilesList>` + `<TaskFileDropzone>` inside the expanded task block; add the search box at the top.

---

## Phase 0 — Storage primitives (pure / local, no DB, no network)

### Task 1: Path helpers + slug

**Files:**
- Create: `apps/api/app/storage/__init__.py` (empty)
- Create: `apps/api/app/storage/paths.py`
- Test: `apps/api/tests/storage/__init__.py` (empty), `apps/api/tests/storage/test_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/storage/test_paths.py
import uuid

from app.storage.paths import build_object_key, slug_filename


def test_slug_filename_removes_unsafe_chars():
    assert slug_filename("Коммерческое предложение!!!  v3.pdf") == "kommercheskoe-predlozhenie-v3.pdf"
    assert slug_filename("../etc/passwd") == "etc-passwd"
    assert slug_filename("файл с пробелами.docx") == "fail-s-probelami.docx"


def test_slug_filename_preserves_extension():
    assert slug_filename("Invoice 2026/05.xlsx") == "invoice-2026-05.xlsx"


def test_slug_filename_handles_empty_or_dotfile():
    assert slug_filename("") == "file"
    assert slug_filename(".hidden") == "hidden"
    assert slug_filename("noext") == "noext"


def test_build_object_key_layout():
    ws = uuid.UUID("00000000-0000-0000-0000-000000000001")
    lead = uuid.UUID("00000000-0000-0000-0000-000000000002")
    act = uuid.UUID("00000000-0000-0000-0000-000000000003")
    key = build_object_key(workspace_id=ws, lead_id=lead, activity_id=act, filename="Invoice v3.pdf")
    assert key == "00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002/00000000-0000-0000-0000-000000000003/invoice-v3.pdf"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/storage/test_paths.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.storage.paths'`.

- [ ] **Step 3: Write the helper**

```python
# apps/api/app/storage/paths.py
"""Pure helpers for computing storage object keys + sluggifying filenames.

Path layout: `{workspace_id}/{lead_id}/{activity_id}/{sluggified_filename}`.
Sluggification: lowercase, strip diacritics, ASCII transliteration for Cyrillic,
collapse non-[a-z0-9.] runs into a single hyphen, preserve the extension.
"""
from __future__ import annotations

import re
import unicodedata
import uuid

# Cyrillic → Latin (rough but stable; we only need a safe filesystem key)
_CYRILLIC_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def _ascii_fold(s: str) -> str:
    # NFKD + drop combining marks, then translate Cyrillic
    s = s.lower()
    s = s.translate(_CYRILLIC_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def slug_filename(name: str) -> str:
    """Return a safe-for-storage filename. Preserves the extension."""
    raw = (name or "").strip()
    if not raw:
        return "file"
    # Split last extension (everything after final dot, if it's short and alphanumeric)
    if "." in raw:
        stem, _, ext = raw.rpartition(".")
        if not stem:  # ".hidden" → stem="", ext="hidden"
            stem, ext = ext, ""
    else:
        stem, ext = raw, ""
    stem_ascii = _ascii_fold(stem)
    ext_ascii = _ascii_fold(ext)
    stem_safe = re.sub(r"[^a-z0-9]+", "-", stem_ascii).strip("-")
    ext_safe = re.sub(r"[^a-z0-9]+", "", ext_ascii)
    if not stem_safe and not ext_safe:
        return "file"
    if ext_safe:
        return f"{stem_safe or 'file'}.{ext_safe}"
    return stem_safe or "file"


def build_object_key(
    *, workspace_id: uuid.UUID, lead_id: uuid.UUID, activity_id: uuid.UUID, filename: str
) -> str:
    """Storage key: `{ws}/{lead}/{activity}/{slug}`. Stable per Activity row."""
    return f"{workspace_id}/{lead_id}/{activity_id}/{slug_filename(filename)}"
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/storage/test_paths.py -v
```
Expected: 4 passed.

```bash
git add apps/api/app/storage/__init__.py apps/api/app/storage/paths.py apps/api/tests/storage/
git commit -m "feat(storage): path helpers + filename slug (pure)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: SupabaseStorageClient (httpx wrapper)

**Files:**
- Create: `apps/api/app/storage/client.py`
- Test: `apps/api/tests/storage/test_client.py`
- Modify: `apps/api/app/config.py` (add bucket setting)
- Modify: `apps/api/.env.example` (document)

- [ ] **Step 1: Add the bucket config**

In `apps/api/app/config.py`, find the existing `supabase_*` block (around lines 33–39) and add:

```python
    supabase_storage_bucket: str = "lead-files"
```

In `apps/api/.env.example` add a line after the existing `SUPABASE_SECRET_KEY=` entry:
```
SUPABASE_STORAGE_BUCKET=lead-files
```

- [ ] **Step 2: Write the failing test**

```python
# apps/api/tests/storage/test_client.py
"""Httpx-mocked tests for SupabaseStorageClient. The client is a thin REST wrapper;
no network IO in tests."""
import pytest
import respx
from httpx import Response

from app.storage.client import SupabaseStorageClient, StorageError


@pytest.mark.asyncio
@respx.mock
async def test_upload_object_posts_to_storage_with_service_key():
    route = respx.post(
        "https://example.supabase.co/storage/v1/object/lead-files/ws/lead/act/file.pdf"
    ).mock(return_value=Response(200, json={"Key": "lead-files/ws/lead/act/file.pdf"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="srv-key",
    )
    await c.upload(key="ws/lead/act/file.pdf", content=b"PDF", content_type="application/pdf")
    assert route.called
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer srv-key"
    assert req.headers["Content-Type"] == "application/pdf"
    assert req.content == b"PDF"


@pytest.mark.asyncio
@respx.mock
async def test_upload_raises_storage_error_on_4xx():
    respx.post(
        "https://example.supabase.co/storage/v1/object/lead-files/ws/lead/act/x.pdf"
    ).mock(return_value=Response(409, json={"error": "Duplicate"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="k",
    )
    with pytest.raises(StorageError, match="409"):
        await c.upload(key="ws/lead/act/x.pdf", content=b"x", content_type="application/pdf")


@pytest.mark.asyncio
@respx.mock
async def test_create_signed_url_returns_full_url():
    route = respx.post(
        "https://example.supabase.co/storage/v1/object/sign/lead-files/ws/lead/act/file.pdf"
    ).mock(return_value=Response(200, json={"signedURL": "/object/sign/lead-files/ws/lead/act/file.pdf?token=abc"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="k",
    )
    url = await c.create_signed_url(key="ws/lead/act/file.pdf", expires_in=300)
    assert route.called
    body = route.calls.last.request.read()
    assert b'"expiresIn":300' in body or b'"expiresIn": 300' in body
    assert url == "https://example.supabase.co/storage/v1/object/sign/lead-files/ws/lead/act/file.pdf?token=abc"


@pytest.mark.asyncio
@respx.mock
async def test_delete_object_swallows_404():
    """Deletion is best-effort — a 404 (already gone) must not raise."""
    respx.delete(
        "https://example.supabase.co/storage/v1/object/lead-files/missing/file.pdf"
    ).mock(return_value=Response(404, json={"error": "Not found"}))
    c = SupabaseStorageClient(
        base_url="https://example.supabase.co",
        bucket="lead-files",
        service_key="k",
    )
    await c.delete(key="missing/file.pdf")  # must not raise
```

- [ ] **Step 3: Add the test deps** (skip if already present)

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pip install respx
```
(If your local env uses `uv add`, use that instead; otherwise `pip install respx` is fine for test-only use. Also add `respx` to the test deps in `pyproject.toml` under `[project.optional-dependencies].test` or wherever pytest deps live — match the existing pattern.)

- [ ] **Step 4: Run to confirm failure**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/storage/test_client.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 5: Write the client**

```python
# apps/api/app/storage/client.py
"""Async Supabase Storage client — thin httpx wrapper, no SDK dependency.

API reference: https://supabase.com/docs/reference/storage. We only use three
endpoints: upload (POST /object/{bucket}/{key}), sign (POST /object/sign/{bucket}/{key}),
delete (DELETE /object/{bucket}/{key}).
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Raised when Supabase Storage returns a non-2xx (except delete-404 which is swallowed)."""


class SupabaseStorageClient:
    def __init__(self, *, base_url: str, bucket: str, service_key: str, timeout_seconds: float = 30.0):
        self._base = base_url.rstrip("/")
        self._bucket = bucket
        self._service_key = service_key
        self._timeout = timeout_seconds

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._service_key}"}
        if extra:
            h.update(extra)
        return h

    async def upload(self, *, key: str, content: bytes, content_type: str) -> None:
        """PUT-like upload via POST /object/{bucket}/{key} with binary body.
        Overwrites if the same key already exists (we include x-upsert: true)."""
        url = f"{self._base}/storage/v1/object/{self._bucket}/{key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                content=content,
                headers=self._headers({"Content-Type": content_type, "x-upsert": "true"}),
            )
        if resp.status_code // 100 != 2:
            raise StorageError(f"upload failed [{resp.status_code}]: {resp.text[:200]}")

    async def create_signed_url(self, *, key: str, expires_in: int = 300) -> str:
        """POST /object/sign/{bucket}/{key} → returns an absolute URL valid for `expires_in` seconds."""
        url = f"{self._base}/storage/v1/object/sign/{self._bucket}/{key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                json={"expiresIn": expires_in},
                headers=self._headers({"Content-Type": "application/json"}),
            )
        if resp.status_code // 100 != 2:
            raise StorageError(f"sign failed [{resp.status_code}]: {resp.text[:200]}")
        signed_path = resp.json().get("signedURL") or resp.json().get("signedUrl") or ""
        if not signed_path:
            raise StorageError(f"sign response missing signedURL: {resp.text[:200]}")
        # Supabase returns a relative path beginning with /object/sign/...; make it absolute.
        if signed_path.startswith("/"):
            return f"{self._base}/storage/v1{signed_path}" if signed_path.startswith("/object") else f"{self._base}{signed_path}"
        return signed_path

    async def delete(self, *, key: str) -> None:
        """DELETE /object/{bucket}/{key} — best-effort. 404 (already gone) is swallowed."""
        url = f"{self._base}/storage/v1/object/{self._bucket}/{key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.delete(url, headers=self._headers())
        if resp.status_code == 404:
            log.info("storage.delete: object already gone", extra={"key": key})
            return
        if resp.status_code // 100 != 2:
            raise StorageError(f"delete failed [{resp.status_code}]: {resp.text[:200]}")


@lru_cache(maxsize=1)
def get_storage_client() -> SupabaseStorageClient:
    """Singleton storage client, constructed from settings.
    Reset between worker restarts; no per-request overhead since httpx clients
    are opened/closed per call (keeps connection management simple)."""
    s = get_settings()
    return SupabaseStorageClient(
        base_url=s.supabase_url,
        bucket=s.supabase_storage_bucket,
        service_key=s.supabase_secret_key,
    )
```

> **Implementer note:** verify the test signed-URL assertion against the real Supabase response shape — the v2 storage API returns `{"signedURL": "/object/sign/...?token=..."}`. If your local Supabase is on v1 and returns a full URL, the `if signed_path.startswith("/")` branch covers it.

- [ ] **Step 6: Run + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/storage/ -v
```
Expected: 4 (paths) + 4 (client) = 8 passed.

```bash
git add apps/api/app/storage/client.py apps/api/tests/storage/test_client.py apps/api/app/config.py apps/api/.env.example apps/api/pyproject.toml
git commit -m "feat(storage): SupabaseStorageClient (httpx) + bucket setting

Async REST wrapper for upload/sign/delete on the lead-files bucket.
No supabase-py dependency. Best-effort delete (404 swallowed).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 1 — DB index for the parent_task lookup

### Task 3: Migration 0037 — GIN expression index

**Files:**
- Create: `apps/api/alembic/versions/20260523_0037_activity_payload_parent_task_index.py`

This index makes `WHERE payload_json->>'parent_task_id' = '<uuid>'` a fast lookup. Without it, listing files for a task scans the whole activities table.

- [ ] **Step 1: Write the migration**

```python
# apps/api/alembic/versions/20260523_0037_activity_payload_parent_task_index.py
"""Activity payload parent_task_id index — fast lookup of task attachments.

Revision ID: 0037_activity_payload_parent_task_index
Revises: 0036_base_update_tables
Create Date: 2026-05-23
"""
from alembic import op

revision = "0037_activity_payload_parent_task_index"
down_revision = "0036_base_update_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # B-tree on the JSON-extract expression. Partial-WHERE excludes non-file rows
    # so the index stays small (we expect 90%+ of activities to be comments/tasks).
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_activities_parent_task_id
        ON activities ((payload_json->>'parent_task_id'))
        WHERE type = 'file'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_activities_parent_task_id")
```

- [ ] **Step 2: Verify static**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/python -m py_compile alembic/versions/20260523_0037_activity_payload_parent_task_index.py
./.venv/bin/alembic heads
```
Expected: no output; heads list ends with `0037_activity_payload_parent_task_index (head)`.

If there's a local Postgres, run `./.venv/bin/alembic upgrade head` then `downgrade -1 && upgrade head` to round-trip. If not, the offline SQL render is enough (`alembic upgrade 0037_activity_payload_parent_task_index --sql` — note the same pre-existing 0002 issue may stop you; that's fine).

- [ ] **Step 3: Commit**

```bash
git add apps/api/alembic/versions/20260523_0037_activity_payload_parent_task_index.py
git commit -m "feat(activity): migration 0037 — partial GIN on payload_json.parent_task_id

Fast lookup of files-for-a-task. Partial WHERE type='file' keeps it small.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Domain logic (files glue)

### Task 4: Upload validation + file kind detection

**Files:**
- Create: `apps/api/app/activity/files.py` (first slice — validators)
- Test: `apps/api/tests/activity/test_files_validators.py`

Pure validators decide MIME + extension before any storage touch.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/activity/test_files_validators.py
import pytest

from app.activity.files import (
    MAX_FILE_BYTES,
    FileTooLarge,
    UnsupportedFileType,
    classify_upload,
)


def test_classify_pdf():
    kind, content_type = classify_upload(filename="report.pdf", size=1234, content_head=b"%PDF-1.7")
    assert kind == "pdf"
    assert content_type == "application/pdf"


def test_classify_image():
    kind, _ = classify_upload(filename="photo.jpg", size=10, content_head=b"\xff\xd8\xff\xe0")
    assert kind == "image"


def test_classify_xlsx():
    kind, ct = classify_upload(filename="data.xlsx", size=5, content_head=b"PK\x03\x04")
    assert kind == "spreadsheet"
    assert "spreadsheet" in ct or ct == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_classify_audio():
    kind, _ = classify_upload(filename="call.mp3", size=5, content_head=b"ID3\x03")
    assert kind == "audio"


def test_classify_plain_text():
    kind, _ = classify_upload(filename="notes.txt", size=10, content_head=b"hello")
    assert kind == "text"


def test_classify_rejects_executable():
    with pytest.raises(UnsupportedFileType):
        classify_upload(filename="payload.exe", size=10, content_head=b"MZ\x90\x00")


def test_classify_rejects_oversize():
    with pytest.raises(FileTooLarge):
        classify_upload(filename="movie.mp4", size=MAX_FILE_BYTES + 1, content_head=b"")


def test_classify_strips_double_extension_attack():
    """`invoice.pdf.exe` must be rejected — outer extension wins."""
    with pytest.raises(UnsupportedFileType):
        classify_upload(filename="invoice.pdf.exe", size=10, content_head=b"")
```

- [ ] **Step 2: Run to fail**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/activity/test_files_validators.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `files.py` first slice**

```python
# apps/api/app/activity/files.py
"""Task-file domain logic: upload validation, MIME detection, and the
service entry points used by the router."""
from __future__ import annotations

import logging
import mimetypes

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB per file


# Extension whitelist → (kind label, default content-type).
# `kind` is what we surface in UI (filterable in TaskFilesList).
_EXT_WHITELIST: dict[str, tuple[str, str]] = {
    "pdf":  ("pdf",         "application/pdf"),
    "doc":  ("document",    "application/msword"),
    "docx": ("document",    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xls":  ("spreadsheet", "application/vnd.ms-excel"),
    "xlsx": ("spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv":  ("spreadsheet", "text/csv"),
    "txt":  ("text",        "text/plain"),
    "md":   ("text",        "text/markdown"),
    "rtf":  ("text",        "application/rtf"),
    "png":  ("image",       "image/png"),
    "jpg":  ("image",       "image/jpeg"),
    "jpeg": ("image",       "image/jpeg"),
    "gif":  ("image",       "image/gif"),
    "webp": ("image",       "image/webp"),
    "heic": ("image",       "image/heic"),
    "mp3":  ("audio",       "audio/mpeg"),
    "wav":  ("audio",       "audio/wav"),
    "m4a":  ("audio",       "audio/mp4"),
    "ogg":  ("audio",       "audio/ogg"),
}


class UnsupportedFileType(ValueError):
    pass


class FileTooLarge(ValueError):
    pass


def classify_upload(*, filename: str, size: int, content_head: bytes) -> tuple[str, str]:
    """Return `(kind, content_type)` or raise. Outer extension wins
    (so `invoice.pdf.exe` is rejected on the `.exe`)."""
    if size > MAX_FILE_BYTES:
        raise FileTooLarge(f"file size {size} > limit {MAX_FILE_BYTES}")
    name = (filename or "").lower().strip()
    if "." not in name:
        raise UnsupportedFileType(f"no extension on {filename!r}")
    ext = name.rsplit(".", 1)[-1]
    if ext not in _EXT_WHITELIST:
        raise UnsupportedFileType(f"unsupported extension .{ext}")
    kind, default_ct = _EXT_WHITELIST[ext]
    # Optional: cross-check the file's magic bytes for known signatures. We don't
    # gate on them (the LLM-uploaded .md case showed sniffing is brittle); we
    # just use mimetypes.guess as a tiebreaker.
    guessed, _ = mimetypes.guess_type(name)
    content_type = guessed if guessed else default_ct
    _ = content_head  # reserved for future magic-byte sniffing
    return kind, content_type
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/activity/test_files_validators.py -v
```
Expected: 8 passed.

```bash
git add apps/api/app/activity/files.py apps/api/tests/activity/test_files_validators.py
git commit -m "feat(activity): file-upload classify + size/extension guards

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Service `upload_task_file` + `list_task_files` + `delete_file_activity`

**Files:**
- Modify: `apps/api/app/activity/files.py` (add service functions at the bottom)
- Modify: `apps/api/app/activity/repositories.py` (add `find_files_by_parent_task`)
- Test: `apps/api/tests/activity/test_task_files.py`

These touch the DB. Smoke tests use mocked storage + an in-memory ORM session pattern (no Postgres needed for the dispatch/decision logic).

- [ ] **Step 1: Append the repository helper**

In `apps/api/app/activity/repositories.py`, add (don't replace anything):

```python
from sqlalchemy import select, text


async def find_files_by_parent_task(
    db, *, workspace_id, lead_id, task_id, q: str | None = None
):
    """All file-activities whose payload_json.parent_task_id == task_id, optionally
    ILIKE-filtered on filename or body."""
    from app.activity.models import Activity, ActivityType
    stmt = (
        select(Activity)
        .where(
            Activity.lead_id == lead_id,
            Activity.workspace_id == workspace_id,
            Activity.type == ActivityType.file.value,
            text("payload_json->>'parent_task_id' = :tid").bindparams(tid=str(task_id)),
        )
        .order_by(Activity.created_at.desc())
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (text("payload_json->>'file_name' ILIKE :q").bindparams(q=like))
            | (Activity.body.ilike(like))
        )
    return list((await db.execute(stmt)).scalars().all())
```

> **Implementer note:** verify that the existing `Activity` model has `workspace_id` (it's noted in the reference). If it doesn't (`lead_id` alone is enough to scope), drop the `workspace_id` filter — the lead's own workspace_id is verified by the router's `_get_lead_or_raise`.

- [ ] **Step 2: Append service functions to `files.py`**

```python
# === Service entrypoints ===

import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity, ActivityType
from app.activity.repositories import find_files_by_parent_task
from app.storage.client import StorageError, get_storage_client
from app.storage.paths import build_object_key


async def upload_task_file(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    user_id: uuid.UUID,
    parent_task_id: uuid.UUID,
    filename: str,
    content: bytes,
    content_type: str,
    kind: str,
    caption: str | None,
) -> Activity:
    """Create an Activity(type=file) row and upload bytes to storage.

    Persistence first (so storage isn't holding orphans on DB failure), THEN
    storage upload. If storage fails, we surface the error to the caller and
    rely on the orphan-purger to mop up the Activity. (A two-phase commit is
    overkill for v1; the rare failure mode leaves an Activity with a dead
    storage path, which the UI handles by showing a broken-link state.)
    """
    activity = Activity(
        lead_id=lead_id,
        workspace_id=workspace_id,
        user_id=user_id,
        type=ActivityType.file.value,
        body=(caption or "").strip() or None,
        file_kind=kind,
        payload_json={
            "parent_task_id": str(parent_task_id),
            "file_name": filename,
            "file_size": len(content),
            "source": "task_file_upload",
        },
    )
    db.add(activity)
    await db.flush()  # we need activity.id for the storage key

    key = build_object_key(
        workspace_id=workspace_id,
        lead_id=lead_id,
        activity_id=activity.id,
        filename=filename,
    )
    activity.file_url = key  # store the path, not a signed URL
    try:
        client = get_storage_client()
        await client.upload(key=key, content=content, content_type=content_type)
    except StorageError as exc:
        log.warning("task_file.upload_storage_failed", extra={"activity_id": str(activity.id), "error": str(exc)[:200]})
        # We re-raise; the caller (router) commits only on success
        raise
    return activity


async def list_task_files(
    db: AsyncSession, *, workspace_id: uuid.UUID, lead_id: uuid.UUID, task_id: uuid.UUID, q: str | None
) -> list[Activity]:
    return await find_files_by_parent_task(
        db, workspace_id=workspace_id, lead_id=lead_id, task_id=task_id, q=q
    )


async def signed_download_url(activity: Activity) -> str:
    """5-minute signed URL for an Activity(type=file)."""
    if activity.type != ActivityType.file.value or not activity.file_url:
        raise ValueError("activity is not a file")
    client = get_storage_client()
    return await client.create_signed_url(key=activity.file_url, expires_in=300)


async def delete_file_activity(db: AsyncSession, activity: Activity) -> None:
    """Best-effort: delete the storage object first, then the Activity row.
    Storage failure is logged, never raised — the row is still removed."""
    if activity.type == ActivityType.file.value and activity.file_url:
        try:
            client = get_storage_client()
            await client.delete(key=activity.file_url)
        except StorageError as exc:
            log.warning("task_file.delete_storage_failed", extra={"activity_id": str(activity.id), "error": str(exc)[:200]})
    await db.delete(activity)
```

- [ ] **Step 3: Write the service smoke test**

```python
# apps/api/tests/activity/test_task_files.py
"""Service-level tests using a real in-memory ORM pattern with monkeypatched
storage. No Postgres required."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.activity import files as svc
from app.activity.models import ActivityType


@pytest.mark.asyncio
async def test_upload_persists_activity_and_writes_to_storage(monkeypatch):
    """db.add → flush gives us id; we then call storage.upload with the computed key."""
    db = SimpleNamespace()
    added = []
    db.add = lambda obj: added.append(obj)

    async def fake_flush():
        added[0].id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    db.flush = fake_flush

    fake_client = SimpleNamespace(upload=AsyncMock())
    monkeypatch.setattr(svc, "get_storage_client", lambda: fake_client)

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
    # storage key is the slugified path
    assert activity.file_url == f"{ws}/{lead}/11111111-1111-1111-1111-111111111111/invoice-v3.pdf"
    fake_client.upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_propagates_storage_error(monkeypatch):
    from app.storage.client import StorageError
    db = SimpleNamespace()
    db.add = lambda _: None
    async def fake_flush():
        db._added.id = uuid.uuid4()  # any id
    db.flush = fake_flush
    db._added = None

    # Capture the added activity
    real_add = db.add
    def capture(obj):
        db._added = obj
        real_add(obj)
    db.add = capture

    fake_client = SimpleNamespace(upload=AsyncMock(side_effect=StorageError("upload failed [500]: x")))
    monkeypatch.setattr(svc, "get_storage_client", lambda: fake_client)

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
    db = SimpleNamespace()
    db.delete = AsyncMock()
    fake_client = SimpleNamespace(delete=AsyncMock(side_effect=StorageError("500")))
    monkeypatch.setattr(svc, "get_storage_client", lambda: fake_client)
    activity = SimpleNamespace(type=ActivityType.file.value, file_url="ws/lead/act/file.pdf", id="x")
    await svc.delete_file_activity(db, activity)  # must not raise
    fake_client.delete.assert_awaited_once()
    db.delete.assert_awaited_once_with(activity)


@pytest.mark.asyncio
async def test_signed_download_url_rejects_non_file_activity():
    activity = SimpleNamespace(type="comment", file_url="ws/lead/act/file.pdf")
    with pytest.raises(ValueError):
        await svc.signed_download_url(activity)
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/activity/test_task_files.py tests/activity/test_files_validators.py -v
```
Expected: 8 + 4 = 12 passed.

```bash
git add apps/api/app/activity/files.py apps/api/app/activity/repositories.py apps/api/tests/activity/test_task_files.py
git commit -m "feat(activity): task-file service — upload/list/delete/sign

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — REST API

### Task 6: Files router

**Files:**
- Create: `apps/api/app/activity/files_router.py`
- Modify: `apps/api/app/main.py` (register router)
- Test: `apps/api/tests/activity/test_files_api.py`

- [ ] **Step 1: Write the router**

```python
# apps/api/app/activity/files_router.py
"""REST endpoints for task file attachments."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import files as svc
from app.activity.files import FileTooLarge, UnsupportedFileType, classify_upload
from app.activity.models import Activity, ActivityType
from app.activity.repositories import find_files_by_parent_task
from app.activity.services import _get_lead_or_raise  # workspace-scoping helper
from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db

router = APIRouter(tags=["activity-files"])


class TaskFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    body: str | None = None
    file_kind: str | None = None
    file_name: str
    file_size: int
    parent_task_id: uuid.UUID | None = None
    created_at: object  # datetime — Pydantic will accept it

    @classmethod
    def from_activity(cls, a: Activity) -> "TaskFileOut":
        pj = a.payload_json or {}
        return cls(
            id=a.id, type=a.type, body=a.body, file_kind=a.file_kind,
            file_name=pj.get("file_name") or "unknown",
            file_size=int(pj.get("file_size") or 0),
            parent_task_id=uuid.UUID(pj["parent_task_id"]) if pj.get("parent_task_id") else None,
            created_at=a.created_at,
        )


class DownloadOut(BaseModel):
    url: str
    expires_in: int


@router.post(
    "/leads/{lead_id}/tasks/{task_id}/files",
    response_model=TaskFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload(
    lead_id: uuid.UUID,
    task_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    caption: Annotated[str | None, Form()] = None,
) -> TaskFileOut:
    await _get_lead_or_raise(db, lead_id, user.workspace_id)

    # Bounded read (defends against header lying about size)
    raw = await file.read(svc.MAX_FILE_BYTES + 1)
    if len(raw) > svc.MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty file")

    try:
        kind, content_type = classify_upload(
            filename=file.filename or "",
            size=len(raw),
            content_head=raw[:64],
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileTooLarge as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc

    activity = await svc.upload_task_file(
        db,
        workspace_id=user.workspace_id,
        lead_id=lead_id,
        user_id=user.id,
        parent_task_id=task_id,
        filename=file.filename or "file",
        content=raw,
        content_type=content_type,
        kind=kind,
        caption=caption,
    )
    await db.commit()
    return TaskFileOut.from_activity(activity)


@router.get(
    "/leads/{lead_id}/tasks/{task_id}/files",
    response_model=list[TaskFileOut],
)
async def list_files(
    lead_id: uuid.UUID,
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    q: str | None = None,
) -> list[TaskFileOut]:
    await _get_lead_or_raise(db, lead_id, user.workspace_id)
    rows = await find_files_by_parent_task(
        db, workspace_id=user.workspace_id, lead_id=lead_id, task_id=task_id, q=q
    )
    return [TaskFileOut.from_activity(r) for r in rows]


@router.get(
    "/activities/{activity_id}/download",
    response_model=DownloadOut,
)
async def download(
    activity_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> DownloadOut:
    # Workspace-scope the lookup: join via the lead.
    from sqlalchemy import select
    activity = (
        await db.execute(
            select(Activity).where(
                Activity.id == activity_id,
                Activity.workspace_id == user.workspace_id,
                Activity.type == ActivityType.file.value,
            )
        )
    ).scalar_one_or_none()
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file not found")
    url = await svc.signed_download_url(activity)
    return DownloadOut(url=url, expires_in=300)


@router.delete(
    "/activities/{activity_id}/file",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete(
    activity_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    from sqlalchemy import select
    activity = (
        await db.execute(
            select(Activity).where(
                Activity.id == activity_id,
                Activity.workspace_id == user.workspace_id,
                Activity.type == ActivityType.file.value,
            )
        )
    ).scalar_one_or_none()
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file not found")
    await svc.delete_file_activity(db, activity)
    await db.commit()
```

- [ ] **Step 2: Register router**

In `apps/api/app/main.py`, find the existing router include block and add:

```python
from app.activity.files_router import router as activity_files_router
app.include_router(activity_files_router)
```

- [ ] **Step 3: Write the API test**

```python
# apps/api/tests/activity/test_files_api.py
"""Pure helpers + route registration smoke. The HTTP→storage e2e runs only on CI
with a real Postgres + Supabase config."""
import pytest


def test_routes_registered():
    from app.main import app
    paths = {r.path for r in app.routes}
    expected = {
        "/leads/{lead_id}/tasks/{task_id}/files",
        "/activities/{activity_id}/download",
        "/activities/{activity_id}/file",
    }
    assert expected.issubset(paths), f"missing: {expected - paths}"


def test_task_file_out_extracts_payload_fields():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from app.activity.files_router import TaskFileOut

    a = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type="file",
        body="caption",
        file_kind="pdf",
        payload_json={"parent_task_id": "22222222-2222-2222-2222-222222222222", "file_name": "x.pdf", "file_size": 42},
        created_at=datetime.now(timezone.utc),
    )
    dto = TaskFileOut.from_activity(a)
    assert dto.file_name == "x.pdf"
    assert dto.file_size == 42
    assert str(dto.parent_task_id) == "22222222-2222-2222-2222-222222222222"
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/pytest tests/activity/ -v
```
Expected: 8 (validators + service) + 2 (api) = 10 passed (plus any pre-existing activity tests still green).

```bash
git add apps/api/app/activity/files_router.py apps/api/app/main.py apps/api/tests/activity/test_files_api.py
git commit -m "feat(activity): REST endpoints for task file attachments

POST /leads/{id}/tasks/{tid}/files (multipart, ≤25 MB, type whitelist)
GET  /leads/{id}/tasks/{tid}/files (optional ?q= filename/body ILIKE)
GET  /activities/{id}/download (5-min signed URL)
DELETE /activities/{id}/file (storage cleanup + Activity row)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Frontend

### Task 7: Types + hooks

**Files:**
- Modify: `apps/web/lib/types.ts` — add `TaskFileOut`.
- Create: `apps/web/lib/hooks/use-task-files.ts`

- [ ] **Step 1: Add the type**

Append to `apps/web/lib/types.ts`:

```typescript
// ---------- task file attachments ----------

export interface TaskFileOut {
  id: string;
  type: "file";
  body: string | null;            // caption
  file_kind: string | null;       // "pdf" | "image" | "audio" | "spreadsheet" | "text" | "document"
  file_name: string;              // original filename
  file_size: number;              // bytes
  parent_task_id: string | null;
  created_at: string;
}
```

- [ ] **Step 2: Write the hooks**

```typescript
// apps/web/lib/hooks/use-task-files.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { TaskFileOut } from "@/lib/types";

export function useTaskFiles(leadId: string, taskId: string, q?: string) {
  return useQuery<TaskFileOut[]>({
    queryKey: ["task-files", leadId, taskId, q ?? ""],
    queryFn: () =>
      api.get<TaskFileOut[]>(
        `/leads/${leadId}/tasks/${taskId}/files${q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
      ),
    enabled: !!leadId && !!taskId,
  });
}

export function useUploadTaskFile(leadId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation<TaskFileOut, Error, { file: File; caption?: string }>({
    mutationFn: async ({ file, caption }) => {
      const form = new FormData();
      form.append("file", file);
      if (caption) form.append("caption", caption);
      return await api.postFormData<TaskFileOut>(
        `/leads/${leadId}/tasks/${taskId}/files`,
        form,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task-files", leadId, taskId] });
      qc.invalidateQueries({ queryKey: ["feed", leadId] }); // file activity also lands in the feed
    },
  });
}

export function useDownloadTaskFile() {
  return useMutation<{ url: string }, Error, string>({
    mutationFn: (activityId) =>
      api.get<{ url: string; expires_in: number }>(`/activities/${activityId}/download`).then(
        (r) => ({ url: r.url }),
      ),
  });
}

export function useDeleteTaskFile(leadId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (activityId) => api.delete<void>(`/activities/${activityId}/file`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task-files", leadId, taskId] });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
    },
  });
}
```

- [ ] **Step 3: Typecheck + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/web && npm run typecheck
```
Expected: 0 errors. (If `api.delete<void>` signature complains, check `api-client.ts` for the exact `delete<T>` shape and adjust.)

```bash
git add apps/web/lib/types.ts apps/web/lib/hooks/use-task-files.ts
git commit -m "feat(web): types + TanStack hooks for task file attachments

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Dropzone component

**Files:**
- Create: `apps/web/components/lead-card/TaskFileDropzone.tsx`

- [ ] **Step 1: Write the component**

```tsx
// apps/web/components/lead-card/TaskFileDropzone.tsx
"use client";

import { useRef, useState } from "react";
import { Loader2, Paperclip, X } from "lucide-react";
import { useUploadTaskFile } from "@/lib/hooks/use-task-files";

const ACCEPT = ".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.rtf,.png,.jpg,.jpeg,.gif,.webp,.heic,.mp3,.wav,.m4a,.ogg";
const MAX_MB = 25;

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

interface Props {
  leadId: string;
  taskId: string;
}

export function TaskFileDropzone({ leadId, taskId }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [picked, setPicked] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadTaskFile(leadId, taskId);

  function handlePick(file: File) {
    setError(null);
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`Слишком большой файл: ${fmtSize(file.size)} (лимит ${MAX_MB} МБ)`);
      return;
    }
    setPicked(file);
  }

  async function submit() {
    if (!picked || upload.isPending) return;
    setError(null);
    try {
      await upload.mutateAsync({ file: picked, caption: caption.trim() || undefined });
      setPicked(null);
      setCaption("");
    } catch (e) {
      setError((e as Error).message || "Не удалось загрузить");
    }
  }

  if (picked) {
    return (
      <div className="bg-brand-bg rounded-2xl p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="type-caption text-brand-primary truncate">
            {picked.name} · {fmtSize(picked.size)}
          </span>
          <button
            type="button"
            onClick={() => { setPicked(null); setCaption(""); setError(null); }}
            disabled={upload.isPending}
            aria-label="Отменить выбор"
            className="text-brand-muted hover:text-brand-primary disabled:opacity-40"
          >
            <X size={14} />
          </button>
        </div>
        <input
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="Подпись (необязательно)"
          disabled={upload.isPending}
          className="w-full px-3 py-1.5 rounded-full bg-white border border-brand-border type-caption outline-none focus:border-brand-accent"
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={submit}
            disabled={upload.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-brand-accent text-white hover:bg-brand-accent/90 disabled:opacity-40"
          >
            {upload.isPending && <Loader2 size={12} className="animate-spin" />}
            Загрузить
          </button>
          {error && <span className="type-caption text-rose">{error}</span>}
        </div>
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) handlePick(f);
      }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-3 text-center transition-colors ${
        dragOver ? "border-brand-accent bg-brand-soft" : "border-brand-border bg-white hover:border-brand-accent"
      }`}
    >
      <div className="inline-flex items-center gap-1.5 type-caption text-brand-muted">
        <Paperclip size={14} />
        Перетащите файл или нажмите, чтобы прикрепить
      </div>
      <p className="type-caption text-brand-muted mt-1">
        До {MAX_MB} МБ · pdf / image / xlsx / doc / txt / audio
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handlePick(f);
          e.target.value = ""; // allow re-selecting the same file
        }}
      />
      {error && <p className="type-caption text-rose mt-1">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/web && npm run typecheck
```

```bash
git add apps/web/components/lead-card/TaskFileDropzone.tsx
git commit -m "feat(web): TaskFileDropzone — drag/drop + caption + size guard

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Files list component

**Files:**
- Create: `apps/web/components/lead-card/TaskFilesList.tsx`

- [ ] **Step 1: Write the component**

```tsx
// apps/web/components/lead-card/TaskFilesList.tsx
"use client";

import { Download, FileText, Image as ImageIcon, FileSpreadsheet, FileAudio, Trash2 } from "lucide-react";
import { useTaskFiles, useDownloadTaskFile, useDeleteTaskFile } from "@/lib/hooks/use-task-files";

function kindIcon(kind: string | null) {
  switch (kind) {
    case "image": return <ImageIcon size={14} />;
    case "audio": return <FileAudio size={14} />;
    case "spreadsheet": return <FileSpreadsheet size={14} />;
    default: return <FileText size={14} />;
  }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

interface Props {
  leadId: string;
  taskId: string;
  q?: string;
}

export function TaskFilesList({ leadId, taskId, q }: Props) {
  const list = useTaskFiles(leadId, taskId, q);
  const download = useDownloadTaskFile();
  const remove = useDeleteTaskFile(leadId, taskId);

  if (list.isLoading) {
    return <p className="type-caption text-brand-muted">Загрузка…</p>;
  }
  const files = list.data ?? [];
  if (files.length === 0) {
    return <p className="type-caption text-brand-muted italic">Файлов нет</p>;
  }

  async function open(activityId: string) {
    const { url } = await download.mutateAsync(activityId);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <ul className="space-y-1.5">
      {files.map((f) => (
        <li key={f.id} className="flex items-center gap-2 px-3 py-2 rounded-2xl bg-brand-bg">
          <span className="text-brand-muted">{kindIcon(f.file_kind)}</span>
          <div className="flex-1 min-w-0">
            <p className="type-body text-brand-primary truncate">{f.file_name}</p>
            <p className="type-caption text-brand-muted">
              {fmtSize(f.file_size)}
              {f.body ? ` · ${f.body}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => open(f.id)}
            disabled={download.isPending}
            aria-label="Скачать"
            className="text-brand-muted hover:text-brand-accent disabled:opacity-40"
          >
            <Download size={14} />
          </button>
          <button
            type="button"
            onClick={() => { if (confirmDelete(f.file_name)) remove.mutate(f.id); }}
            disabled={remove.isPending}
            aria-label="Удалить файл"
            className="text-rose/70 hover:text-rose disabled:opacity-40"
          >
            <Trash2 size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function confirmDelete(name: string): boolean {
  // Per-file deletes are infrequent; an inline two-step would clutter the list.
  // We use a plain confirm here intentionally — matches the rest of the lead-card destructive ops
  // that have a dedicated modal (DeleteConfirmModal) which is overkill for one file.
  return window.confirm(`Удалить файл «${name}»?`);
}
```

> **Note:** `window.confirm` is OK here because (a) the file is replaceable (re-upload), (b) a custom inline confirm in a dense list is worse UX, and (c) the audit's `window.confirm` finding was about lead-level destruction (`NeedsReviewRow` «Не лид»). If a future audit complains, swap for the inline two-step pattern from `NeedsReviewRow`.

- [ ] **Step 2: Typecheck + commit**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/web && npm run typecheck
```

```bash
git add apps/web/components/lead-card/TaskFilesList.tsx
git commit -m "feat(web): TaskFilesList — download + delete + per-task scoped query

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Wire into TasksTab (search box + per-task dropzone + list)

**Files:**
- Modify: `apps/web/components/lead-card/TasksTab.tsx`

This is the integration step. The current `TasksTab` renders a flat list of task `<li>` rows. We add:
1. A search input at the top filtering tasks by `text` / `body`.
2. An expandable section under each task with `<TaskFilesList>` + `<TaskFileDropzone>`.

- [ ] **Step 1: Read the current state of `TasksTab.tsx`**

The file lives at `apps/web/components/lead-card/TasksTab.tsx`. Read it in full so the diff is surgical. Key state already there: `text`, `due`, `adding`, `rows`. Add: `expanded: Set<string>`, `search: string`.

- [ ] **Step 2: Apply the changes**

(a) Imports — add at the top:
```tsx
import { TaskFilesList } from "./TaskFilesList";
import { TaskFileDropzone } from "./TaskFileDropzone";
import { Paperclip, Search, ChevronDown } from "lucide-react";
```
(The exact lucide imports may already include some — keep the existing set and add only the missing ones.)

(b) State — add inside the component, alongside the existing `useState` declarations:
```tsx
const [search, setSearch] = useState("");
const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
```

(c) Filter `rows` by `search` — replace the existing `rows` memo:
```tsx
const rows = useMemo(() => {
  const sorted = [...(tasks ?? [])].sort((a, b) => {
    if (a.task_done !== b.task_done) return a.task_done ? 1 : -1;
    const ad = a.task_due_at ? new Date(a.task_due_at).getTime() : Infinity;
    const bd = b.task_due_at ? new Date(b.task_due_at).getTime() : Infinity;
    return ad - bd;
  });
  const q = search.trim().toLowerCase();
  if (!q) return sorted;
  return sorted.filter((a) => {
    const title = taskTitle(a).toLowerCase();
    const body = (a.body ?? "").toLowerCase();
    return title.includes(q) || body.includes(q);
  });
}, [tasks, search]);
```

(d) Add the search input right after the header (between `<h2>` and the `{adding && (...)}` block):
```tsx
<div className="mb-3 relative">
  <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted" />
  <input
    value={search}
    onChange={(e) => setSearch(e.target.value)}
    placeholder="Поиск по задачам и файлам"
    className={`w-full pl-8 pr-3 py-2 ${C.form.field}`}
  />
</div>
```

(e) In the row render, replace the existing `<li>...</li>` with an expandable variant. Show the file/expand affordance on every row; expand opens the files block:
```tsx
{!isLoading && !isError && rows.length > 0 && (
  <ul className="flex flex-col gap-1.5">
    {rows.map((a) => {
      const dueLabel = formatDue(a.task_due_at);
      const isExpanded = expanded.has(a.id);
      const toggle = () => setExpanded((s) => {
        const n = new Set(s);
        if (n.has(a.id)) n.delete(a.id); else n.add(a.id);
        return n;
      });
      return (
        <li key={a.id} className="rounded-2xl bg-brand-bg overflow-hidden">
          <div className="flex items-start gap-3 px-3 py-2.5">
            <button
              type="button"
              onClick={() => !a.task_done && completeTask.mutate(a.id)}
              disabled={a.task_done || completeTask.isPending}
              aria-label={a.task_done ? "Выполнено" : "Отметить выполненной"}
              className="shrink-0 mt-0.5 text-brand-muted hover:text-brand-accent transition-colors disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded"
            >
              {a.task_done ? <CheckSquare size={16} className="text-success" /> : <Square size={16} />}
            </button>
            <div className="flex-1 min-w-0">
              <p className={`type-body ${a.task_done ? "line-through text-brand-muted" : "text-brand-primary"}`}>
                {taskTitle(a)}
              </p>
              {dueLabel && (
                <span className="inline-flex items-center gap-1 type-caption text-brand-muted mt-0.5">
                  <Calendar size={11} /> до {dueLabel}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={toggle}
              aria-expanded={isExpanded}
              aria-label="Файлы"
              className="shrink-0 inline-flex items-center gap-1 type-caption text-brand-muted hover:text-brand-primary"
            >
              <Paperclip size={12} />
              <ChevronDown size={12} className={`transition-transform ${isExpanded ? "rotate-180" : ""}`} />
            </button>
          </div>
          {isExpanded && (
            <div className="px-3 pb-3 space-y-2 border-t border-brand-border/50 pt-2">
              <TaskFilesList leadId={leadId} taskId={a.id} q={search.trim() || undefined} />
              <TaskFileDropzone leadId={leadId} taskId={a.id} />
            </div>
          )}
        </li>
      );
    })}
  </ul>
)}
```

- [ ] **Step 3: Pre-PR checks (mandatory for routing-touching changes; this is safer to also run)**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/web && npm run typecheck && npm run lint && npm run build
```
Expected: all clean. (Build is required by `CLAUDE.md` because we touched a lead-card path; even without new `<Link>`s, run it.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/lead-card/TasksTab.tsx
git commit -m "feat(web): TasksTab — search + expandable file attachments per task

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Orphan cleanup (cron)

### Task 11: Weekly orphan-purger

**Files:**
- Modify: `apps/api/app/scheduled/jobs.py` — add `purge_orphan_storage_files`.
- Modify: `apps/api/app/scheduled/celery_app.py` — add beat entry.

**v1 scope:** sweep the bucket weekly, list all keys at the prefix `{workspace}/`, cross-reference against `Activity.file_url`; delete any key with no matching row. Conservative: only purge keys older than 7 days (avoid racing in-flight uploads).

- [ ] **Step 1: Append job + storage list helper**

In `apps/api/app/storage/client.py`, add a `list_objects` method:

```python
    async def list_objects(self, *, prefix: str = "", limit: int = 1000) -> list[dict]:
        """POST /object/list/{bucket} — paginated listing. Returns the items array."""
        url = f"{self._base}/storage/v1/object/list/{self._bucket}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                json={"prefix": prefix, "limit": limit, "offset": 0},
                headers=self._headers({"Content-Type": "application/json"}),
            )
        if resp.status_code // 100 != 2:
            raise StorageError(f"list failed [{resp.status_code}]: {resp.text[:200]}")
        data = resp.json()
        return data if isinstance(data, list) else []
```

Then in `apps/api/app/scheduled/jobs.py`, append:

```python
@celery_app.task(name="app.scheduled.jobs.purge_orphan_storage_files")
def purge_orphan_storage_files() -> dict:
    """Weekly: list lead-files bucket, drop objects with no Activity backing them.
    Conservative — skips objects modified in the last 7 days to avoid racing uploads."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.activity.models import Activity, ActivityType
    from app.storage.client import get_storage_client

    async def _core():
        engine, factory = _build_task_engine_and_factory()
        deleted = 0
        kept = 0
        try:
            async with factory() as db:
                live_keys = set(
                    (
                        await db.execute(
                            select(Activity.file_url).where(
                                Activity.type == ActivityType.file.value,
                                Activity.file_url.is_not(None),
                            )
                        )
                    ).scalars().all()
                )
            client = get_storage_client()
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            for obj in await client.list_objects(prefix="", limit=1000):
                key = obj.get("name") or ""
                modified = obj.get("updated_at") or obj.get("created_at") or ""
                try:
                    mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    mod_dt = datetime.now(timezone.utc)
                if mod_dt > cutoff:
                    kept += 1
                    continue
                if key not in live_keys:
                    try:
                        await client.delete(key=key)
                        deleted += 1
                    except Exception:
                        # best-effort; will retry next week
                        pass
        finally:
            await engine.dispose()
        return {"job": "purge_orphan_storage_files", "deleted": deleted, "kept_recent": kept}

    return asyncio.run(_core())
```

- [ ] **Step 2: Add beat entry**

In `apps/api/app/scheduled/celery_app.py`, find `celery_app.conf.beat_schedule = { ... }` and add:

```python
    "purge-orphan-storage-files": {
        "task": "app.scheduled.jobs.purge_orphan_storage_files",
        "schedule": crontab(hour=3, minute=30, day_of_week=0),  # Sundays 03:30 UTC
    },
```

- [ ] **Step 3: Verify task registry**

```bash
cd /Users/aleksandrhvastunov/Desktop/drinkx-crm/apps/api && ./.venv/bin/python -c "
import app.scheduled.jobs  # force task import
from app.scheduled.celery_app import celery_app
assert 'app.scheduled.jobs.purge_orphan_storage_files' in celery_app.tasks
print('ok')
"
```
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/scheduled/jobs.py apps/api/app/scheduled/celery_app.py apps/api/app/storage/client.py
git commit -m "feat(storage): weekly orphan-file purger (Celery beat, Sundays 03:30 UTC)

list_objects added to the storage client. Cross-references against
Activity.file_url; only deletes objects older than 7 days to avoid
racing in-flight uploads.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Docs

### Task 12: Feature documentation

**Files:**
- Create: `docs/features/task-file-attachments.md`
- Modify: `docs/brain/00_CURRENT_STATE.md` (one-line note about the new domain)

- [ ] **Step 1: Write the feature doc**

```markdown
# Вложения файлов к задачам

> **Что это.** К задаче в карточке лида менеджер может прикрепить
> файл (PDF, картинка, документ, таблица, аудио, текст; ≤25 МБ).
> Файлы лежат в приватном бакете Supabase Storage; ссылка для скачивания
> подписывается на 5 минут.

## Скоуп

Поиск v1: по имени файла + тексту задачи (ILIKE). Извлечение содержимого
(текст PDF, расшифровка аудио) **в скоупе не входит** — следующая итерация.

Доступ: любой `current_user` лида (workspace-scoped через `_get_lead_or_raise`).

## Архитектура

Файл — это `Activity(type="file")` с привязкой к задаче через
`payload_json.parent_task_id = <task_activity_id>`. Storage-ключ:
`{workspace_id}/{lead_id}/{activity_id}/{slug(filename)}`.

```
1. UPLOAD     POST /leads/{lead_id}/tasks/{task_id}/files (multipart)
              ↓
              classify_upload — extension whitelist + size cap
              ↓
              create Activity(type=file) → db.flush() (нужен activity.id для ключа)
              ↓
              SupabaseStorageClient.upload(key=..., bytes, content_type) — httpx POST
              ↓
              activity.file_url = key (НЕ signed URL — путь в бакете)
              ↓
              db.commit() + 201 TaskFileOut
2. LIST       GET /leads/{lead_id}/tasks/{task_id}/files[?q=...]
              → ILIKE на payload_json.file_name + Activity.body
              → партиальный GIN-индекс ix_activities_parent_task_id
3. DOWNLOAD   GET /activities/{id}/download
              → SupabaseStorageClient.create_signed_url(key, expires_in=300)
              → 200 {url, expires_in}
4. DELETE     DELETE /activities/{id}/file
              → storage.delete (best-effort, 404 swallowed)
              → db.delete(activity); commit
```

## REST API

| Метод | Путь | Что делает |
|---|---|---|
| POST | `/leads/{id}/tasks/{tid}/files` | multipart `file` + optional `caption` → 201 TaskFileOut |
| GET  | `/leads/{id}/tasks/{tid}/files?q=…` | список файлов задачи (ILIKE по имени + body) |
| GET  | `/activities/{id}/download` | 5-min signed URL |
| DELETE | `/activities/{id}/file` | удаление storage + Activity |

## ⚠️ Подводные камни

1. **Storage и Activity не транзакционны.** Если storage.upload падает после
   db.flush(), Activity-строка существует с `file_url`, но в бакете файла нет.
   Поэтому: (а) роутер коммитит только при успехе upload; (б) ETL purger
   подчищает сирот в бакете еженедельно (Sunday 03:30 UTC).
2. **`file_url` хранит storage-путь, НЕ signed URL.** Signed URL генерится
   on-demand (5 мин TTL) — иначе ссылка протухает на стороне БД.
3. **Двойное расширение** (`invoice.pdf.exe`) ловится по последнему: `.exe`
   не в whitelist → 400.
4. **`window.confirm` в `TaskFilesList`** — намеренно, файл легко перезагрузить.
   Если аудит вернётся к этому — поменять на inline-двушаговое подтверждение
   как в `NeedsReviewRow`.
5. **Бакет приватный, RLS не настроен** — фронт ходит к Supabase Storage только
   через наш бэкенд. Если будут публичные ссылки на превью изображений — RLS
   нужен.
6. **Поиск ILIKE по `payload_json->>'file_name'`** уходит на партиальный
   B-tree-индекс (миграция 0037). При росте до сотен тысяч файлов рассмотреть
   GIN trgm-индекс на том же выражении.

## Тестовое покрытие

```
tests/storage/
  test_paths.py          4 ✓ — slug + key
  test_client.py         4 ✓ — httpx-mocked upload/sign/delete
tests/activity/
  test_files_validators  8 ✓ — extension whitelist + size guards
  test_task_files.py     4 ✓ — service layer + delete-best-effort
  test_files_api.py      2 ✓ — route registration + DTO
  ──────────────────────────
  Итого                 22 passed
```

Real-bucket integration test — отдельной таской, гонится только в CI
с `SUPABASE_STORAGE_BUCKET` и валидным `SUPABASE_SECRET_KEY`.
```

- [ ] **Step 2: Add the brain note**

In `docs/brain/00_CURRENT_STATE.md`, update the `Last updated:` line at the top to mention the new domain. Keep the previous note intact below; just prepend the new entry.

- [ ] **Step 3: Commit**

```bash
git add docs/features/task-file-attachments.md docs/brain/00_CURRENT_STATE.md
git commit -m "docs(task-file-attachments): feature doc + current-state note

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (run before opening the PR)

- **Spec coverage:** uploads (T4 + T6) ✓, list (T6) ✓, signed download (T6) ✓, delete (T6) ✓, search by filename + body (T5 repo + T10 wired in UI) ✓, ≤25 MB cap (T4 + T6 bounded read) ✓, type whitelist (T4) ✓, task binding via `parent_task_id` (T5) ✓, files visible in feed (existing `useFeed` invalidation in hooks) ✓, weekly orphan purger (T11) ✓. **Gap to watch:** content-extraction (PDF text, audio STT) — explicitly out of scope; mention in BACKLOG when this lands.
- **Type consistency:** `TaskFileOut.from_activity` reads `payload_json["parent_task_id"] / file_name / file_size` — these keys match `upload_task_file`'s persistence (`payload_json={"parent_task_id": ..., "file_name": ..., "file_size": ...}`). `Activity.file_url` is the storage key, not a signed URL — used consistently in `signed_download_url` and `delete_file_activity`. Constants: `MAX_FILE_BYTES = 25 MB`, `kind` whitelist values (`pdf | document | spreadsheet | text | image | audio`) match what `kindIcon()` switches on.
- **Placeholder scan:** no TBDs. Two intentional implementer-notes are left (Step 2 in Task 5 about the `workspace_id` column on `Activity` — needs codebase verification; Step 5 in Task 2 about the Supabase signed-URL response shape) — both are "verify and adapt" hints, not placeholders.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-23-task-file-attachments.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review.
2. **Inline Execution** — execute in this session with checkpoints.

Which approach?
