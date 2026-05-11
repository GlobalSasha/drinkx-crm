"""WhisperProvider — placeholder.

Reserved for on-prem self-hosted STT. The factory falls back here only
when `STT_PROVIDER=whisper`; until a wire is implemented the call
raises `SttError("whisper_not_implemented")` so the transcribe task
records a clear failure reason instead of silently swallowing audio.
"""
from __future__ import annotations

from app.inbox.stt.base import SttError


class WhisperProvider:
    provider_name = "whisper"

    async def transcribe(self, audio_bytes: bytes, language: str = "ru") -> str:
        raise SttError("whisper_not_implemented")
