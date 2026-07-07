"""Service layer for the external OS surface. Called by REST + MCP."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.external import repositories as repo
from app.external.schemas import (
    CompanyOut, CompanyPage, ContactOut, LeadOut, LeadPage, LeadSummaryOut,
    ManagerOut, MetaOut, PipelineOut, PipelineSummaryOut, StageOut, StageSummary,
)
from app.pipelines.models import Stage

CONTRACT_VERSION = "1.0"
_MAX_LIMIT = 100


def _clamp(limit: int) -> int:
    return max(1, min(_MAX_LIMIT, limit))


def _lead_out(lead, stage_entered_at, assigned_to_name) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.stage_entered_at = stage_entered_at
    out.assigned_to_name = assigned_to_name
    return out


async def list_leads(db, workspace_id, *, pipeline_id=None, stage_id=None,
                     assigned_to=None, updated_since=None, q=None, cursor=None, limit=50) -> LeadPage:
    limit = _clamp(limit)
    rows = await repo.list_leads_rows(
        db, workspace_id, pipeline_id=pipeline_id, stage_id=stage_id,
        assigned_to=assigned_to, updated_since=updated_since, q=q, cursor=cursor, limit=limit,
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_lead_out(r[0], r[1], r[2]) for r in rows]
    next_cursor = repo.encode_cursor(rows[-1][0].updated_at, rows[-1][0].id) if has_more and rows else None
    return LeadPage(items=items, next_cursor=next_cursor)


async def get_lead(db, workspace_id, lead_id) -> LeadOut | None:
    row = await repo.get_lead_row(db, workspace_id, lead_id)
    if row is None:
        return None
    return _lead_out(row[0], row[1], row[2])


async def lead_summary(db, workspace_id, lead_id) -> LeadSummaryOut | None:
    row = await repo.get_lead_row(db, workspace_id, lead_id)
    if row is None:
        return None
    lead, stage_entered_at, assigned_to_name = row[0], row[1], row[2]
    lead_out = _lead_out(lead, stage_entered_at, assigned_to_name)

    company = None
    if lead.company_id is not None:
        c = await repo.get_company_row(db, workspace_id, lead.company_id)
        company = CompanyOut.model_validate(c) if c is not None else None

    contacts = [ContactOut.model_validate(c) for c in await repo.list_contacts_rows(
        db, workspace_id, lead_id=lead.id, company_id=None)]

    stage_name = stage_probability = None
    if lead.stage_id is not None:
        st = (await db.execute(select(Stage).where(Stage.id == lead.stage_id))).scalar_one_or_none()
        if st is not None:
            stage_name, stage_probability = st.name, st.probability

    days_in_stage = None
    if stage_entered_at is not None:
        days_in_stage = (datetime.now(timezone.utc) - stage_entered_at).days

    return LeadSummaryOut(
        lead=lead_out, company=company, contacts=contacts,
        stage_name=stage_name, stage_probability=stage_probability, days_in_stage=days_in_stage,
        is_rotting_stage=bool(lead.is_rotting_stage), is_rotting_next_step=bool(lead.is_rotting_next_step),
    )


async def list_companies(db, workspace_id, *, q=None, updated_since=None, cursor=None, limit=50) -> CompanyPage:
    limit = _clamp(limit)
    rows = await repo.list_companies_rows(db, workspace_id, q=q, updated_since=updated_since, cursor=cursor, limit=limit)
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [CompanyOut.model_validate(c) for c in rows]
    next_cursor = repo.encode_cursor(rows[-1].updated_at, rows[-1].id) if has_more and rows else None
    return CompanyPage(items=items, next_cursor=next_cursor)


async def get_company(db, workspace_id, company_id) -> CompanyOut | None:
    c = await repo.get_company_row(db, workspace_id, company_id)
    return CompanyOut.model_validate(c) if c is not None else None


async def list_contacts(db, workspace_id, *, lead_id=None, company_id=None) -> list[ContactOut]:
    rows = await repo.list_contacts_rows(db, workspace_id, lead_id=lead_id, company_id=company_id)
    return [ContactOut.model_validate(c) for c in rows]


def _pipeline_out(p) -> PipelineOut:
    return PipelineOut(
        id=p.id, name=p.name, position=p.position,
        stages=[StageOut.model_validate(s) for s in sorted(p.stages, key=lambda s: s.position)],
    )


async def list_pipelines(db, workspace_id) -> list[PipelineOut]:
    return [_pipeline_out(p) for p in await repo.list_pipelines_rows(db, workspace_id)]


async def pipeline_summary(db, workspace_id, pipeline_id) -> PipelineSummaryOut | None:
    p = await repo.get_pipeline_row(db, workspace_id, pipeline_id)
    if p is None:
        return None
    aggs = await repo.pipeline_stage_aggregates(db, workspace_id, pipeline_id)
    stages = [
        StageSummary(stage_id=a[0], stage_name=a[1], lead_count=a[2], total_amount=a[3], rotting_count=a[4])
        for a in aggs
    ]
    return PipelineSummaryOut(
        pipeline_id=p.id, pipeline_name=p.name, stages=stages,
        total_leads=sum(s.lead_count for s in stages),
        total_amount=sum((s.total_amount for s in stages), start=type(stages[0].total_amount)(0)) if stages else 0,
    )


async def meta(db, workspace_id) -> MetaOut:
    pipelines = await repo.list_pipelines_rows(db, workspace_id)
    all_stages = [StageOut.model_validate(s) for p in pipelines for s in p.stages]
    managers = [ManagerOut(id=m[0], name=m[1]) for m in await repo.list_managers(db, workspace_id)]
    return MetaOut(contract_version=CONTRACT_VERSION, stages=all_stages, managers=managers)
