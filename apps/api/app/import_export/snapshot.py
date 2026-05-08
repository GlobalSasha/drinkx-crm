"""Lead snapshot generator for the AI bulk-update loop (PRD §6.14).

Produces a YAML payload the manager hands to an external LLM. Includes
only the fields a model needs to reason about the lead — no DB ids,
timestamps, or workspace bookkeeping.

Synchronous (not Celery): the snapshot is small (≤ 500 leads × ~500
bytes ≈ 250 KB) and the manager hits "download" expecting an immediate
response. No ExportJob row is created.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.contacts.models import Contact
from app.leads.models import Lead
from app.pipelines.models import Stage


# Contacts must clear BOTH gates to make it into the snapshot:
#   - verified_status not invalid
#   - confidence not low (matches the spec wording "skip confidence < 0.3"
#     against our enum-string Contact.confidence which is low/medium/high)
_LOW_QUALITY_CONFIDENCE = {"low", "0", "0.0", "0.1", "0.2"}


def _to_yaml_safe(value: Any) -> Any:
    """Coerce values PyYAML can't serialise on its own.
    Decimal → float; UUID → str; everything else passes through."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _contact_passes(contact: Contact) -> bool:
    """True if the contact should land in the snapshot."""
    verified = (getattr(contact, "verified_status", "") or "").lower()
    confidence = (getattr(contact, "confidence", "") or "").lower()
    if verified == "invalid":
        return False
    if confidence in _LOW_QUALITY_CONFIDENCE:
        return False
    return True


def _format_contact(contact: Contact) -> dict[str, Any]:
    return {
        "name": getattr(contact, "name", "") or "",
        "title": getattr(contact, "title", "") or "",
        "email": getattr(contact, "email", "") or "",
        "phone": getattr(contact, "phone", "") or "",
        "role_type": getattr(contact, "role_type", "") or "",
    }


def _format_ai_brief(ai_data: Any) -> dict[str, Any]:
    """Pull the subset of the AI Brief that's actually useful to an
    external LLM — drop anything we computed for our own UI (`urgency`,
    `confidence`, `sources_used`, `score_rationale`)."""
    if not isinstance(ai_data, dict):
        return {}
    return {
        "company_profile": ai_data.get("company_profile") or "",
        "growth_signals": list(ai_data.get("growth_signals") or []),
        "risk_signals": list(ai_data.get("risk_signals") or []),
        "next_steps": list(ai_data.get("next_steps") or []),
    }


def _format_lead(
    lead: Lead, *, stage_name: str, include_ai_brief: bool
) -> dict[str, Any]:
    contacts = [
        _format_contact(c) for c in (lead.contacts or []) if _contact_passes(c)
    ]
    payload: dict[str, Any] = {
        "id": str(lead.id),
        "company_name": getattr(lead, "company_name", "") or "",
        "inn": getattr(lead, "inn", "") or "",
        "segment": getattr(lead, "segment", "") or "",
        "city": getattr(lead, "city", "") or "",
        "stage": stage_name or "",
        "priority": getattr(lead, "priority", "") or "",
        "fit_score": _to_yaml_safe(getattr(lead, "fit_score", None)),
        "tags": list(getattr(lead, "tags_json", None) or []),
    }
    if include_ai_brief:
        brief = _format_ai_brief(getattr(lead, "ai_data", None))
        if brief.get("company_profile") or any(
            brief.get(k) for k in ("growth_signals", "risk_signals", "next_steps")
        ):
            payload["ai_brief"] = brief
    payload["contacts"] = contacts
    return payload


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    filters: dict | None = None,
    include_ai_brief: bool = True,
    limit: int = 500,
) -> bytes:
    """Build the YAML snapshot. Returns UTF-8 bytes ready for the
    StreamingResponse / Content-Disposition: attachment download."""
    filters = filters or {}

    stmt = (
        select(Lead)
        .where(Lead.workspace_id == workspace_id)
        .options(selectinload(Lead.contacts))
    )
    # Mirror the GET /api/leads filter shape (subset).
    if filters.get("stage_id"):
        stmt = stmt.where(Lead.stage_id == filters["stage_id"])
    if filters.get("segment"):
        stmt = stmt.where(Lead.segment == filters["segment"])
    if filters.get("city"):
        stmt = stmt.where(Lead.city == filters["city"])
    if filters.get("priority"):
        stmt = stmt.where(Lead.priority == filters["priority"])
    if filters.get("deal_type"):
        stmt = stmt.where(Lead.deal_type == filters["deal_type"])
    if filters.get("assigned_to"):
        stmt = stmt.where(Lead.assigned_to == filters["assigned_to"])
    if filters.get("assignment_status"):
        stmt = stmt.where(Lead.assignment_status == filters["assignment_status"])
    if filters.get("fit_min") is not None:
        try:
            stmt = stmt.where(Lead.fit_score >= float(filters["fit_min"]))
        except (TypeError, ValueError):
            pass
    if filters.get("q"):
        stmt = stmt.where(Lead.company_name.ilike(f"%{filters['q']}%"))

    stmt = stmt.order_by(Lead.created_at.desc()).limit(limit)
    res = await session.execute(stmt)
    leads = list(res.scalars().unique())

    # Resolve stage names in one extra query — same trick as the export task.
    stage_ids = {l.stage_id for l in leads if l.stage_id}
    stage_lookup: dict[Any, str] = {}
    if stage_ids:
        s_res = await session.execute(
            select(Stage.id, Stage.name).where(Stage.id.in_(stage_ids))
        )
        stage_lookup = {sid: name for sid, name in s_res.all()}

    payload = {
        "leads": [
            _format_lead(
                l,
                stage_name=stage_lookup.get(l.stage_id, "") or "",
                include_ai_brief=include_ai_brief,
            )
            for l in leads
        ],
    }

    # default_flow_style=False → block-style YAML (human-readable for the
    # external LLM). sort_keys=False → preserve our key order (id first,
    # ai_brief before contacts, etc.).
    text = yaml.safe_dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return text.encode("utf-8")


__all__ = ["generate_snapshot"]
