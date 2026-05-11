"""STT provider factory — switch via `STT_PROVIDER` env.

Default is `salute` (Sber SaluteSpeech). Unknown values fall back to
salute and log a warning — the transcribe task should never silently
choose a different provider than the operator expected.
"""
from __future__ import annotations

import structlog

from app.config import get_settings
from app.inbox.stt.base import SttProvider
from app.inbox.stt.salute import SaluteSpeechProvider
from app.inbox.stt.whisper import WhisperProvider

log = structlog.get_logger()


def get_stt_provider() -> SttProvider:
    s = get_settings()
    name = (s.stt_provider or "salute").lower()
    if name == "salute":
        return SaluteSpeechProvider()
    if name == "whisper":
        return WhisperProvider()
    log.warning("stt.factory.unknown_provider", value=name)
    return SaluteSpeechProvider()
