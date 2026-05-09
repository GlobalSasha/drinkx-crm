"""Condition tree evaluator — Sprint 2.5 G1.

Evaluates a `condition_json` blob against a Lead. Shape:

    {"all": [
        {"field": "priority", "op": "eq", "value": "A"},
        {"field": "score",    "op": "gte", "value": 60}
    ]}

`all` = AND, `any` = OR. Empty / null condition → True (always fire).
Unknown fields / unknown ops → False with a structured log warning,
so a stale UI bundle that ships a removed field doesn't crash the
trigger fan-out — it just doesn't fire that automation.

Allowed fields are derived from a fixed allowlist rather than
reflecting on `Lead.__table__.c` — keeps the public surface stable
even if internal columns get renamed.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.leads.models import Lead

log = structlog.get_logger()


# Allowlisted fields the UI can target. Anything else evaluates False
# with a warning. Add fields here in lock-step with the frontend
# condition-builder dropdown.
ALLOWED_FIELDS = (
    "priority",      # str A/B/C/D
    "score",         # int 0-100
    "deal_type",     # str
    "stage_id",      # uuid
    "pipeline_id",   # uuid
    "source",        # str
    "assignment_status",  # str pool/assigned/transferred
)


def _resolve(lead: Lead, field: str) -> Any:
    if field not in ALLOWED_FIELDS:
        return _UNKNOWN
    return getattr(lead, field, _UNKNOWN)


# Sentinel — distinguishes «field doesn't exist» from «field is None».
_UNKNOWN = object()


def _check_op(op: str, lhs: Any, rhs: Any) -> bool:
    """Apply one comparison. Returns False on type errors so a
    misconfigured condition can't crash the hot path."""
    try:
        if op == "eq":
            return lhs == rhs
        if op == "neq":
            return lhs != rhs
        if op == "gte":
            return lhs is not None and float(lhs) >= float(rhs)
        if op == "lte":
            return lhs is not None and float(lhs) <= float(rhs)
        if op == "gt":
            return lhs is not None and float(lhs) > float(rhs)
        if op == "lt":
            return lhs is not None and float(lhs) < float(rhs)
        if op == "is_null":
            return lhs is None
        if op == "is_not_null":
            return lhs is not None
        if op == "in":
            return isinstance(rhs, (list, tuple)) and lhs in rhs
    except (TypeError, ValueError):
        return False
    return False


def evaluate(condition: dict | None, lead: Lead) -> bool:
    """Top-level dispatch. Empty / null → True. Unknown shape → False."""
    if condition is None or condition == {}:
        return True

    if "all" in condition:
        clauses = condition.get("all") or []
        return all(_evaluate_clause(c, lead) for c in clauses) if clauses else True
    if "any" in condition:
        clauses = condition.get("any") or []
        return any(_evaluate_clause(c, lead) for c in clauses)

    log.warning(
        "automation.condition.unknown_root",
        keys=list(condition.keys()),
    )
    return False


def _evaluate_clause(clause: Any, lead: Lead) -> bool:
    if not isinstance(clause, dict):
        return False
    field = clause.get("field")
    op = clause.get("op")
    value = clause.get("value")
    if not isinstance(field, str) or not isinstance(op, str):
        return False
    lhs = _resolve(lead, field)
    if lhs is _UNKNOWN:
        log.warning(
            "automation.condition.unknown_field", field=field
        )
        return False
    return _check_op(op, lhs, value)
