"""Quote catalog Pydantic schemas — Phase 1."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    unit_price: float
    is_active: bool


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = "other"
    unit_price: float = 0


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    category: str | None = None
    unit_price: float | None = None
    is_active: bool | None = None
