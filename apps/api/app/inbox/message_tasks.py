"""Async cores for inbox-side Celery tasks — Sprint 3.4.

G4 ships `transcribe_call_async` as a thin stub: it just records that
a transcription was dispatched for a given InboxMessage. The real
SaluteSpeech / MiMo pipeline lands in G4b and replaces the body of
this function without touching the dispatch wiring.
"""
from __future__ import annotations

from uuid import UUID

import structlog

log = structlog.get_logger()


async def transcribe_call_async(message_id: UUID) -> dict:
    """G4 placeholder. G4b will:
      1. Download `inbox_messages.media_url` from Mango.
      2. Run STT via the configured `SttProvider` (salute / yandex / whisper).
      3. Summarize the transcript with MiMo Flash (`task_type=prefilter`).
      4. Update `inbox_messages.transcript / .summary / .stt_provider`.
      5. Refresh the lead-agent suggestion 60s later if matched.
    """
    log.info("inbox.transcribe.queued_stub", message_id=str(message_id))
    return {"job": "transcribe_call", "status": "stub", "message_id": str(message_id)}
