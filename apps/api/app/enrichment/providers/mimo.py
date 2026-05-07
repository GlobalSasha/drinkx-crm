"""Xiaomi MiMo provider — OpenAI-compatible /chat/completions."""
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
    is_flash_task,
)

log = structlog.get_logger()


class MiMoProvider:
    name = "mimo"

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
        if not s.mimo_api_key:
            raise LLMAuthError("MIMO_API_KEY not set", provider=self.name, status=None)

        model = s.mimo_model_flash if is_flash_task(task_type) else s.mimo_model_pro
        url = f"{s.mimo_base_url.rstrip('/')}/chat/completions"

        # MiMo strictly validates known fields (returns 400 on
        # 'reasoning_effort' / 'thinking' which we tried earlier as
        # defensive hints). Strip to OpenAI-spec basics; the synthesis
        # prompt itself enforces "single JSON, no markdown, no preamble".
        payload: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        # MiMo uses 'api-key:' header, NOT 'Authorization: Bearer'
        headers = {"api-key": s.mimo_api_key, "Content-Type": "application/json"}

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
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("empty choices", provider=self.name)
        text = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        # Rough pricing (placeholder until MiMo publishes real rates)
        cost_per_1k_in = 0.0005 if is_flash_task(task_type) else 0.0015
        cost_per_1k_out = 0.0005 if is_flash_task(task_type) else 0.0015
        cost_usd = (
            (prompt_tokens / 1000) * cost_per_1k_in
            + (completion_tokens / 1000) * cost_per_1k_out
        )

        return CompletionResult(
            text=text,
            model=model,
            provider=self.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
