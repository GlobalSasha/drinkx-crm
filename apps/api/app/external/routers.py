"""GET-only REST surface for external OS access — /external/v1/*."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.external import services as svc
from app.external.dependencies import ServiceContext, require_service_key
from app.external.schemas import (
    CompanyOut, CompanyPage, ContactOut, LeadOut, LeadPage, LeadSummaryOut,
    MetaOut, PipelineOut, PipelineSummaryOut,
)

router = APIRouter(prefix="/external/v1", tags=["external"])

_Ctx = Annotated[ServiceContext, Depends(require_service_key())]
_Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/leads", response_model=LeadPage)
async def list_leads(
    ctx: _Ctx, db: _Db,
    pipeline_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    updated_since: datetime | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return await svc.list_leads(
        db, ctx.workspace_id, pipeline_id=pipeline_id, stage_id=stage_id,
        assigned_to=assigned_to, updated_since=updated_since, q=q, cursor=cursor, limit=limit,
    )


@router.get("/leads/{lead_id}", response_model=LeadOut)
async def get_lead(ctx: _Ctx, db: _Db, lead_id: uuid.UUID):
    out = await svc.get_lead(db, ctx.workspace_id, lead_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    return out


@router.get("/leads/{lead_id}/summary", response_model=LeadSummaryOut)
async def lead_summary(ctx: _Ctx, db: _Db, lead_id: uuid.UUID):
    out = await svc.lead_summary(db, ctx.workspace_id, lead_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    return out


@router.get("/companies", response_model=CompanyPage)
async def list_companies(
    ctx: _Ctx, db: _Db,
    q: str | None = None,
    updated_since: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    return await svc.list_companies(db, ctx.workspace_id, q=q, updated_since=updated_since, cursor=cursor, limit=limit)


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(ctx: _Ctx, db: _Db, company_id: uuid.UUID):
    out = await svc.get_company(db, ctx.workspace_id, company_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")
    return out


@router.get("/contacts", response_model=list[ContactOut])
async def list_contacts(
    ctx: _Ctx, db: _Db,
    lead_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
):
    if (lead_id is None) == (company_id is None):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exactly one of lead_id or company_id required")
    return await svc.list_contacts(db, ctx.workspace_id, lead_id=lead_id, company_id=company_id)


@router.get("/pipelines", response_model=list[PipelineOut])
async def list_pipelines(ctx: _Ctx, db: _Db):
    return await svc.list_pipelines(db, ctx.workspace_id)


@router.get("/pipelines/{pipeline_id}/summary", response_model=PipelineSummaryOut)
async def pipeline_summary(ctx: _Ctx, db: _Db, pipeline_id: uuid.UUID):
    out = await svc.pipeline_summary(db, ctx.workspace_id, pipeline_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline not found")
    return out


@router.get("/meta", response_model=MetaOut)
async def meta(ctx: _Ctx, db: _Db):
    return await svc.meta(db, ctx.workspace_id)
