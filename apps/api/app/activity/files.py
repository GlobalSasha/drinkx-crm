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
    # Optional cross-check via mimetypes (tiebreaker)
    guessed, _ = mimetypes.guess_type(name)
    content_type = guessed if guessed else default_ct
    _ = content_head  # reserved for future magic-byte sniffing
    return kind, content_type
