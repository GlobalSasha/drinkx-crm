"""Groq provider — OpenAI-compatible /chat/completions.

Free tier, very fast first-token, reachable from RU IPs. Sits in the
fallback chain after MiMo so we still get a result when MiMo times out.
Same shape as DeepSeekProvider — the wire format is identical.
"""
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

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    name = "groq"

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
        if not s.groq_api_key:
            raise LLMAuthError("GROQ_API_KEY not set", provider=self.name, status=None)

        model = s.groq_model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {s.groq_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            try:
                resp = await client.post(_GROQ_URL, json=payload, headers=headers)
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
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("empty choices", provider=self.name)
        text = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        in_tokens = int(usage.get("prompt_tokens", 0))
        out_tokens = int(usage.get("completion_tokens", 0))
        # Groq currently free at the published tier — track 0 cost for now.
        # Update if Groq introduces paid pricing on Llama 70B.
        cost_usd = 0.0

        return CompletionResult(
            text=text,
            model=model,
            provider=self.name,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            cost_usd=cost_usd,
        )
