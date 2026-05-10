"""Lead AI Agent runner — Sprint 3.1 Phase C.

Two entry points:
  - `get_suggestion(lead, ...)` — fires LLM via TaskType.prefilter (Flash)
    and returns a typed `AgentSuggestion`. Returns `None` on any
    failure (timeout, parse error, all providers down) so the caller
    can render a silent banner instead of crashing.
  - `chat(lead, message, history, ...)` — fires LLM via TaskType.sales_coach
    (Pro) and returns a `ChatResponse` with the appended turn. On
    failure returns a graceful Russian fallback string — the chat
    must never crash the LeadCard.

Both helpers reuse `app.enrichment.providers.factory.complete_with_fallback`
verbatim — no new abstraction layer (per the «do NOT add a new
TaskType if existing values cover the use case» constraint).
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from app.enrichment.providers.base import LLMError, TaskType
from app.enrichment.providers.factory import complete_with_fallback

from app.lead_agent.context import build_lead_context, load_product_foundation
from app.lead_agent.prompts import (
    CHAT_SYSTEM,
    FOUNDATION_INJECT_CHARS,
    SUGGESTION_SYSTEM,
)
from app.lead_agent.schemas import AgentSuggestion, ChatMessage, ChatResponse

log = structlog.get_logger()

# Trim user-supplied chat history to this many messages before
# building the prompt. 6 = 3 manager / Чак pairs — enough context
# for follow-up clarifications, small enough to keep token cost
# predictable on MiMo Pro.
HISTORY_TURNS_FOR_PROMPT = 6

# Persisted history cap (returned to client). Larger than the
# prompt window so the UI can scroll back without losing turns
# before they fall off the wire.
HISTORY_TURNS_PERSISTED = 20


def _strip_code_fence(raw: str) -> str:
    """Remove ```json / ``` fences if the model wrapped its answer.
    Mirrors the trick in `app.enrichment.orchestrator._parse_research_output`."""
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return s


async def get_suggestion(
    lead: Any,
    *,
    stage_name: str | None = None,
) -> AgentSuggestion | None:
    """Background banner — short JSON recommendation. Flash model.

    Soft fallback contract: any exception (LLM down, JSON parse
    error, schema validation) → returns `None`. The caller
    (`tasks.refresh_suggestion_async` or the `/refresh` route) is
    expected to handle `None` by either keeping the previous
    suggestion or clearing the agent_state slot — we don't make
    that decision here.
    """
    foundation = load_product_foundation()[:FOUNDATION_INJECT_CHARS]
    system = SUGGESTION_SYSTEM.format(product_foundation=foundation)
    user = (
        "Карточка лида:\n"
        f"{build_lead_context(lead, stage_name=stage_name)}\n\n"
        "Дай одну рекомендацию по этой карточке. Только JSON по схеме."
    )

    try:
        completion = await complete_with_fallback(
            system=system,
            user=user,
            task_type=TaskType.prefilter,
            max_tokens=400,
            temperature=0.3,
        )
    except LLMError as exc:
        log.warning(
            "lead_agent.suggestion.llm_failed",
            lead_id=str(getattr(lead, "id", "")),
            provider=getattr(exc, "provider", ""),
            reason=str(exc)[:200],
        )
        return None

    raw = _strip_code_fence(completion.text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(
            "lead_agent.suggestion.parse_failed",
            lead_id=str(getattr(lead, "id", "")),
            raw_preview=raw[:200],
        )
        return None

    if not isinstance(data, dict):
        log.warning(
            "lead_agent.suggestion.wrong_shape",
            lead_id=str(getattr(lead, "id", "")),
            got=type(data).__name__,
        )
        return None

    try:
        suggestion = AgentSuggestion(**data)
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError + odd shapes
        log.warning(
            "lead_agent.suggestion.validation_failed",
            lead_id=str(getattr(lead, "id", "")),
            reason=str(exc)[:200],
        )
        return None

    # Force the «no confident action» rule: if confidence < 0.4 and the
    # model still attached an action_label, drop the label. Keeps the
    # UI from prompting the manager to commit on shaky ground.
    if suggestion.confidence < 0.4 and suggestion.action_label:
        suggestion = suggestion.model_copy(update={"action_label": None})

    return suggestion


async def chat(
    lead: Any,
    message: str,
    history: list[ChatMessage] | None = None,
    *,
    stage_name: str | None = None,
) -> ChatResponse:
    """Sales Coach chat — long-form RU answer. Pro model.

    Hard fallback: on `LLMError` we return a polite Russian
    «попробуй через минуту» reply rather than raising. The router
    surfaces that as a 200 to the frontend so the chat drawer
    doesn't break — operators see the same behaviour as a slow
    network blip.
    """
    history = history or []
    foundation = load_product_foundation()[:FOUNDATION_INJECT_CHARS]
    system = CHAT_SYSTEM.format(
        product_foundation=foundation,
        lead_context=build_lead_context(lead, stage_name=stage_name),
    )

    recent = history[-HISTORY_TURNS_FOR_PROMPT:]
    history_block = "\n".join(
        f"{'Менеджер' if m.role == 'user' else 'Чак'}: {m.content}"
        for m in recent
    )
    if history_block:
        user = f"{history_block}\nМенеджер: {message}\nЧак:"
    else:
        user = f"Менеджер: {message}\nЧак:"

    try:
        completion = await complete_with_fallback(
            system=system,
            user=user,
            task_type=TaskType.sales_coach,
            max_tokens=1200,
            temperature=0.7,
        )
        reply = completion.text.strip()
    except LLMError as exc:
        log.warning(
            "lead_agent.chat.llm_failed",
            lead_id=str(getattr(lead, "id", "")),
            provider=getattr(exc, "provider", ""),
            reason=str(exc)[:200],
        )
        reply = "Сейчас не могу ответить — попробуй через минуту."

    updated = (
        history
        + [
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=reply),
        ]
    )
    return ChatResponse(
        reply=reply,
        updated_history=updated[-HISTORY_TURNS_PERSISTED:],
    )
