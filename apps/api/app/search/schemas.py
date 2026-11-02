"""Pydantic DTO for global search hits."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SearchHit(BaseModel):
    type: Literal["company", "lead", "contact", "file"]
    id: UUID
    title: str
    subtitle: str | None = None
    lead_id: UUID | None = None
    url: str
    rank: float | None = None


class TakenLeadHit(BaseModel):
    """Someone else's lead matching the query — shown to a manager so they
    don't create a duplicate. Deliberately without a link or contacts."""
    id: UUID
    title: str
    owner_name: str | None = None
    stage_name: str | None = None


class SearchResponse(BaseModel):
    items: list[SearchHit]
    taken: list[TakenLeadHit] = []
    total: int
    query: str
    mode: Literal["ilike", "trgm", "empty"]
