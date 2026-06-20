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

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.contacts.models import Contact
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


# Person-name keys (clean fields). Bare "name" stays mapped to company_name,
# so it is intentionally excluded here.
PERSON_NAME_KEYS: tuple[str, ...] = (
    "имя", "фио", "ф.и.о.", "контактное лицо", "ваше имя",
    "как вас зовут", "contact name", "contact_name", "контакт",
)
# Free-text message keys, priority order.
QUESTION_KEYS: tuple[str, ...] = (
    "вопрос", "question", "сообщение", "message",
    "комментарий", "comment", "comments",
)
# Normalized blob labels that count as the free-text message.
_MESSAGE_LABELS = {"сообщение", "вопрос", "message", "comment", "comments", "комментарий"}
# Normalized blob labels excluded from the structured-fields summary.
_SUMMARY_EXCLUDE = _MESSAGE_LABELS | {
    "имя", "фио", "ф.и.о.", "контактное лицо", "ваше имя", "name", "контакт",
    "источник", "source", "email", "e-mail", "почта",
    "телефон", "phone", "тел", "mobile",
}


def _clean(text: str) -> str:
    """Collapse all runs of whitespace (incl. newlines) to single spaces."""
    return " ".join(str(text).split())


def _lookup(payload: Any, keys: tuple[str, ...]) -> str | None:
    """First non-empty value whose normalized key matches one of `keys`.
    Preserves the value's internal whitespace (callers collapse if needed)."""
    if not isinstance(payload, dict):
        return None
    norm_map = {_normalize_key(str(k)): v for k, v in payload.items()}
    for key in keys:
        v = norm_map.get(_normalize_key(key))
        if v not in (None, ""):
            return str(v).strip()
    return None


