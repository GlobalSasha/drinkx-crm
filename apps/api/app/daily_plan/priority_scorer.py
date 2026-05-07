"""Pure-function priority scoring for the daily plan generator.

Inputs are read off ORM Lead + Stage objects. Output is a single Decimal.
Higher = the manager should call this lead first.

Weights are MODULE-LEVEL CONSTANTS so they're trivial to tune later
(no DB roundtrip, no admin UI yet — Sprint 1.5+).

Formula:
  base       = stage.probability                         (0..100)
  + 25  if   next_action_at is overdue (now > next_action_at)
  + 15  if   next_action_at is within next 24h
  + 10  if   priority == 'A'
  +  5  if   priority == 'B'
  +  3  if   priority == 'C'
  + 20  if   is_rotting_stage OR is_rotting_next_step
  + (fit_score or 0)                                     (0..10)
  - 50  if   archived_at OR won_at OR lost_at is set
  - 100 if   assignment_status != 'assigned'
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.leads.models import Lead
from app.pipelines.models import Stage


# --- tunable weights ---
W_OVERDUE = Decimal("25")
W_DUE_SOON = Decimal("15")
W_PRIORITY_A = Decimal("10")
W_PRIORITY_B = Decimal("5")
W_PRIORITY_C = Decimal("3")
W_ROTTING = Decimal("20")
W_FIT_MULTIPLIER = Decimal("1")        # multiply fit_score (0..10) by this
P_ARCHIVED_OR_TERMINAL = Decimal("-50")
P_NOT_ASSIGNED = Decimal("-100")

DUE_SOON_WINDOW = timedelta(hours=24)


def score_lead(lead: Lead, stage: Stage | None, now: datetime) -> Decimal:
    """Return priority score for one lead. Higher = call first.

    `stage` may be None (e.g. lead with NULL stage_id); we treat that as 0
    base probability.
    """
    score = Decimal(stage.probability) if stage is not None else Decimal(0)

    # Time pressure
    if lead.next_action_at is not None:
        if lead.next_action_at < now:
            score += W_OVERDUE
        elif lead.next_action_at <= now + DUE_SOON_WINDOW:
            score += W_DUE_SOON

    # Strategic priority (A/B/C/D — D contributes 0)
    if lead.priority == "A":
        score += W_PRIORITY_A
    elif lead.priority == "B":
        score += W_PRIORITY_B
    elif lead.priority == "C":
        score += W_PRIORITY_C

    # Rotting (either kind triggers; weight applied once)
    if lead.is_rotting_stage or lead.is_rotting_next_step:
        score += W_ROTTING

    # AI fit-score nudge — fit_score column is Numeric, may be None
    if lead.fit_score is not None:
        score += Decimal(str(lead.fit_score)) * W_FIT_MULTIPLIER

    # Penalties
    if (
        lead.archived_at is not None
        or lead.won_at is not None
        or lead.lost_at is not None
    ):
        score += P_ARCHIVED_OR_TERMINAL

    if lead.assignment_status != "assigned":
        score += P_NOT_ASSIGNED

    return score
