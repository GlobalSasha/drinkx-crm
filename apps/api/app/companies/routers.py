"""REST endpoints for the companies domain (Sprint 3.3)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.companies import merge as merge_module
from app.companies import repositories as companies_repo
from app.companies import services as companies_service
from app.companies.schemas import (
    CompanyCardOut,
    CompanyContactOut,
    CompanyCreate,
    CompanyLeadOut,
    CompanyListOut,
    CompanyActivityOut,
    CompanyOut,
    CompanyUpdate,
)
from app.companies.services import (
    CompanyNotFound,
    DuplicateCompanyWarning,
)
from app.db import get_db

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyListOut)
async def list_companies(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    city: str | None = None,
    primary_segment: str | None = None,
    is_archived: bool | None = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> CompanyListOut:
    items, total = await companies_repo.list_companies(
        db,
        workspace_id=user.workspace_id,
        city=city,
        primary_segment=primary_segment,
        is_archived=is_archived,
        limit=limit,
        offset=offset,
    )
    return CompanyListOut(
        items=[CompanyOut.model_validate(c) for c in items],
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyCardOut)
async def get_company_card(
    company_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> CompanyCardOut:
    try:
        company = await companies_service.get_card(
            db, workspace_id=user.workspace_id, company_id=company_id
        )
    except CompanyNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )

    leads = await companies_repo.list_leads_for_company(
        db, workspace_id=user.workspace_id, company_id=company_id
    )
    contacts = await companies_repo.list_contacts_for_company(
        db, workspace_id=user.workspace_id, company_id=company_id
    )
    activities = await companies_repo.recent_activities_for_company(
        db, workspace_id=user.workspace_id, company_id=company_id, limit=20
    )

    return CompanyCardOut(
        **CompanyOut.model_validate(company).model_dump(),
        leads=[CompanyLeadOut.model_validate(l) for l in leads],
        contacts=[CompanyContactOut.model_validate(c) for c in contacts],
        recent_activities=[CompanyActivityOut.model_validate(a) for a in activities],
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CompanyOut)
async def create(
    payload: CompanyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    force: bool = Query(
        False,
        description="Skip the duplicate-warning 409 — used after the manager "
        "explicitly confirms «Создать новую» in the UI.",
    ),
) -> CompanyOut:
    try:
        company = await companies_service.create_company(
            db, workspace_id=user.workspace_id, data=payload, force=force
        )
    except DuplicateCompanyWarning as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "duplicate_warning",
                "candidates": [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "inn": c.inn,
                        "leads_count": leads_count,
                    }
                    for c, leads_count in e.candidates
                ],
            },
        )
    await db.commit()
    return CompanyOut.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyOut)
async def update(
    company_id: UUID,
    payload: CompanyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> CompanyOut:
    try:
        company = await companies_service.update_company(
            db,
            workspace_id=user.workspace_id,
            company_id=company_id,
            data=payload,
        )
    except CompanyNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    await db.commit()
    return CompanyOut.model_validate(company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive(
    company_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    """Soft archive — flips `is_archived = true`. Leads keep their FK
    so the snapshot in `leads.company_name` stays correct."""
    try:
        await companies_service.archive_company(
            db, workspace_id=user.workspace_id, company_id=company_id
        )
    except CompanyNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    await db.commit()


@router.post("/{source_id}/merge-into/{target_id}", response_model=CompanyOut)
async def merge_into(
    source_id: UUID,
    target_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    force: bool = Query(
        False,
        description="Override INN conflict (when source.inn != target.inn).",
    ),
) -> CompanyOut:
    try:
        target = await merge_module.merge_into(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
            source_id=source_id,
            target_id=target_id,
            force=force,
        )
    except merge_module.MergeNotPossible as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=e.message
        )
    except merge_module.InnConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "inn_conflict",
                "source_inn": e.source_inn,
                "target_inn": e.target_inn,
            },
        )
    await db.commit()
    return CompanyOut.model_validate(target)
