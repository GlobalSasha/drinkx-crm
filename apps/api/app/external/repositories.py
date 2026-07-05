"""Workspace-scoped read queries for the external OS surface."""
from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.companies.models import Company
from app.contacts.models import Contact
from app.auth.models import User
from app.leads.models import Lead, LeadStageHistory
from app.pipelines.models import Pipeline, Stage


def encode_cursor(updated_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{updated_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, rid = raw.split("|", 1)
    return datetime.fromisoformat(ts), uuid.UUID(rid)


async def list_leads_rows(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    pipeline_id: uuid.UUID | None,
    stage_id: uuid.UUID | None,
    assigned_to: uuid.UUID | None,
    updated_since: datetime | None,
    q: str | None,
    cursor: str | None,
    limit: int,
):
    stmt = (
        select(Lead, LeadStageHistory.entered_at.label("stage_entered_at"), User.name.label("assigned_to_name"))
        .outerjoin(
            LeadStageHistory,
            and_(LeadStageHistory.lead_id == Lead.id, LeadStageHistory.exited_at.is_(None)),
        )
        .outerjoin(User, User.id == Lead.assigned_to)
        .where(Lead.workspace_id == workspace_id, Lead.deleted_at.is_(None))
    )
    if pipeline_id is not None:
        stmt = stmt.where(Lead.pipeline_id == pipeline_id)
    if stage_id is not None:
        stmt = stmt.where(Lead.stage_id == stage_id)
    if assigned_to is not None:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    if updated_since is not None:
        stmt = stmt.where(Lead.updated_at >= updated_since)
    if q is not None:
        stmt = stmt.where(Lead.company_name.ilike(f"%{q}%"))
    if cursor is not None:
        c_ts, c_id = decode_cursor(cursor)
        stmt = stmt.where(
            (Lead.updated_at, Lead.id) < (c_ts, c_id)  # row-value comparison
        )
    stmt = stmt.order_by(Lead.updated_at.desc(), Lead.id.desc()).limit(limit + 1)
    return list((await db.execute(stmt)).all())


async def get_lead_row(db, workspace_id, lead_id):
    stmt = (
        select(Lead, LeadStageHistory.entered_at.label("stage_entered_at"), User.name.label("assigned_to_name"))
        .outerjoin(
            LeadStageHistory,
            and_(LeadStageHistory.lead_id == Lead.id, LeadStageHistory.exited_at.is_(None)),
        )
        .outerjoin(User, User.id == Lead.assigned_to)
        .where(Lead.id == lead_id, Lead.workspace_id == workspace_id, Lead.deleted_at.is_(None))
    )
    return (await db.execute(stmt)).first()


async def get_company_row(db, workspace_id, company_id):
    stmt = select(Company).where(
        Company.id == company_id, Company.workspace_id == workspace_id, Company.is_archived.is_(False)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_companies_rows(db, workspace_id, *, q, updated_since, cursor, limit):
    stmt = select(Company).where(Company.workspace_id == workspace_id, Company.is_archived.is_(False))
    if q is not None:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    if updated_since is not None:
        stmt = stmt.where(Company.updated_at >= updated_since)
    if cursor is not None:
        c_ts, c_id = decode_cursor(cursor)
        stmt = stmt.where((Company.updated_at, Company.id) < (c_ts, c_id))
    stmt = stmt.order_by(Company.updated_at.desc(), Company.id.desc()).limit(limit + 1)
    return list((await db.execute(stmt)).scalars().all())


async def list_contacts_rows(db, workspace_id, *, lead_id, company_id):
    # Contact carries workspace_id directly (see app/contacts/models.py),
    # so isolation is a plain filter — no join needed.
    stmt = select(Contact).where(Contact.workspace_id == workspace_id)
    if lead_id is not None:
        stmt = stmt.where(Contact.lead_id == lead_id)
    else:
        stmt = stmt.where(Contact.company_id == company_id)
    return list((await db.execute(stmt)).scalars().all())


async def list_pipelines_rows(db, workspace_id):
    stmt = (
        select(Pipeline)
        .where(Pipeline.workspace_id == workspace_id)
        .options(selectinload(Pipeline.stages))
        .order_by(Pipeline.position)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_pipeline_row(db, workspace_id, pipeline_id):
    stmt = (
        select(Pipeline)
        .where(Pipeline.id == pipeline_id, Pipeline.workspace_id == workspace_id)
        .options(selectinload(Pipeline.stages))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def pipeline_stage_aggregates(db, workspace_id, pipeline_id):
    stmt = (
        select(
            Stage.id,
            Stage.name,
            func.count(Lead.id),
            func.coalesce(func.sum(Lead.deal_amount), 0),
            func.coalesce(func.sum(case((Lead.is_rotting_stage, 1), else_=0)), 0),
        )
        .select_from(Stage)
        .outerjoin(
            Lead,
            and_(
                Lead.stage_id == Stage.id,
                Lead.workspace_id == workspace_id,
                Lead.deleted_at.is_(None),
            ),
        )
        .where(Stage.pipeline_id == pipeline_id)
        .group_by(Stage.id, Stage.name, Stage.position)
        .order_by(Stage.position)
    )
    return list((await db.execute(stmt)).all())


async def list_managers(db, workspace_id):
    stmt = select(User.id, User.name).where(User.workspace_id == workspace_id).order_by(User.name)
    return list((await db.execute(stmt)).all())
