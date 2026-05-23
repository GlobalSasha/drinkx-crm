"""File content extraction for the task-attachment search index.

Given the bytes of an uploaded file, produces a plain-text excerpt that
the database can ILIKE-match against. Four modes:
* PDF — pypdf.PdfReader, concatenate page text.
* Text-ish (.txt / .md / .csv / .rtf) — decode utf-8 with replace.
* Audio (.mp3 / .wav / .m4a / .ogg) — OpenAI Whisper transcription
  via httpx (no SDK dep). Requires OPENAI_API_KEY in settings; if
  the key isn't set, audio extraction is a noop.
* Anything else (image / xlsx / doc / docx) — return None; the
  search just won't match content for these formats in v1.

All functions are best-effort: any exception is caught + logged + an
empty/None result is returned. Search degrades gracefully; the upload
itself stays intact.
"""
from __future__ import annotations

import io
import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

# Cap extracted text at 100 KB per file. Anything beyond that is unlikely
# to be useful in an ILIKE-based search and would bloat payload_json.
MAX_EXTRACT_BYTES = 100 * 1024

# Whisper API rejects files > 25 MB. Matches our overall upload cap
# (MAX_FILE_BYTES = 25 * 1024 * 1024 in app.activity.files).
MAX_AUDIO_BYTES_FOR_WHISPER = 25 * 1024 * 1024
WHISPER_TIMEOUT_SECONDS = 120.0
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"

_TEXT_LIKE_KINDS = {"text"}
_PDF_KINDS = {"pdf"}
_AUDIO_KINDS = {"audio"}


def extract_content(*, file_kind: str | None, file_name: str, content: bytes) -> str | None:
    """Pick the right extractor based on file_kind. Returns the extracted text
    truncated to MAX_EXTRACT_BYTES, or None if the format isn't supported in v1."""
    if not content:
        return None

    try:
        if file_kind in _TEXT_LIKE_KINDS:
            return _truncate(_extract_text(content))
        if file_kind in _PDF_KINDS:
            return _truncate(_extract_pdf(content, filename=file_name))
        if file_kind in _AUDIO_KINDS:
            transcript = _extract_audio(content, filename=file_name)
            return _truncate(transcript) if transcript else None
        # Image, spreadsheet, document — not yet supported.
        log.info(
            "extraction.skipped",
            extra={"file_name": file_name, "file_kind": file_kind, "reason": "unsupported_kind"},
        )
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "extraction.failed",
            extra={"file_name": file_name, "file_kind": file_kind, "error": str(exc)[:200]},
        )
        return None


def _truncate(text: str) -> str:
    """Truncate to MAX_EXTRACT_BYTES (bytes, not chars) — preserves utf-8
    boundary by re-encoding."""
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_EXTRACT_BYTES:
        return text
    return encoded[:MAX_EXTRACT_BYTES].decode("utf-8", errors="ignore")


def _extract_text(content: bytes) -> str:
    """Decode utf-8 with byte-level replacement (the same strategy we use
    for staged .md files in base_update)."""
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes, *, filename: str) -> str:
    """Use pypdf to concatenate page text. Empty / scanned PDFs (no text
    layer) return an empty string — the search just won't match for them."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        log.info("extraction.skipped", extra={"file_name": filename, "reason": "encrypted_pdf"})
        return ""
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            # one bad page shouldn't kill the whole extraction
            continue
    return "\n".join(p.strip() for p in pages if p.strip())


def _extract_audio(content: bytes, *, filename: str) -> str:
    """POST the audio file to OpenAI Whisper for transcription.

    Uses httpx directly (no SDK dep). Returns an empty string when the
    API key isn't configured (graceful degradation in dev environments).
    Any non-2xx response or network error is caught by the outer try
    in extract_content() and turns into None.
    """
    if len(content) > MAX_AUDIO_BYTES_FOR_WHISPER:
        log.info(
            "extraction.skipped",
            extra={"file_name": filename, "reason": "audio_too_large", "bytes": len(content)},
        )
        return ""

    api_key = get_settings().openai_api_key
    if not api_key:
        log.info(
            "extraction.skipped",
            extra={"file_name": filename, "reason": "openai_api_key_unset"},
        )
        return ""

    # Whisper expects multipart/form-data with the file + model. The browser
    # sets the boundary itself in our frontend uploads; here we hand-roll
    # it via httpx's files= argument.
    response = httpx.post(
        WHISPER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (filename, content)},
        data={"model": WHISPER_MODEL, "response_format": "text"},
        timeout=WHISPER_TIMEOUT_SECONDS,
    )
    if response.status_code // 100 != 2:
        log.warning(
            "extraction.whisper_failed",
            extra={
                "file_name": filename,
                "status": response.status_code,
                "body": response.text[:200],
            },
        )
        return ""

    # With response_format=text, Whisper returns plain text directly (not JSON).
    return (response.text or "").strip()
