"""Leads REST endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.automation.stage_change import StageTransitionBlocked, StageTransitionInvalid
from app.db import get_db
from app.leads import services
# Правило «кто может открыть этот лид» переехало в свой модуль: его же
# подключает /leads/{id}/tasks, который висит на другом роутере.
from app.leads.access import lead_access_guard
from app.leads.schemas import (
    DealPatchIn,
    ForecastOut,
    GateViolationOut,
    LeadAssignIn,
    LeadAssignOut,
    LeadCreate,
    LeadListOut,
    LeadOut,
    PoolFacetsOut,
    LeadUpdate,
    LeadPipelineChangeIn,
    MergeLeadsIn,
    MoveStageBlockedDetail,
    MoveStageIn,
    PrimaryContactIn,
    ScoreBreakdownOut,
    ScoreDetailsPatchIn,
    SprintCreateIn,
    SprintCreateOut,
    StageDurationOut,
    StageDwellOut,
    TransferIn,
    UtmSourceStatOut,
)
from app.leads.services import (
    LeadAlreadyClaimed,
    LeadNotFound,
    LeadNotOwnedByUser,
    PipelineNotFound,
    PrimaryContactInvalid,
    StageNotFound,
    TransferTargetInvalid,
)


def _resolve_assignee_scope(
    *,
    explicit: UUID | None,
    all_assignees: bool,
    q: str | None,
    user_id: UUID,
    role: str,
    workspace_search: bool = False,
) -> UUID | None:
    """Return the `assigned_to` filter for GET /leads (None = no assignee filter).

    `GET /leads` powers the pipeline kanban, /today widgets, and the
    message-to-lead picker. Scoping rules:

      - admin/head — full workspace access:
          * text search (`q`) → whole workspace (None), unless they
            explicitly picked a manager (explicit id) — then the q text
            filter still applies on top, giving a manager-scoped search
            rather than workspace-wide.
          * all_assignees → whole workspace (None) — the «Все» option.
          * explicit id → that manager.
          * nothing → self.
      - manager (any other role) — sees and edits ONLY leads assigned
        to himself. `explicit`, `all_assignees`, `q` and `workspace_search`
        can no longer widen or redirect the scope.
    """
    # Privileged role set mirrors app/auth/models.py USER_ROLES ("admin","head","manager").
    privileged = role in ("admin", "head")
    if not privileged:
        # Managers are always locked to their own book.
        return user_id
    # Whole-workspace text search: privileged users get it. Never overrides an
    # explicit manager selection.
    if q and (workspace_search or privileged) and not (privileged and explicit is not None):
        return None
    if privileged:
        if all_assignees:
            return None
        if explicit is not None:
            return explicit
        return user_id


router = APIRouter(
    prefix="/leads",
    tags=["leads"],
    dependencies=[Depends(lead_access_guard)],
)


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
    all_assignees: bool = False,
    workspace_search: bool = False,
    form_id: UUID | None = Query(None),
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
        assigned_to=_resolve_assignee_scope(
            explicit=assigned_to,
            all_assignees=all_assignees,
            q=q,
            user_id=user.id,
            role=user.role,
            workspace_search=workspace_search,
        ),
        q=q,
        form_id=form_id,
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


# Повторяющиеся параметры для множественного выбора: ?city=Москва&city=Казань.
# Одна кодировка на все списки — и в запросе списка, и в запросе счётчиков.
_MULTI = Annotated[list[str] | None, Query()]


def _pool_selection(
    *,
    city: list[str] | None,
    segment: list[str] | None,
    priority: list[str] | None,
    tier: list[str] | None,
    deal_type: list[str] | None,
    source: list[str] | None,
    tag: list[str] | None,
    fit_min: float | None,
    has_email: bool,
    has_phone: bool,
    form_id: UUID | None,
    needs_review: bool | None,
    q: str | None,
):
    from app.leads.selection import LeadSelection

    return LeadSelection.from_params(
        cities=city,
        segments=segment,
        priorities=priority,
        tiers=tier,
        deal_types=deal_type,
        sources=source,
        tags=tag,
        fit_min=fit_min,
        has_email=has_email,
        has_phone=has_phone,
        form_id=form_id,
        needs_review=needs_review,
        q=q,
        assignment_status="pool",
    )


@router.get("/pool", response_model=LeadListOut)
async def list_pool(
    city: _MULTI = None,
    segment: _MULTI = None,
    priority: _MULTI = None,
    tier: _MULTI = None,
    deal_type: _MULTI = None,
    source: _MULTI = None,
    tag: _MULTI = None,
    fit_min: float | None = None,
    has_email: bool = Query(False),
    has_phone: bool = Query(False),
    q: str | None = Query(None, max_length=200),
    form_id: UUID | None = Query(None),
    needs_review: bool | None = Query(None),
    page: int = Query(1, ge=1),
    # Страница снова страница. До G6 фронтенд просил 500 строк и решал
    # принадлежность к выборке у себя, поэтому карточка за этой границей не
    # находилась ничем (аудит G6). Отбор целиком ушёл в базу, и держать
    # потолок в пятьсот больше незачем.
    page_size: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    # Unassigned pool is management-only after the 2026-09-14 policy change.
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> LeadListOut:
    """Страница базы лидов. Весь отбор и порядок — на сервере.

    Множественный выбор кодируется повторением параметра. Между разными
    фильтрами И, внутри одного ИЛИ; теги — И, карточка обязана нести
    каждый выбранный.
    """
    selection = _pool_selection(
        city=city, segment=segment, priority=priority, tier=tier,
        deal_type=deal_type, source=source, tag=tag, fit_min=fit_min,
        has_email=has_email, has_phone=has_phone, form_id=form_id,
        needs_review=needs_review, q=q,
    )
    items, total = await services.list_pool(
        db, user.workspace_id, selection, page=page, page_size=page_size
    )
    return LeadListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/pool/facets", response_model=PoolFacetsOut)
async def pool_facets(
    form_id: UUID | None = Query(None),
    needs_review: bool | None = Query(None),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> PoolFacetsOut:
    """Значения фильтров и их размеры по всей базе лидов.

    Отдельным запросом, а не полем в списке: числа зависят только от
    области пула (форма и needs_review) и не меняются при листании и при
    выборе фасетов, поэтому клиент кэширует их отдельно, и переход на
    следующую страницу стоит двух запросов, а не девяти.
    """
    from app.leads.selection import LeadSelection

    selection = LeadSelection.pool(form_id=form_id, needs_review=needs_review)
    facets = await services.pool_facets(db, user.workspace_id, selection)
    total = sum(item["count"] for item in facets.get("tiers", []))
    return PoolFacetsOut(**facets, total=total)


@router.post("/assign", response_model=LeadAssignOut)
async def assign_leads(
    payload: LeadAssignIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> LeadAssignOut:
    """Выдать лиды менеджеру — пачкой по списку id или по фильтру из пула.

    Только руководитель и админ. Менеджер больше не может брать карточки
    из пула сам.
    """
    try:
        items, requested, skipped = await services.assign_leads(
            db,
            user.workspace_id,
            user.id,
            payload.to_user_id,
            mode=payload.mode,
            only_pool=payload.only_pool,
            lead_ids=payload.lead_ids,
            # Тот же контракт выборки, что у списка и экспорта: действие с
            # названием «по фильтру» обязано работать по тому фильтру,
            # который человек видит на экране (аудит G6).
            selection=payload.to_selection(),
            limit=payload.limit,
            comment=payload.comment,
        )
    except TransferTargetInvalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Получатель не найден в этом рабочем пространстве",
        )
    await db.commit()
    return LeadAssignOut(
        assigned_count=len(items),
        requested=requested,
        skipped=skipped,
        items=items,  # type: ignore[arg-type]
    )


@router.post("/sprint", response_model=SprintCreateOut)
async def create_sprint(
    payload: SprintCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    # A manager may no longer pull leads out of the pool himself.
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
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


@router.get("/stage-dwell", response_model=list[StageDwellOut])
async def lead_stage_dwell(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> list[StageDwellOut]:
    """«Где застревают сделки» — per active stage dwell stats (median/p90 days
    + how many leads are stuck past rot_days), bottlenecks first. Declared
    before `/{lead_id}` so the literal path wins.
    """
    from app.leads.analytics import stage_dwell_summary

    rows = await stage_dwell_summary(db, user.workspace_id)
    return [StageDwellOut(**r) for r in rows]


@router.get("/utm-stats", response_model=list[UtmSourceStatOut])
async def lead_utm_stats(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> list[UtmSourceStatOut]:
    """«Какой канал приносит сделки» — leads grouped by UTM source with
    won-deal count + revenue. Declared before `/{lead_id}` so the literal
    path wins over the path-param route.
    """
    from app.leads.analytics import utm_source_stats

    rows = await utm_source_stats(db, user.workspace_id)
    return [UtmSourceStatOut(**r) for r in rows]


@router.get("/forecast", response_model=ForecastOut)
async def lead_forecast(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ForecastOut:
    """«Прогноз» — суммы по ВСЕЙ доступной выборке, посчитанные в базе.

    Раньше страница складывала одну страницу `GET /leads`, прося 500 строк
    при потолке роута 200: запрос отбивался валидацией, и прогноз молча
    показывал нули. Агрегату страницы не нужны — ни `page`, ни `page_size`
    на него не влияют.

    Менеджер видит свои сделки, руководитель и админ — весь workspace. Это
    сознательное отличие от `GET /leads`, где по умолчанию даже админу
    отдаются только его лиды: прогноз без команды руководителю бесполезен.

    Объявлено ДО `/{lead_id}`, иначе литеральный путь перехватит
    маршрут с параметром и ответит 404.
    """
    from app.leads.analytics import forecast_summary

    scope = None if user.role in ("admin", "head") else user.id
    data = await forecast_summary(db, user.workspace_id, assigned_to=scope)
    return ForecastOut(**data)


@router.get("/trash", response_model=LeadListOut)
async def list_trash(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadListOut:
    """Soft-deleted leads only — the Trash view. Declared before
    `/{lead_id}` so the literal path wins."""
    filters = dict(
        page=page,
        page_size=page_size,
        assigned_to=None if user.role in ("admin", "head") else user.id,
    )
    items, total = await services.list_trash(db, user.workspace_id, filters)
    return LeadListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    from app.leads.repositories import get_by_id

    lead = await get_by_id(db, lead_id, user.workspace_id)
    if lead is None or lead.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    # Attach days-on-current-stage for the lead card stages bar.
    lead.current_stage_days = await services.current_stage_days(db, lead)  # type: ignore[attr-defined]
    return lead  # type: ignore[return-value]


@router.get("/{lead_id}/duplicates", response_model=list[LeadOut])
async def lead_duplicates(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[LeadOut]:
    """Likely duplicates of this lead — same corporate-email domain, phone, or
    company. Non-destructive: surfaces candidates for the manager to review and
    merge (the merge itself is a separate, explicit action).
    """
    from app.leads.dedup import find_duplicates
    from app.leads.repositories import get_by_id

    lead = await get_by_id(db, lead_id, user.workspace_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return await find_duplicates(db, lead)  # type: ignore[return-value]


@router.post("/{lead_id}/merge", response_model=LeadOut)
async def merge_lead_duplicates(
    lead_id: UUID,
    payload: MergeLeadsIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Merge the listed duplicate leads into this lead (the master).

    Human-triggered (the manager picks the master). Re-points history, fills the
    master's empty fields, archives the duplicates with merged_into_id set —
    soft and reversible. Never auto-runs.
    """
    from app.leads.dedup import MergeError, merge_leads

    try:
        master = await merge_leads(
            db,
            workspace_id=user.workspace_id,
            master_id=lead_id,
            duplicate_ids=payload.duplicate_ids,
            user_id=user.id,
        )
    except MergeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return master  # type: ignore[return-value]


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
    except services.CompanyNameLocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "company_name_locked",
                "message": "Лид связан с компанией. Переименуйте компанию — имя обновится автоматически.",
            },
        )
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
    """Move a lead to Trash (soft delete). Recoverable via `restore`."""
    from app.audit.audit import log as log_audit_event

    try:
        await services.soft_delete_lead(db, user.workspace_id, lead_id, user.id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await log_audit_event(
        db,
        action="lead.soft_delete",
        workspace_id=user.workspace_id,
        user_id=user.id,
        entity_type="lead",
        entity_id=lead_id,
    )
    await db.commit()


@router.post("/{lead_id}/restore", response_model=LeadOut)
async def restore_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Restore a lead out of Trash."""
    from app.audit.audit import log as log_audit_event

    try:
        lead = await services.restore_lead(db, user.workspace_id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await log_audit_event(
        db,
        action="lead.restore",
        workspace_id=user.workspace_id,
        user_id=user.id,
        entity_type="lead",
        entity_id=lead_id,
    )
    await db.commit()
    return lead  # type: ignore[return-value]


@router.delete("/{lead_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def destroy_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> None:
    """Permanently destroy a lead. admin/head only — irreversible."""
    from app.audit.audit import log as log_audit_event

    try:
        await services.destroy_lead(db, user.workspace_id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await log_audit_event(
        db,
        action="lead.destroy",
        workspace_id=user.workspace_id,
        user_id=user.id,
        entity_type="lead",
        entity_id=lead_id,
    )
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


@router.post("/{lead_id}/unclaim", response_model=LeadOut)
async def unclaim_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Return a lead the current user owns back to the workspace pool."""
    try:
        lead = await services.unclaim_lead(db, user.workspace_id, user.id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except LeadNotOwnedByUser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Можно вернуть в базу только свой лид",
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


@router.patch("/{lead_id}/primary-contact", response_model=LeadOut)
async def set_primary_contact(
    lead_id: UUID,
    payload: PrimaryContactIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Pin one Contact as «основной ЛПР» for this lead. Pass
    `{"contact_id": null}` to clear. Setting a new primary
    automatically replaces the previous — `primary_contact_id` is
    a single FK column on `leads`."""
    try:
        lead = await services.set_primary_contact(
            db, user.workspace_id, lead_id, payload.contact_id
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except PrimaryContactInvalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact not found or does not belong to this lead",
        )
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


# ---------------------------------------------------------------------------
# Lead Card v2 — deal-value + manual scoring + stage-durations
# ---------------------------------------------------------------------------


@router.patch("/{lead_id}/deal", response_model=LeadOut)
async def patch_deal(
    lead_id: UUID,
    payload: DealPatchIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Partial update of the deal-value strip (commercial model, sum,
    quantity, equipment). Empty `deal_equipment` normalises to NULL."""
    try:
        lead = await services.patch_deal_fields(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            fields_set=payload.model_fields_set,
            commercial_model=payload.commercial_model,
            deal_amount=payload.deal_amount,
            deal_quantity=payload.deal_quantity,
            deal_equipment=payload.deal_equipment,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead  # type: ignore[return-value]


@router.get("/{lead_id}/score-details", response_model=ScoreBreakdownOut)
async def get_score_details(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ScoreBreakdownOut:
    """Per-criterion score breakdown for the popup — joins this
    workspace's `scoring_criteria` with the lead's
    `score_details_json`. Always returns the full criteria list (with
    `current_value=0` for keys the manager hasn't touched yet)."""
    try:
        data = await services.get_score_breakdown(
            db, workspace_id=user.workspace_id, lead_id=lead_id
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return ScoreBreakdownOut.model_validate(data)


@router.patch("/{lead_id}/score-details", response_model=LeadOut)
async def patch_score_details(
    lead_id: UUID,
    payload: ScoreDetailsPatchIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Manual edit of the 8-criteria scoring grid. Body shape:

      { "score_details": { "scale_potential": 4, "budget_confirmed": 5, ... } }

    Unknown keys are dropped; values outside 0..max_value → 400.
    Server recomputes `leads.score` (integer 0..100) AND
    `leads.priority` (A/B/C/D via 80/60/40 thresholds) from the
    merged dict, then returns the updated LeadOut."""
    try:
        lead = await services.patch_score_details(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            patch=payload.score_details,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return lead  # type: ignore[return-value]


@router.get("/{lead_id}/stage-durations", response_model=list[StageDurationOut])
async def get_stage_durations(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[StageDurationOut]:
    """How many days a lead has spent in each stage of its pipeline.
    Source: `lead_stage_history` table (Sprint Lead Card Redesign).
    See service docstring for the per-stage day computation."""
    try:
        rows = await services.get_stage_durations(
            db, workspace_id=user.workspace_id, lead_id=lead_id
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return [StageDurationOut.model_validate(r) for r in rows]


@router.post("/{lead_id}/pipeline", response_model=LeadOut)
async def change_lead_pipeline(
    lead_id: UUID,
    payload: LeadPipelineChangeIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    """Перенос лида в другую воронку; лид встаёт на первый этап, если этап не указан."""
    try:
        lead = await services.change_pipeline(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
            lead_id=lead_id,
            pipeline_id=payload.pipeline_id,
            stage_id=payload.stage_id,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except PipelineNotFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Воронка не найдена в этом рабочем пространстве",
        )
    except StageNotFound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="В выбранной воронке нет этапов",
        )
    await db.commit()
    return lead  # type: ignore[return-value]
