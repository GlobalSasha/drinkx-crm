"""Automation Builder REST endpoints — Sprint 2.5 G1.

Surface (mounted at `/api/automations`):
  GET    /api/automations               — list (any role; managers may
                                          want to see what's configured)
  POST   /api/automations               — create (admin/head)
  PATCH  /api/automations/{id}          — update (admin/head)
  DELETE /api/automations/{id}          — delete (admin/head)
  GET    /api/automations/{id}/runs     — recent run history (any role)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as log_audit_event
from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.automation_builder import services as svc
from app.automation_builder.schemas import (
    AutomationCreate,
    AutomationOut,
    AutomationRunOut,
    AutomationUpdate,
)
from app.db import get_db


router = APIRouter(prefix="/automations", tags=["automations"])


@router.get("", response_model=list[AutomationOut])
async def list_automations_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[AutomationOut]:
    rows = await svc.list_automations(db, workspace_id=user.workspace_id)
    return [AutomationOut.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=AutomationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_automation_endpoint(
    payload: AutomationCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> AutomationOut:
    try:
        automation = await svc.create_automation(
            db,
            workspace_id=user.workspace_id,
            created_by=user.id,
            name=payload.name,
            trigger=payload.trigger,
            trigger_config_json=payload.trigger_config_json,
            condition_json=payload.condition_json,
            action_type=payload.action_type,
            action_config_json=payload.action_config_json,
            is_active=payload.is_active,
        )
    except svc.InvalidTrigger as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_trigger", "message": f"Неизвестный триггер: {exc}"},
        ) from exc
    except svc.InvalidAction as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_action", "message": f"Неизвестное действие: {exc}"},
        ) from exc
    except svc.InvalidActionConfig as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_action_config",
                "message": f"Конфигурация действия неполная: {exc}",
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="automation.create",
        entity_type="automation",
        entity_id=automation.id,
        delta={
            "name": automation.name,
            "trigger": automation.trigger,
            "action_type": automation.action_type,
        },
    )
    await db.commit()
    return AutomationOut.model_validate(automation)


@router.patch("/{automation_id}", response_model=AutomationOut)
async def update_automation_endpoint(
    automation_id: uuid.UUID,
    payload: AutomationUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> AutomationOut:
    sent = payload.model_fields_set
    try:
        automation = await svc.update_automation(
            db,
            automation_id=automation_id,
            workspace_id=user.workspace_id,
            name=payload.name,
            trigger=payload.trigger,
            trigger_config_json=payload.trigger_config_json,
            trigger_config_set="trigger_config_json" in sent,
            condition_json=payload.condition_json,
            condition_set="condition_json" in sent,
            action_type=payload.action_type,
            action_config_json=payload.action_config_json,
            is_active=payload.is_active,
        )
    except svc.AutomationNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="automation not found",
        ) from exc
    except svc.InvalidTrigger as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_trigger", "message": f"Неизвестный триггер: {exc}"},
        ) from exc
    except svc.InvalidAction as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_action", "message": f"Неизвестное действие: {exc}"},
        ) from exc
    except svc.InvalidActionConfig as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_action_config",
                "message": f"Конфигурация действия неполная: {exc}",
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="automation.update",
        entity_type="automation",
        entity_id=automation.id,
        delta=payload.model_dump(exclude_unset=True),
    )
    await db.commit()
    return AutomationOut.model_validate(automation)


@router.delete(
    "/{automation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_automation_endpoint(
    automation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> None:
    try:
        await svc.delete_automation(
            db,
            automation_id=automation_id,
            workspace_id=user.workspace_id,
        )
    except svc.AutomationNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="automation not found",
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="automation.delete",
        entity_type="automation",
        entity_id=automation_id,
    )
    await db.commit()


@router.get(
    "/{automation_id}/runs", response_model=list[AutomationRunOut]
)
async def list_automation_runs_endpoint(
    automation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[AutomationRunOut]:
    rows = await svc.list_runs(
        db,
        automation_id=automation_id,
        workspace_id=user.workspace_id,
        limit=limit,
    )
    return [AutomationRunOut.model_validate(r) for r in rows]
