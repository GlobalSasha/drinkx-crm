"""Task-file domain logic: upload validation, MIME detection, and the
service entry points used by the router.

Service layer (upload_task_file / list_task_files / signed_download_url /
delete_file_activity) lands in a later task; this commit ships only the
pure validators."""
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


def _content_matches_ext(ext: str, head: bytes) -> bool:
    """True if the leading bytes are consistent with `ext`. Text-like
    extensions (csv/txt/md/rtf) have no binary signature to verify and
    always pass — they carry no executable risk. Binary types must match."""
    h = head
    if ext == "pdf":
        return h[:5] == b"%PDF-"
    if ext == "png":
        return h[:8] == b"\x89PNG\r\n\x1a\n"
    if ext in ("jpg", "jpeg"):
        return h[:3] == b"\xff\xd8\xff"
    if ext == "gif":
        return h[:6] in (b"GIF87a", b"GIF89a")
    if ext == "webp":
        return h[:4] == b"RIFF" and h[8:12] == b"WEBP"
    if ext == "wav":
        return h[:4] == b"RIFF" and h[8:12] == b"WAVE"
    if ext == "ogg":
        return h[:4] == b"OggS"
    if ext in ("heic", "m4a"):
        return h[4:8] == b"ftyp"  # ISO base-media box; brand follows
    if ext in ("docx", "xlsx"):
        return h[:4] == b"PK\x03\x04"  # OOXML = ZIP container
    if ext in ("doc", "xls"):
        return h[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE2 (legacy Office)
    if ext == "mp3":
        return h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    # csv, txt, md, rtf, and any other allowed text type: nothing to verify
    return True


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
    if not _content_matches_ext(ext, content_head):
        raise UnsupportedFileType(f"content does not match .{ext} signature")
    # Optional cross-check via mimetypes (tiebreaker)
    guessed, _ = mimetypes.guess_type(name)
    content_type = guessed if guessed else default_ct
    return kind, content_type


# === Service entrypoints ===

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity, ActivityType
from app.activity.repositories import find_files_by_parent_task
from app.storage.client import StorageError, get_storage_client
from app.storage.paths import build_object_key


async def upload_lead_file(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    user_id: uuid.UUID,
    parent_task_id: uuid.UUID | None,
    filename: str,
    content: bytes,
    content_type: str,
    kind: str,
    caption: str | None,
) -> Activity:
    """Create an Activity(type=file) row and upload bytes to storage.

    If parent_task_id is None, the file is a lead-level feed attachment
    (rendered in UnifiedFeed); otherwise it's attached to a task and
    shows up in the TasksTab/ArchiveTab file panel.

    The router commits the transaction only after this function returns
    cleanly. On StorageError we re-raise; the session rollback leaves the
    DB clean — there is no Activity row to clean up. The weekly
    orphan-purger handles the inverse case: the rare scenario where the
    storage upload succeeded but the request died before db.commit().
    """
    payload_json: dict = {
        "file_name": filename,
        "file_size": len(content),
        "source": "lead_file_upload" if parent_task_id is None else "task_file_upload",
    }
    if parent_task_id is not None:
        payload_json["parent_task_id"] = str(parent_task_id)

    activity_kwargs: dict = dict(
        lead_id=lead_id,
        user_id=user_id,
        type=ActivityType.file.value,
        body=(caption or "").strip() or None,
        file_kind=kind,
        payload_json=payload_json,
    )
    if hasattr(Activity, "workspace_id"):
        activity_kwargs["workspace_id"] = workspace_id

    activity = Activity(**activity_kwargs)
    db.add(activity)
    await db.flush()  # we need activity.id for the storage key

    key = build_object_key(
        workspace_id=workspace_id,
        lead_id=lead_id,
        activity_id=activity.id,
        filename=filename,
    )
    activity.file_url = key  # storage PATH, not signed URL
    try:
        client = get_storage_client()
        await client.upload(key=key, content=content, content_type=content_type)
    except StorageError as exc:
        log.warning(
            "task_file.upload_storage_failed",
            extra={"activity_id": str(activity.id), "error": str(exc)[:200]},
        )
        raise
    # Ensure server-default columns (created_at) are populated for the response DTO.
    await db.refresh(activity)
    return activity


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
    """Thin wrapper around upload_lead_file for task-scoped file attachments."""
    return await upload_lead_file(
        db,
        workspace_id=workspace_id,
        lead_id=lead_id,
        user_id=user_id,
        parent_task_id=parent_task_id,
        filename=filename,
        content=content,
        content_type=content_type,
        kind=kind,
        caption=caption,
    )


async def list_task_files(
    db: AsyncSession, *, lead_id: uuid.UUID, task_id: uuid.UUID, q: str | None
) -> list[Activity]:
    return await find_files_by_parent_task(
        db, lead_id=lead_id, task_id=task_id, q=q
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
            log.warning(
                "task_file.delete_storage_failed",
                extra={"activity_id": str(activity.id), "error": str(exc)[:200]},
            )
    await db.delete(activity)
