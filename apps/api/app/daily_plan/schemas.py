"""Internal dataclasses for the daily plan generator — not exposed as API schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.leads.models import Lead
from app.pipelines.models import Stage


@dataclass(frozen=True)
class ScoredItem:
    lead: Lead
    stage: Stage | None
    priority_score: Decimal
    estimated_minutes: int = 15
