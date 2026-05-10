"""Lead AI Agent Pydantic schemas — Sprint 3.1 Phase C.

`AgentSuggestion` is what the runner returns and what the
`agent_state.suggestion` JSON in `leads.agent_state` carries. The DB
column is opaque JSONB — these schemas are the only contract.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentSuggestion(BaseModel):
    """Background-mode banner content. Stored in `lead.agent_state['suggestion']`
    as a plain dict; `runner.get_suggestion` returns this typed shape."""
    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="1-2 sentence recommendation, RU")
    action_label: str | None = Field(
        default=None,
        description='Optional primary CTA, e.g. "Позвонить", "Отправить КП", "Напомнить".',
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="0.0–1.0. <0.4 → UI may dim the banner; runner clears action_label below 0.4.",
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Frontend POSTs the manager's message + recent in-memory history.

    History is bounded by the runner (last ~6 turns) before being fed
    into the prompt; we accept whatever the client sends and trim
    server-side to keep token cost predictable.
    """
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    updated_history: list[ChatMessage]


class SuggestionResponse(BaseModel):
    """GET /agent/suggestion returns the cached-on-row suggestion
    (no LLM call). `null` when nothing has been computed yet."""
    suggestion: AgentSuggestion | None = None
