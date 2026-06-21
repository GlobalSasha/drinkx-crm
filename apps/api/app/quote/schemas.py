"""Quote catalog + quote Pydantic schemas — Phase 1-2."""
from __future__ import annotations

from datetime import date, datetime
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


# --- Quote schemas (Phase 2) ---


class QuoteLineIn(BaseModel):
    product_id_ref: UUID | None = None
    product_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    quantity: float = 1
    unit_price: float = 0
    line_discount_pct: float = 0


class QuoteLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    position: int
    product_id_ref: UUID | None
    product_name: str
    description: str | None
    quantity: float
    unit_price: float
    line_discount_pct: float
    total: float


class QuoteCreate(BaseModel):
    recipient_contact_id: UUID | None = None
    valid_until: date | None = None
    vat_rate: float = 20
    discount: float = 0
    lines: list[QuoteLineIn] = Field(default_factory=list)


class QuoteUpdate(BaseModel):
    recipient_contact_id: UUID | None = None
    valid_until: date | None = None
    vat_rate: float | None = None
    discount: float | None = None
    lines: list[QuoteLineIn] | None = None


class QuoteStatusIn(BaseModel):
    status: str


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    lead_id: UUID
    number: str
    status: str
    recipient_contact_id: UUID | None
    valid_until: date | None
    vat_rate: float
    discount: float
    subtotal: float
    total: float
    sent_at: datetime | None
    accepted_at: datetime | None
    created_at: datetime
    lines: list[QuoteLineOut] = Field(default_factory=list)


class QuoteListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    status: str
    total: float
    valid_until: date | None
    created_at: datetime
