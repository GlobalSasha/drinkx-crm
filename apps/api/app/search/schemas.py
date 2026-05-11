"""Pydantic DTO for global search hits."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SearchHit(BaseModel):
    type: Literal["company", "lead", "contact"]
    id: UUID
    title: str
    subtitle: str | None = None
    lead_id: UUID | None = None
    url: str
    rank: float | None = None


class SearchResponse(BaseModel):
    items: list[SearchHit]
    total: int
    query: str
    mode: Literal["ilike", "trgm", "empty"]
