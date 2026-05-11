"""SaluteSpeech provider — Sber STT.

OAuth2 token caching is in-memory per process. The token TTL is 30
minutes; we refresh ~2 minutes before expiry (1700s window) so
overlapping refreshes never compete on a single Celery worker.

Sber's STT endpoint accepts raw audio bytes in the body with the
`Content-Type` set to the codec. Mango recordings come down as MP3
(`audio/mpeg`); future formats (e.g. ogg/opus) are a one-line change.

Docs (pinned at time of writing):
  https://developers.sber.ru/docs/ru/salutespeech/recognition/rest/recognition-guide
"""
from __future__ import annotations

import base64
import time
import uuid

import httpx
import structlog

from app.config import get_settings
from app.inbox.stt.base import SttError

log = structlog.get_logger()


_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_STT_URL = "https://smartspeech.sber.ru/rest/v1/speech:recognize"


class SaluteSpeechProvider:
    provider_name = "salute"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
    ) -> None:
        s = get_settings()
        self.client_id = client_id if client_id is not None else s.salute_client_id
        self.client_secret = (
            client_secret if client_secret is not None else s.salute_client_secret
        )
        self.scope = scope or s.salute_scope
        self._token: str | None = None
        self._token_expires: float = 0.0

    # ------------------------------------------------------------------
    # OAuth2 token
    # ------------------------------------------------------------------

    def _basic_auth(self) -> str:
        creds = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        return base64.b64encode(creds).decode("ascii")

    async def _fetch_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise SttError("salute_not_configured")

        headers = {
            "Authorization": f"Basic {self._basic_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": str(uuid.uuid4()),
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
                resp = await client.post(
                    _OAUTH_URL,
                    headers=headers,
                    data={"scope": self.scope},
                )
        except httpx.HTTPError as exc:
            raise SttError("salute_oauth_http_error") from exc

        if resp.status_code != 200:
            log.warning(
                "stt.salute.oauth_bad_status",
                status=resp.status_code,
                body=resp.text[:200],
            )
            raise SttError(f"salute_oauth_status_{resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise SttError("salute_oauth_bad_json") from exc

        token = payload.get("access_token")
        if not token:
            raise SttError("salute_oauth_no_token")

        # Sber's TTL is 30 minutes; cache for 28 to leave headroom.
        self._token = token
        self._token_expires = time.time() + 1700
        return token

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token
        return await self._fetch_token()

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    async def transcribe(self, audio_bytes: bytes, language: str = "ru") -> str:
        if not audio_bytes:
            return ""

        token = await self._get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "audio/mpeg",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0, verify=True) as client:
                resp = await client.post(
                    _STT_URL,
                    headers=headers,
                    content=audio_bytes,
                    params={"language": language},
                )
        except httpx.HTTPError as exc:
            raise SttError("salute_stt_http_error") from exc

        if resp.status_code != 200:
            log.warning(
                "stt.salute.recognize_bad_status",
                status=resp.status_code,
                body=resp.text[:200],
            )
            raise SttError(f"salute_status_{resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise SttError("salute_bad_json") from exc

        # Sber returns `{ "result": [ {"normalized_text": "..."} ] }`.
        # Be defensive — recognizers occasionally omit fields on silence.
        result = data.get("result") or []
        if not result:
            return ""
        first = result[0] if isinstance(result, list) else result
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return (
                first.get("normalized_text")
                or first.get("text")
                or ""
            )
        return ""
