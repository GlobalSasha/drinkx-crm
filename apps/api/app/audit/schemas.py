"""Audit log API schemas — Sprint 1.5."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    user_id: UUID | None
    # Sprint 2.4 G5: joined from `users` table for the «Пользователь»
    # column. Both NULL when the audit row's `user_id` is NULL
    # (system-triggered) or the user has been deleted since — frontend
    # falls back to the first 8 chars of the raw user_id.
    user_full_name: str | None = None
    user_email: str | None = None
    action: str
    entity_type: str
    entity_id: UUID | None
    delta_json: dict[str, Any] | None
    created_at: datetime


class AuditLogPageOut(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
