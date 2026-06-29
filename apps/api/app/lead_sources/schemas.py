"""Pydantic schemas for the lead-source dictionary."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class LeadSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    is_paid: bool
    is_system: bool
    sort_order: int


class LeadSourceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_paid: bool = False
    sort_order: int = 0


class LeadSourceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    is_paid: bool | None = None
    sort_order: int | None = None
