"""Google Gemini provider — generativelanguage REST API."""
from __future__ import annotations

import httpx
import structlog

from app.config import get_settings
from app.enrichment.providers.base import (
    CompletionResult,
    LLMAuthError,
    LLMError,
    LLMRateLimited,
    LLMServerError,
    TaskType,
)

log = structlog.get_logger()

_GEMINI_BASE = "https://generativelanguage.googleapis.com"


class GeminiProvider:
    name = "gemini"

    async def complete(
        self,
        *,
        system: str,
        user: str,
        task_type: TaskType,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        timeout_seconds: float = 30.0,
    ) -> CompletionResult:
        s = get_settings()
        if not s.gemini_api_key:
            raise LLMAuthError("GEMINI_API_KEY not set", provider=self.name, status=None)

        model = s.gemini_model
        url = f"{_GEMINI_BASE}/v1beta/models/{model}:generateContent"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system}\n\n{user}"}],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    params={"key": s.gemini_api_key},
                    headers={"Content-Type": "application/json"},
                )
            except httpx.TimeoutException as e:
                raise LLMServerError(f"timeout: {e}", provider=self.name)
            except httpx.HTTPError as e:
                raise LLMServerError(f"http error: {e}", provider=self.name)

        if resp.status_code == 429:
            raise LLMRateLimited(resp.text[:200], provider=self.name, status=429)
        if resp.status_code in (401, 403):
            raise LLMAuthError(resp.text[:200], provider=self.name, status=resp.status_code)
        if resp.status_code >= 500:
            raise LLMServerError(resp.text[:200], provider=self.name, status=resp.status_code)
        if not resp.is_success:
            raise LLMError(
                f"{resp.status_code}: {resp.text[:200]}", provider=self.name, status=resp.status_code
            )

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMError("empty candidates", provider=self.name)
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)

        usage = data.get("usageMetadata", {})
        in_tokens = int(usage.get("promptTokenCount", 0))
        out_tokens = int(usage.get("candidatesTokenCount", 0))
        # Gemini 2.0 flash approx pricing: $0.075/MTok in, $0.30/MTok out
        cost_usd = (in_tokens / 1_000_000) * 0.075 + (out_tokens / 1_000_000) * 0.30

        return CompletionResult(
            text=text,
            model=model,
            provider=self.name,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            cost_usd=cost_usd,
        )
