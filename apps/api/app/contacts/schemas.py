"""Pydantic schemas for Contact endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContactBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    title: str | None = None
    role_type: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram_url: str | None = None
    linkedin_url: str | None = None
    source: str | None = None
    confidence: str = "medium"
    verified_status: str = "to_verify"
    notes: str | None = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str | None = None
    title: str | None = None
    role_type: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram_url: str | None = None
    linkedin_url: str | None = None
    source: str | None = None
    confidence: str | None = None
    verified_status: str | None = None
    notes: str | None = None


class ContactOut(ContactBase):
    id: UUID
    lead_id: UUID
    created_at: datetime
    updated_at: datetime
