"""base_update services: matching, auto-apply, resolution apply.

Only the matching slice is implemented here so far; auto-apply (Task 9)
and resolution applier (Task 10) come next.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.base_update import constants as c
from app.base_update.matcher import is_low_confidence
from app.base_update.models import IngestConflict, IngestRecord
from app.base_update.schemas import ExtractedCard
from app.companies import services as companies_svc
from app.companies.models import Company
from app.companies.schemas import CompanyCreate, CompanyUpdate
from app.companies.utils import normalize_company_name
from app.contacts import services as contacts_svc
from app.leads.models import Lead
from app.pipelines import repositories as pipelines_repo


@dataclass
class CompanyMatch:
    action: str  # "create" | "update" | "ambiguous"
    company_id: Any = None  # uuid.UUID at runtime; Any keeps the pure tests cheap
    candidates: list[dict] = field(default_factory=list)  # [{id, name}] for ambiguous (#1)


def _match_from_rows(name: str, rows: list[Any]) -> CompanyMatch:
    """Pure: given a name and the active-company rows already filtered by normalized key,
    decide create / update / ambiguous. Rows must expose `.id` and `.name`.
    """
    if not (name or "").strip():
        return CompanyMatch(action="create")
    if not rows:
        return CompanyMatch(action="create")
    if len(rows) == 1:
        return CompanyMatch(action="update", company_id=rows[0].id)
    return CompanyMatch(
        action="ambiguous",
        candidates=[{"id": str(r.id), "name": r.name} for r in rows],
    )


async def match_company(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str
) -> CompanyMatch:
    """Look up active companies whose normalized_name equals the normalized
    form of `name`, then classify via the pure helper."""
    key = normalize_company_name(name or "")
    if not key:
        return CompanyMatch(action="create")
    rows = (
        await db.execute(
            select(Company).where(
                Company.workspace_id == workspace_id,
                Company.normalized_name == key,
                Company.archived_at.is_(None),
            )
        )
    ).scalars().all()
    return _match_from_rows(name, list(rows))


def _conflict(
    record: IngestRecord,
    *,
    type_: str,
    target_kind: str,
    field_name: str | None = None,
    base_value: str | None = None,
    incoming_value: str | None = None,
    candidates: list[dict] | None = None,
) -> IngestConflict:
    """Build (do not persist) one IngestConflict row, parented to `record`.
    Caller adds it to the session."""
    return IngestConflict(
        ingest_job_id=record.ingest_job_id,
        ingest_record_id=record.id,
        type=type_,
        target_kind=target_kind,
        field_name=field_name,
        base_value=base_value,
        incoming_value=incoming_value,
        candidates_json=candidates,
        status=c.CONFLICT_OPEN,
    )


def _norm(v) -> str:
    return str(v).strip().lower() if v is not None else ""


def _diff_company_fields(card: ExtractedCard, company) -> tuple[dict, list[tuple[str, str | None, str | None]]]:
    """Return ({field_name: autofill_value}, [(field_name, base_str, incoming_str)] for conflicts).

    Operates only on CompanyCreate-compatible fields. The mapping
    card.company.segment → company.primary_segment is handled here.
    """
    pairs = [
        ("primary_segment", card.company.segment, getattr(company, "primary_segment", None)),
        ("website", card.company.website, getattr(company, "website", None)),
        ("inn", card.company.inn, getattr(company, "inn", None)),
        ("city", card.company.city, getattr(company, "city", None)),
        ("phone", card.company.phone, getattr(company, "phone", None)),
        ("email", card.company.email, getattr(company, "email", None)),
    ]
    updates: dict = {}
    conflicts: list[tuple[str, str | None, str | None]] = []
    for fld, incoming, base in pairs:
        if incoming is None or _norm(incoming) == "":
            continue
        if base is None or _norm(base) == "":
            updates[fld] = incoming
        elif _norm(base) == _norm(incoming):
            continue
        else:
            conflicts.append((fld, str(base), str(incoming)))
    return updates, conflicts


async def apply_record(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    record: IngestRecord,
    card: ExtractedCard,
    source_files: list[str],
    dedup_conflict_field: str | None,
) -> str:
    """Auto-write the safe parts of a dedup'd card into the base and
    queue per-type conflicts for the disputable parts. Returns the
    record.action it set."""
    record.source_files = source_files
    record.confidence = card.extraction_confidence

    pre_conflicts: list[IngestConflict] = []

    if is_low_confidence(card.extraction_confidence, company_name=card.company.name):
        pre_conflicts.append(
            _conflict(
                record,
                type_=c.C_LOW_CONFIDENCE,
                target_kind=c.TK_COMPANY,
                incoming_value=card.company.name or None,
            )
        )
    if dedup_conflict_field:
        pre_conflicts.append(
            _conflict(
                record,
                type_=c.C_BATCH_DUPLICATE,
                target_kind=c.TK_COMPANY,
                field_name=dedup_conflict_field,
            )
        )

    # If low confidence with empty name, we cannot safely match the base — bail out as conflict-only.
    if is_low_confidence(card.extraction_confidence, company_name=card.company.name) and not (card.company.name or "").strip():
        for cf in pre_conflicts:
            db.add(cf)
        record.action = c.ACTION_CONFLICT
        return c.ACTION_CONFLICT

    match = await match_company(db, workspace_id=workspace_id, name=card.company.name)

    if match.action == "ambiguous":
        pre_conflicts.append(
            _conflict(
                record,
                type_=c.C_COMPANY_AMBIGUOUS,
                target_kind=c.TK_COMPANY,
                incoming_value=card.company.name,
                candidates=match.candidates,
            )
        )
        for cf in pre_conflicts:
            db.add(cf)
        record.action = c.ACTION_CONFLICT
        return c.ACTION_CONFLICT

    had_conflict = bool(pre_conflicts)

    # Register pre-existing conflicts (low-confidence, batch-dup) before any writes.
    for cf in pre_conflicts:
        db.add(cf)

    if match.action == "create":
        company = await companies_svc.create_company(
            db,
            workspace_id=workspace_id,
            data=CompanyCreate(
                name=card.company.name,
                inn=card.company.inn,
                website=card.company.website,
                phone=card.company.phone,
                email=card.company.email,
                city=card.company.city,
                primary_segment=card.company.segment,
            ),
            force=True,
        )
        record.match_company_id = company.id

        first = await pipelines_repo.get_default_first_stage(db, workspace_id)
        if first is None:
            record.error = "no default pipeline / first stage in workspace"
            record.action = c.ACTION_CONFLICT
            return c.ACTION_CONFLICT
        pipeline_id, stage_id = first

        lead = Lead(
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            company_id=company.id,
            company_name=company.name,
            segment=card.company.segment,
            city=card.company.city,
            email=card.company.email,
            phone=card.company.phone,
            website=card.company.website,
            inn=card.company.inn,
            priority=card.company.priority,
            source="base_update",
            tags_json=[],
            assignment_status="pool",
            needs_review=True,
            ai_data={"base_update_brief": card.ai_brief} if card.ai_brief else None,
        )
        db.add(lead)
        await db.flush()
        record.match_lead_id = lead.id

        for ctc in card.contacts:
            await contacts_svc.create_contact(
                db,
                workspace_id,
                lead.id,
                {
                    "name": ctc.name,
                    "title": ctc.title,
                    "role_type": ctc.role_type,
                    "email": ctc.email,
                    "phone": ctc.phone,
                    "telegram": ctc.telegram,
                    "linkedin": ctc.linkedin,
                    "source": "base_update",
                    "verified_status": "to_verify",
                },
            )

        record.action = c.ACTION_CONFLICT if had_conflict else c.ACTION_CREATED
        return record.action

    # match.action == "update"
    company = await companies_svc.get_card(db, workspace_id=workspace_id, company_id=match.company_id)
    record.match_company_id = company.id

    updates, field_conflicts = _diff_company_fields(card, company)
    if updates:
        await companies_svc.update_company(
            db, workspace_id=workspace_id, company_id=company.id, data=CompanyUpdate(**updates)
        )
    late_conflicts: list[IngestConflict] = []
    for fld, base_v, incoming_v in field_conflicts:
        late_conflicts.append(
            _conflict(
                record,
                type_=c.C_FIELD_MISMATCH,
                target_kind=c.TK_COMPANY,
                field_name=fld,
                base_value=base_v,
                incoming_value=incoming_v,
            )
        )

    # Lead-target selection (#4): we keep it simple — the orchestrator decides
    # how to map the lead. Here we just queue a #4 conflict listing candidates
    # if >1 lead exists; otherwise we attach to the single existing lead, or
    # create a fresh pool lead if none exists.
    lead_rows = (
        await db.execute(
            select(Lead).where(
                Lead.workspace_id == workspace_id,
                Lead.company_id == company.id,
                Lead.assignment_status != "deleted",
            )
        )
    ).scalars().all()

    if len(lead_rows) == 0:
        first = await pipelines_repo.get_default_first_stage(db, workspace_id)
        if first is None:
            record.error = "no default pipeline / first stage in workspace"
            for cf in late_conflicts:
                db.add(cf)
            record.action = c.ACTION_CONFLICT
            return c.ACTION_CONFLICT
        pipeline_id, stage_id = first
        new_lead = Lead(
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            company_id=company.id,
            company_name=company.name,
            source="base_update",
            tags_json=[],
            assignment_status="pool",
            needs_review=True,
            ai_data={"base_update_brief": card.ai_brief} if card.ai_brief else None,
        )
        db.add(new_lead)
        await db.flush()
        record.match_lead_id = new_lead.id
    elif len(lead_rows) == 1:
        record.match_lead_id = lead_rows[0].id
    else:
        late_conflicts.append(
            _conflict(
                record,
                type_=c.C_LEAD_TARGET,
                target_kind=c.TK_LEAD,
                candidates=[{"id": str(l.id), "name": l.company_name or company.name} for l in lead_rows],
            )
        )

    for cf in late_conflicts:
        db.add(cf)
    record.action = c.ACTION_CONFLICT if (had_conflict or late_conflicts) else c.ACTION_UPDATED
    return record.action


log = logging.getLogger(__name__)


def _decide_apply(cf: IngestConflict) -> tuple[str, dict]:
    """Pure: map a resolved conflict to an operation descriptor.

    Returns `(op, args)`. `op` ∈
        "update_company_field" — args: {field, value}
        "set_match_company"    — args: {company_id}
        "set_record_error"     — args: {message}
        "noop"                 — no DB write
        "deferred"             — handled by a later iteration (Task 16+)
    """
    type_ = cf.type
    res = cf.resolution

    if type_ == c.C_FIELD_MISMATCH and cf.target_kind == c.TK_COMPANY:
        if res == c.R_OVERWRITE:
            return ("update_company_field", {"field": cf.field_name, "value": cf.incoming_value})
        if res == c.R_MANUAL:
            return ("update_company_field", {"field": cf.field_name, "value": cf.resolved_value})
        if res in (c.R_KEEP, c.R_SKIP):
            return ("noop", {})

    if type_ == c.C_COMPANY_AMBIGUOUS:
        if res == c.R_PICK and cf.resolved_value:
            return ("set_match_company", {"company_id": cf.resolved_value})
        if res in (c.R_KEEP, c.R_SKIP):
            return ("noop", {})

    if type_ == c.C_LOW_CONFIDENCE:
        if res == c.R_MANUAL:
            return ("set_record_error", {"message": f"manual: {cf.resolved_value or ''}"})
        if res == c.R_SKIP:
            return ("noop", {})

    if type_ == c.C_BATCH_DUPLICATE:
        if res in (c.R_KEEP, c.R_SKIP):
            return ("noop", {})
        # R_ADD_SEPARATE for #6 needs a re-run; defer.

    # TODO Task 16+: C_CONTACT_MISMATCH, C_LEAD_TARGET, brief overwrite
    return ("deferred", {})


async def _execute_op(db: AsyncSession, *, workspace_id, cf: IngestConflict, op: str, args: dict) -> bool:
    """Run the op chosen by _decide_apply. Returns True on success, False on failure
    (caller flips conflict status accordingly)."""
    if op == "noop":
        return True
    if op == "deferred":
        cf.record.error = f"resolution deferred: {cf.type}"
        return False
    if op == "update_company_field":
        company_id = cf.record.match_company_id
        if company_id is None:
            cf.record.error = "cannot apply: record has no match_company_id"
            return False
        try:
            await companies_svc.update_company(
                db, workspace_id=workspace_id, company_id=company_id,
                data=CompanyUpdate(**{args["field"]: args["value"]}),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("base_update.apply.update_company_failed", extra={"conflict": str(cf.id), "error": str(exc)[:200]})
            cf.record.error = f"update_company failed: {str(exc)[:120]}"
            return False
    if op == "set_match_company":
        try:
            cf.record.match_company_id = uuid.UUID(args["company_id"])
            return True
        except (ValueError, TypeError):
            cf.record.error = f"invalid company id: {args.get('company_id')!r}"
            return False
    if op == "set_record_error":
        cf.record.error = args["message"]
        return True
    cf.record.error = f"unknown op: {op}"
    return False


async def apply_resolutions(db: AsyncSession, *, workspace_id: uuid.UUID, job_id: uuid.UUID) -> dict:
    """Apply every conflict whose status is CONFLICT_RESOLVED. Returns a small
    summary dict for the orchestrator/log."""
    from app.base_update.models import IngestJob, IngestRecord  # local to avoid cycles

    # Load the job (workspace-scoped)
    job = (
        await db.execute(
            select(IngestJob).where(IngestJob.id == job_id, IngestJob.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise ValueError(f"job {job_id} not found in workspace {workspace_id}")

    # All conflicts marked CONFLICT_RESOLVED (admin has decided), join the record for FK + scoping
    conflicts = (
        await db.execute(
            select(IngestConflict)
            .join(IngestRecord, IngestRecord.id == IngestConflict.ingest_record_id)
            .where(
                IngestConflict.ingest_job_id == job_id,
                IngestConflict.status == c.CONFLICT_RESOLVED,
            )
        )
    ).scalars().all()

    applied = 0
    failed = 0
    deferred = 0
    for cf in conflicts:
        op, args = _decide_apply(cf)
        ok = await _execute_op(db, workspace_id=workspace_id, cf=cf, op=op, args=args)
        if op == "deferred":
            deferred += 1
        elif ok:
            applied += 1
        else:
            failed += 1
            cf.status = c.CONFLICT_OPEN  # bounce back so admin can retry

    # Recount open after our writes (deferred + bounced-back contribute to "open")
    open_count = (
        await db.execute(
            select(IngestConflict).where(
                IngestConflict.ingest_job_id == job_id,
                IngestConflict.status == c.CONFLICT_OPEN,
            )
        )
    ).scalars().all()
    job.status = c.JOB_DONE if len(open_count) == 0 else c.JOB_READY

    return {"applied": applied, "failed": failed, "deferred": deferred, "open": len(open_count)}
