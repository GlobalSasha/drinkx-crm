"""DB access for the companies domain. Pure SQLAlchemy — no HTTP, no
business rules. All callers pass the AsyncSession and the
workspace_id; cross-workspace lookups are not exposed."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.companies.models import Company
from app.contacts.models import Contact
from app.leads.models import Lead


async def get_by_id(
    db: AsyncSession, *, workspace_id: UUID, company_id: UUID
) -> Company | None:
    res = await db.execute(
        select(Company).where(
            Company.id == company_id, Company.workspace_id == workspace_id
        )
    )
    return res.scalar_one_or_none()


async def list_companies(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    city: str | None = None,
    primary_segment: str | None = None,
    is_archived: bool | None = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[Sequence[Company], int]:
    base = select(Company).where(Company.workspace_id == workspace_id)
    if is_archived is not None:
        base = base.where(Company.is_archived == is_archived)
    if city:
        base = base.where(Company.city == city)
    if primary_segment:
        base = base.where(Company.primary_segment == primary_segment)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    items = (
        await db.execute(
            base.order_by(desc(Company.created_at)).limit(limit).offset(offset)
        )
    ).scalars().all()
    return items, int(total)


async def find_duplicates_by_normalized(
    db: AsyncSession, *, workspace_id: UUID, normalized_name: str
) -> list[tuple[Company, int]]:
    """Active companies with the same normalized_name, plus their
    leads_count. Used by the 409 duplicate-warning flow."""
    stmt = (
        select(Company, func.count(Lead.id).label("leads_count"))
        .outerjoin(Lead, Lead.company_id == Company.id)
        .where(
            Company.workspace_id == workspace_id,
            Company.normalized_name == normalized_name,
            Company.is_archived.is_(False),
        )
        .group_by(Company.id)
    )
    res = await db.execute(stmt)
    return [(row.Company, int(row.leads_count)) for row in res.all()]


async def list_leads_for_company(
    db: AsyncSession, *, workspace_id: UUID, company_id: UUID
) -> Sequence[Lead]:
    res = await db.execute(
        select(Lead)
        .where(Lead.workspace_id == workspace_id, Lead.company_id == company_id)
        .order_by(desc(Lead.created_at))
    )
    return res.scalars().all()


async def list_contacts_for_company(
    db: AsyncSession, *, workspace_id: UUID, company_id: UUID
) -> Sequence[Contact]:
    res = await db.execute(
        select(Contact)
        .where(Contact.workspace_id == workspace_id, Contact.company_id == company_id)
        .order_by(desc(Contact.created_at))
    )
    return res.scalars().all()


async def recent_activities_for_company(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    company_id: UUID,
    limit: int = 20,
) -> Sequence[Activity]:
    """Aggregate last `limit` activities across all leads that belong to
    this company. Returns ORM rows; routers project to schema."""
    res = await db.execute(
        select(Activity)
        .join(Lead, Lead.id == Activity.lead_id)
        .where(
            Lead.workspace_id == workspace_id,
            Lead.company_id == company_id,
        )
        .order_by(desc(Activity.created_at))
        .limit(limit)
    )
    return res.scalars().all()
