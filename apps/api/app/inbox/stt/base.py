"""SttProvider Protocol — ADR-024.

Mirrors the LLM provider abstraction (app.enrichment.providers.base):
a thin Protocol so the call-transcription pipeline does not care
which vendor is wired up — switching is one env var.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class SttError(Exception):
    """Stable error code surfaced from a provider — e.g.
    `salute_http_401`, `salute_auth_failed`, `salute_empty_result`.
    Safe to log without leaking credentials."""


@runtime_checkable
class SttProvider(Protocol):
    """Speech-to-text provider — Russian-first."""

    provider_name: str

    async def transcribe(self, audio_bytes: bytes, language: str = "ru") -> str:
        """Returns the recognized text. Raises `SttError` on auth or
        transport failures; returns "" if the audio is silent or the
        provider explicitly returned an empty result."""
        ...
