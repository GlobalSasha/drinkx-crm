"""Anthropic Claude provider — Messages API."""
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


class AnthropicProvider:
    name = "anthropic"

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
        if not s.anthropic_api_key:
            raise LLMAuthError("ANTHROPIC_API_KEY not set", provider=self.name, status=None)

        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": s.anthropic_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": s.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
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
        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = data.get("usage", {})
        in_tokens = int(usage.get("input_tokens", 0))
        out_tokens = int(usage.get("output_tokens", 0))
        cost_usd = (in_tokens / 1_000_000) * 3.0 + (out_tokens / 1_000_000) * 15.0  # claude-sonnet-4-5 approx

        return CompletionResult(
            text=text,
            model=s.anthropic_model,
            provider=self.name,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            cost_usd=cost_usd,
        )