def _parse_labeled_block(text: str | None) -> list[tuple[str, str]]:
    """Split a newline-separated `Label: value` blob into ordered
    (label, value) pairs. Accepts ASCII ':' and full-width '：'. Returns
    [] when the text is not such a block."""
    pairs: list[tuple[str, str]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        positions = [line.find(c) for c in (":", "：") if line.find(c) > 0]
        if not positions:
            continue
        idx = min(positions)
        label = line[:idx].strip()
        value = line[idx + 1:].strip()
        if label and value:
            pairs.append((label, value))
    return pairs


def extract_person_name(payload: Any, *, limit: int = 120) -> str | None:
    """Contact person's name: a clean person-name field, else the `Имя:`/
    `ФИО:` line inside the message blob, else None."""
    v = _lookup(payload, PERSON_NAME_KEYS)
    if v:
        return _clean(v)[:limit]
    pairs = _parse_labeled_block(_lookup(payload, QUESTION_KEYS))
    name = next(
        (val for lbl, val in pairs if _normalize_key(lbl) in PERSON_NAME_KEYS),
        None,
    )
    return _clean(name)[:limit] if name else None


def extract_question(payload: Any, *, limit: int = 200) -> str | None:
    """The visitor's free-text message, or None when there is none
    (e.g. landing forms carrying only structured fields)."""
    raw = _lookup(payload, QUESTION_KEYS)
    if not raw:
        return None
    pairs = _parse_labeled_block(raw)
    if len(pairs) >= 2:  # a real Label:value blob, not a one-line message
        msg = next((val for lbl, val in pairs if _normalize_key(lbl) in _MESSAGE_LABELS), None)
        return _clean(msg)[:limit] if msg else None
    return _clean(raw)[:limit]


def extract_summary(payload: Any, *, limit: int = 200) -> str:
    """One-line recap of a structured blob (used when there is no
    free-text question): `Label: value · Label: value`, contact fields
    and noise excluded. Empty when the payload is not a blob."""
    pairs = _parse_labeled_block(_lookup(payload, QUESTION_KEYS))
    if len(pairs) < 2:
        return ""
    kept = [f"{lbl}: {val}" for lbl, val in pairs if _normalize_key(lbl) not in _SUMMARY_EXCLUDE]
    return _clean(" · ".join(kept))[:limit]


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
    utm: dict[str, str] | None = None,
) -> Lead:
    """Build the Lead + form_submission Activity (+ optional comment
    Activity if the payload included a freeform note) in the caller's
    session. Caller commits.

    Two activities are emitted by design — separating them lets the
    Activity Feed render the manager-facing comment as plain text while
    the form_submission row carries the structured provenance
    (form_name/slug/source_domain/utm) that is searchable and survives
    re-rendering even if the comment is later edited.
    """
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

    # Web-form contact (ADR-012): a submission carrying an email or phone
    # becomes a first-class Contact + primary ЛПР, so the lead card's
    # «Контакты» tab and one-click call/email work without manual entry.
    if lead.email or lead.phone:
        contact = Contact(
            workspace_id=lead.workspace_id,
            lead_id=lead.id,
            name=(extract_person_name(payload) or lead.email or lead.phone or "Контакт с формы")[:120],
            email=lead.email,
            phone=lead.phone,
            source="webform",
            confidence="high",
            verified_status="verified",
        )
        session.add(contact)
        await session.flush()
        if lead.primary_contact_id is None:
            lead.primary_contact_id = contact.id

    # UTM attribution (Odoo utm pattern): resolve source/medium/campaign names
    # into per-workspace dictionary rows and stamp their ids onto the lead, so
    # channel analytics become a GROUP BY. New names are auto-created.
    if utm:
        from app.utm.services import resolve_utm

        ids = await resolve_utm(session, form.workspace_id, utm)
        lead.utm_source_id = ids["utm_source_id"]
        lead.utm_medium_id = ids["utm_medium_id"]
        lead.utm_campaign_id = ids["utm_campaign_id"]

    # Sprint «Website Leads Intake»: route to the form's fixed owner and
    # drop a "Связаться" task. No owner → lead stays in pool (legacy
    # behaviour). Deterministic, NOT AI — this is system-created routing.
    if form.default_assignee_id:
        now = datetime.now(timezone.utc)
        lead.assignment_status = "assigned"
        lead.assigned_to = form.default_assignee_id
        lead.assigned_at = now
        try:
            sla_hours = int(form.contact_task_sla_hours or 2)
        except (TypeError, ValueError):
            sla_hours = 2
        session.add(
            Activity(
                lead_id=lead.id,
                user_id=None,
                type="task",
                body="Связаться с заявкой",
                task_due_at=now + timedelta(hours=sla_hours),
            )
        )

    if notes:
        session.add(
            Activity(
                lead_id=lead.id,
                user_id=None,
                type="comment",
                # `body` is the canonical comment text the Activity Feed renders
                # (FeedItemComment reads item.body). Mirror it into payload_json
                # for forensic metadata (source/form_slug). Without body the
                # webform comment showed up as an empty entry in the card.
                body=notes[:5000],
                payload_json={
                    "text": notes[:5000],
                    "source": "webform",
                    "form_slug": form.slug,
                },
            )
        )

    # Always emit a form_submission Activity — the canonical record that
    # this lead arrived via a public form. The Activity Feed renders this
    # with form_name + source_domain + utm chips so the manager sees
    # provenance at a glance without opening the FormSubmission row.
    session.add(
        Activity(
            lead_id=lead.id,
            user_id=None,
            type="form_submission",
            payload_json={
                "form_name": form.name,
                "form_slug": form.slug,
                "source_domain": (source_domain or "")[:300],
                "utm": dict(utm) if utm else {},
            },
        )
    )

    # Sprint 2.5 G1: fan out to the Automation Builder. Wrapped in
    # safe_evaluate_trigger so a misconfigured automation can't roll
    # back the public form-submission transaction (worst case: lead
    # is created but no automation fires; ops sees the warning log).
    from app.automation_builder.services import safe_evaluate_trigger

    await safe_evaluate_trigger(
        session,
        workspace_id=lead.workspace_id,
        trigger="form_submission",
        lead=lead,
        payload={"form_id": str(form.id)},
    )

    return lead


__all__ = ["FORM_FIELD_TO_LEAD", "create_lead_from_submission"]
