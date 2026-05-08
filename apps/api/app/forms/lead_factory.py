"""Convert a public form submission into a Lead + optional Activity.

The form's `fields_json` is just configuration — what actually arrives
in the submission is whatever the manager wired into the embed. We map
common keys (RU + EN) to canonical Lead fields; everything else stays
in `FormSubmission.raw_payload` for forensic reference.

ADR-007 compliance: the form *captures* a lead but never assigns it
to a manager, never advances stage, never triggers AI auto-actions.
The new lead lands in pool — manager picks it up via the existing
claim-from-pool flow.
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.forms.models import WebForm
from app.leads.models import Lead

log = structlog.get_logger()


# Lowercase form-key → canonical Lead field. Lookup is case-insensitive
# and normalises whitespace + underscores → hyphens so "Company Name",
# "company_name", "company-name" all hit `company_name`.
FORM_FIELD_TO_LEAD: dict[str, str] = {
    # Company name
    "company_name":  "company_name",
    "company name":  "company_name",
    "company":       "company_name",
    "название":      "company_name",
    "название компании": "company_name",
    "наименование":  "company_name",
    "name":          "company_name",
    # Email
    "email":         "email",
    "e-mail":        "email",
    "почта":         "email",
    # Phone
    "phone":         "phone",
    "телефон":       "phone",
    "тел":           "phone",
    "mobile":        "phone",
    # Website
    "website":       "website",
    "сайт":          "website",
    "url":           "website",
    # City
    "city":          "city",
    "город":         "city",
    # INN
    "inn":           "inn",
    "инн":           "inn",
    # Notes — surfaced as a comment Activity, not a Lead column
    "comment":       "notes",
    "comments":      "notes",
    "message":       "notes",
    "комментарий":   "notes",
    "сообщение":     "notes",
    "вопрос":        "notes",
}


def _normalize_key(k: str) -> str:
    return (k or "").strip().lower().replace("_", " ").replace("-", " ").strip()


def _project_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Walk the raw payload, return {canonical_field: stringified_value}.
    Only collects values for known canonical fields; everything else
    survives in raw_payload on FormSubmission for the manager to inspect."""
    out: dict[str, str] = {}
    if not isinstance(payload, dict):
        return out
    for raw_key, raw_val in payload.items():
        if raw_val is None or raw_val == "":
            continue
        norm = _normalize_key(str(raw_key))
        # Try direct lookup (with both space-normalised and original key)
        target = FORM_FIELD_TO_LEAD.get(norm) or FORM_FIELD_TO_LEAD.get(
            norm.replace(" ", "_")
        )
        if not target:
            continue
        # Don't overwrite an earlier-seen value for the same target
        if target in out:
            continue
        if isinstance(raw_val, (list, tuple)):
            raw_val = ", ".join(str(v) for v in raw_val if v)
        out[target] = str(raw_val).strip()
    return out


async def create_lead_from_submission(
    session: AsyncSession,
    *,
    form: WebForm,
    payload: dict[str, Any],
    source_domain: str | None,
) -> Lead:
    """Build the Lead + optional comment Activity in the caller's session.
    Caller commits."""
    from app.pipelines import repositories as pipelines_repo

    projected = _project_payload(payload)

    # Company name fallback chain: explicit field → source domain →
    # form-name suffix. Never empty, never None.
    company = projected.pop("company_name", "") or (source_domain or "").strip()
    if not company:
        company = f"Заявка с формы {form.name}"
    company = company[:255]

    notes = projected.pop("notes", None)

    # Resolve target placement: form's explicit target wins, else
    # workspace default first stage.
    pipeline_id = form.target_pipeline_id
    stage_id = form.target_stage_id
    if pipeline_id is None or stage_id is None:
        first = await pipelines_repo.get_default_first_stage(
            session, form.workspace_id
        )
        if first is not None:
            fallback_pipeline, fallback_stage = first
            pipeline_id = pipeline_id or fallback_pipeline
            stage_id = stage_id or fallback_stage

    lead_kwargs: dict[str, Any] = {
        "workspace_id": form.workspace_id,
        "pipeline_id": pipeline_id,
        "stage_id": stage_id,
        "company_name": company,
        "assignment_status": "pool",
        "tags_json": [],
        # Source surfaces in the lead-card chip strip — manager sees
        # which form delivered the lead at a glance.
        "source": f"form:{form.slug}"[:60],
    }
    # Copy optional projected fields straight onto the model.
    for col in ("email", "phone", "website", "city", "inn"):
        v = projected.get(col)
        if v:
            lead_kwargs[col] = v[:300]

    lead = Lead(**lead_kwargs)
    session.add(lead)
    await session.flush()

    if notes:
        session.add(
            Activity(
                lead_id=lead.id,
                user_id=None,
                type="comment",
                payload_json={
                    "text": notes[:5000],
                    "source": "webform",
                    "form_slug": form.slug,
                },
            )
        )

    return lead


__all__ = ["FORM_FIELD_TO_LEAD", "create_lead_from_submission"]
