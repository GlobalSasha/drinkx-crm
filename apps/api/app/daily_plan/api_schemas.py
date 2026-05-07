"""Daily Plan REST DTOs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DailyPlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    daily_plan_id: UUID
    lead_id: UUID | None
    position: int
    priority_score: Decimal
    estimated_minutes: int
    time_block: str | None
    task_kind: str
    hint_one_liner: str
    done: bool
    done_at: datetime | None
    # Joined fields for rendering — populated by the service layer:
    lead_company_name: str | None = None
    lead_segment: str | None = None
    lead_city: str | None = None


class DailyPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    user_id: UUID
    plan_date: date
    generated_at: datetime | None
    status: str           # pending | generating | ready | failed
    generation_error: str | None
    summary_json: dict
    items: list[DailyPlanItemOut]
    created_at: datetime
    updated_at: datetime


class RegenerateOut(BaseModel):
    """Returned by POST /daily-plans/{date}/regenerate (202)."""
    plan_id: UUID | None
    status: str           # 'generating' (queued) or 'ready' (replaced existing inline if quick)
    task_id: str | None   # Celery task id when async
