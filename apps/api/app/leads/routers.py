"""Leads REST endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.automation.stage_change import StageTransitionBlocked, StageTransitionInvalid
from app.db import get_db
from app.leads import services
from app.leads.schemas import (
    GateViolationOut,
    LeadCreate,
    LeadListOut,
    LeadOut,
    LeadUpdate,
    MoveStageBlockedDetail,
    MoveStageIn,
    SprintCreateIn,
    SprintCreateOut,
    TransferIn,
)
from app.leads.services import (
    LeadAlreadyClaimed,
    LeadNotFound,
    LeadNotOwnedByUser,
    StageNotFound,
    TransferTargetInvalid,
)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadListOut)
async def list_leads(
    stage_id: UUID | None = None,
    pipeline_id: UUID | None = None,
    segment: str | None = None,
    city: str | None = None,
    priority: str | None = None,
    deal_type: str | None = None,
    assigned_to: UUID | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadListOut:
    filters = dict(
        stage_id=stage_id,
        pipeline_id=pipeline_id,
        segment=segment,
        city=city,
        priority=priority,
        deal_type=deal_type,
        assigned_to=assigned_to,
        q=q,
        page=page,
        page_size=page_size,
    )
    items, total = await services.list_leads(db, user.workspace_id, filters)
    return LeadListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    lead = await services.create_lead(db, user.workspace_id, user.id, payload)
    await db.commit()
    return lead  # type: ignore[return-value]


@router.get("/pool", response_model=LeadListOut)
async def list_pool(
    city: str | None = None,
    segment: str | None = None,
    fit_min: float | None = None,
    page: int = Query(1, ge=1),
    # Hotfix 2026-05-08: cap raised 200 → 500 to match the frontend's
    # intent. /leads-pool fetches the whole pool once and filters
    # client-side (commit 480d0a9 on 2026-05-07 set page_size=500),
    # but the cap still rejected with 422 every request — production
    # has been silently broken on /leads-pool since the 480d0a9 deploy.
    # 500 keeps a sane safety rail; longer-term fix is server-side
    # filtering when the workspace pool exceeds this.
    page_size: int = Query(50, ge=1, le=500),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadListOut:
    filters = dict(city=city, segment=segment, fit_min=fit_min, page=page, page_size=page_size)
    items, total = await services.list_pool(db, user.workspace_id, filters)
    return LeadListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/sprint", response_model=SprintCreateOut)
async def create_sprint(
    payload: SprintCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> SprintCreateOut:
    items, requested = await services.claim_sprint(
        db,
        user.workspace_id,
        user.id,
        cities=payload.cities,
        segment=payload.segment,
        limit=payload.limit,
    )
    await db.commit()
    return SprintCreateOut(
        claimed_count=len(items),
        requested=requested,
        items=items,  # type: ignore[arg-type]
    )


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    from app.leads.repositories import get_by_id

    lead = await get_by_id(db, lead_id, user.workspace_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead  # type: ignore[return-value]


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: UUID,
    payload: LeadUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.update_lead(db, user.workspace_id, lead_id, payload)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return lead  # type: ignore[return-value]


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    try:
        await services.delete_lead(db, user.workspace_id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await db.commit()


@router.post("/{lead_id}/claim", response_model=LeadOut)
async def claim_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.claim_lead(db, user.workspace_id, user.id, lead_id)
    except LeadAlreadyClaimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Эту карточку только что взял другой менеджер",
        )
    await db.commit()
    return lead  # type: ignore[return-value]


@router.post("/{lead_id}/transfer", response_model=LeadOut)
async def transfer_lead(
    lead_id: UUID,
    payload: TransferIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.transfer_lead(
            db,
            user.workspace_id,
            user.id,
            user.role,
            lead_id,
            payload.to_user_id,
            payload.comment,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except LeadNotOwnedByUser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this lead",
        )
    except TransferTargetInvalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer target user not found in this workspace",
        )
    await db.commit()
    return lead  # type: ignore[return-value]


@router.post("/{lead_id}/move-stage", response_model=LeadOut)
async def move_stage(
    lead_id: UUID,
    payload: MoveStageIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    # Sprint 2.6 G1 stability fix #1: stage_change POST_ACTIONS fan
    # out to Automation Builder; any `send_template` actions queue
    # email dispatch via this contextvar. SMTP runs AFTER commit
    # below so a slow / failing relay can't hold the move-stage
    # transaction.
    from app.automation_builder.dispatch import (
        collect_pending_email_dispatches,
        flush_pending_email_dispatches,
    )

    async with collect_pending_email_dispatches() as pending_emails:
        try:
            lead = await services.move_lead_stage(
                db,
                user.workspace_id,
                user.id,
                lead_id,
                payload.stage_id,
                gate_skipped=payload.gate_skipped,
                skip_reason=payload.skip_reason,
                lost_reason=payload.lost_reason,
            )
        except LeadNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        except StageNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
        except StageTransitionInvalid as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except StageTransitionBlocked as e:
            detail = MoveStageBlockedDetail(
                message="Stage transition blocked by gate criteria",
                violations=[
                    GateViolationOut(code=v.code, message=v.message, hard=v.hard)
                    for v in e.violations
                ],
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail.model_dump(),
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        await db.commit()

    await flush_pending_email_dispatches(pending_emails)
    return lead  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Sprint 2.6 G4 — custom-field values rendered + edited on the LeadCard
# ---------------------------------------------------------------------------


@router.get("/{lead_id}/attributes")
async def list_lead_attributes(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[dict]:
    """Workspace definitions merged with this lead's values. Returns
    one row per definition, in `position` order, with `value=null`
    when the manager hasn't filled the field yet.

    Workspace-scoping: lead lookup goes through `services.get_lead`
    which returns `LeadNotFound` for cross-workspace ids; downstream
    `list_values_with_definitions` filters definitions by workspace
    too, so a manager in workspace A can never see attributes from
    workspace B even via a leaked lead UUID.
    """
    from app.custom_attributes import services as ca_svc

    try:
        await services.get_lead(
            db, workspace_id=user.workspace_id, lead_id=lead_id
        )
    except LeadNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found"
        )

    rows = await ca_svc.list_values_with_definitions(
        db, workspace_id=user.workspace_id, lead_id=lead_id
    )
    return rows


@router.patch("/{lead_id}/attributes")
async def upsert_lead_attribute(
    lead_id: UUID,
    payload: dict,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> dict:
    """Inline-edit upsert for one custom field on one lead. Body
    shape: `{definition_id: uuid, value: str | null}`.

    Cross-workspace defence-in-depth: BOTH the lead AND the
    definition must belong to the caller's workspace. The lead lookup
    happens before the upsert; the definition's workspace is checked
    inside `upsert_value_from_string` via `repo.get_definition`. A
    manager in workspace A handing a leaked definition_id from
    workspace B gets a 403 — Sprint 2.6 G4 audit fix.
    """
    from app.custom_attributes import services as ca_svc

    # Pydantic validation done manually to keep the endpoint light —
    # body is small + only two fields. Fail fast on missing ids.
    raw_def_id = payload.get("definition_id")
    if not raw_def_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="definition_id is required",
        )
    try:
        definition_id = UUID(str(raw_def_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="definition_id must be a UUID",
        ) from exc
    raw_value = payload.get("value")

    try:
        await services.get_lead(
            db, workspace_id=user.workspace_id, lead_id=lead_id
        )
    except LeadNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found"
        )

    try:
        await ca_svc.upsert_value_from_string(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            definition_id=definition_id,
            raw_value=(
                str(raw_value) if raw_value is not None else None
            ),
        )
    except ca_svc.DefinitionNotFound as exc:
        # Cross-workspace lookup OR genuinely-deleted definition. Map
        # to 403 — the workspace-membership check in `get_definition`
        # is the security boundary here, not a mere 404.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Custom attribute is not in this workspace",
        ) from exc
    except ca_svc.InvalidValueForKind as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_value",
                "message": str(exc),
            },
        ) from exc

    await db.commit()

    # Echo back the merged attribute row so the caller can update its
    # client-side cache without a follow-up GET.
    rows = await ca_svc.list_values_with_definitions(
        db, workspace_id=user.workspace_id, lead_id=lead_id
    )
    for row in rows:
        if row["definition_id"] == definition_id:
            return row
    # Defensive — shouldn't happen since we just wrote the row.
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Updated attribute not found in re-read",
    )
