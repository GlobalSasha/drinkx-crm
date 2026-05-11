"""Business rules for the companies domain (Sprint 3.3).

Key invariants:
- `normalized_name` and `domain` are derived server-side from
  `name` / `website`. Frontend never sends them.
- Creation triggers a 409 `duplicate_warning` if a non-archived row
  with the same normalized_name exists; client may retry with
  `?force=true`.
- Renaming a company propagates to `leads.company_name` for ACTIVE
  leads only. Closed/archived leads keep their historical snapshot
  — the spec's `is_archived = false` filter is implemented here as
  `archived_at IS NULL` (the actual lead column; see Phase 0 §7).
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.companies.repositories import find_duplicates_by_normalized, get_by_id
from app.companies.schemas import CompanyCreate, CompanyUpdate
from app.companies.utils import extract_domain, normalize_company_name
from app.leads.models import Lead


class CompanyNotFound(Exception):
    def __init__(self, company_id: UUID):
        self.company_id = company_id


@dataclass
class DuplicateCompanyWarning(Exception):  # type: ignore[misc]
    """Raised by `create_company(force=False)` when at least one active
    row with the same normalized_name exists. The router catches and
    translates into a 409 response containing `candidates`."""

    candidates: list[tuple[Company, int]]


async def create_company(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    data: CompanyCreate,
    force: bool = False,
) -> Company:
    normalized = normalize_company_name(data.name)
    if not force:
        candidates = await find_duplicates_by_normalized(
            db, workspace_id=workspace_id, normalized_name=normalized
        )
        if candidates:
            raise DuplicateCompanyWarning(candidates=candidates)

    company = Company(
        workspace_id=workspace_id,
        name=data.name,
        normalized_name=normalized,
        legal_name=data.legal_name,
        inn=data.inn,
        kpp=data.kpp,
        website=data.website,
        domain=extract_domain(data.website),
        phone=data.phone,
        email=data.email,
        city=data.city,
        address=data.address,
        primary_segment=data.primary_segment,
        employee_range=data.employee_range,
        notes=data.notes,
    )
    db.add(company)
    await db.flush()
    return company


async def update_company(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    company_id: UUID,
    data: CompanyUpdate,
) -> Company:
    company = await get_by_id(db, workspace_id=workspace_id, company_id=company_id)
    if company is None:
        raise CompanyNotFound(company_id)

    new_name: str | None = None
    if data.name is not None and data.name != company.name:
        new_name = data.name
        company.name = data.name
        company.normalized_name = normalize_company_name(data.name)

    if data.website is not None:
        company.website = data.website
        company.domain = extract_domain(data.website)

    # Patch other fields (use model_dump exclude_unset so we only touch
    # what the client sent).
    payload = data.model_dump(exclude_unset=True, exclude={"name", "website"})
    for key, value in payload.items():
        setattr(company, key, value)

    # Name-sync rule: only ACTIVE leads inherit a renamed company.
    # `leads` schema has `archived_at` not `is_archived` — substitution
    # per Phase 0 feasibility note.
    if new_name is not None:
        await db.execute(
            text(
                "UPDATE leads SET company_name = :n, updated_at = now() "
                "WHERE company_id = :id AND archived_at IS NULL"
            ),
            {"n": new_name, "id": company_id},
        )

    await db.flush()
    return company


async def archive_company(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    company_id: UUID,
) -> None:
    """Soft archive — sets `is_archived = true` + `archived_at = now()`.
    Leads keep their `company_id` (we don't null it out — the snapshot
    in `leads.company_name` stays correct)."""
    company = await get_by_id(db, workspace_id=workspace_id, company_id=company_id)
    if company is None:
        raise CompanyNotFound(company_id)
    from datetime import datetime, timezone

    company.is_archived = True
    company.archived_at = datetime.now(tz=timezone.utc)
    await db.flush()


async def get_card(
    db: AsyncSession, *, workspace_id: UUID, company_id: UUID
) -> Company:
    company = await get_by_id(db, workspace_id=workspace_id, company_id=company_id)
    if company is None:
        raise CompanyNotFound(company_id)
    return company


async def leads_count(
    db: AsyncSession, *, workspace_id: UUID, company_id: UUID
) -> int:
    """Lightweight count used by the duplicate-warning payload — but
    `find_duplicates_by_normalized` already returns counts via the
    aggregate. This helper is here for one-off lookups (e.g. the card
    page subtitle) so callers don't reach for `select count()` ad hoc."""
    from sqlalchemy import func

    res = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.workspace_id == workspace_id, Lead.company_id == company_id
        )
    )
    return int(res.scalar() or 0)
