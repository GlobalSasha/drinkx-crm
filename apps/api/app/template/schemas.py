"""Message Templates Pydantic schemas — Sprint 2.4 G4."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirror models.VALID_CHANNELS. Pydantic Literal validates at the API
# boundary so the service never sees a stray string.
TemplateChannel = Literal["email", "tg", "sms"]


class MessageTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    channel: TemplateChannel
    category: str | None = None
    text: str
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class MessageTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    channel: TemplateChannel
    category: str | None = Field(None, max_length=100)
    text: str = Field(..., min_length=1)


class MessageTemplateUpdate(BaseModel):
    """PATCH body. All fields optional — UI sends only the field it's
    changing. Channel is mutable in v1; the unique-constraint guard in
    the service catches the case where a rename collides with an
    existing (workspace, name, channel) row."""
    name: str | None = Field(None, min_length=1, max_length=255)
    channel: TemplateChannel | None = None
    category: str | None = Field(None, max_length=100)
    text: str | None = Field(None, min_length=1)
