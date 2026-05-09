"""Message Templates REST endpoints — Sprint 2.4 G4.

Surface (mounted at `/api/templates`):
  GET    /api/templates         — list (any role; managers may need
                                   to preview templates in 2.5)
  POST   /api/templates         — create (admin only)
  PATCH  /api/templates/{id}    — update (admin only)
  DELETE /api/templates/{id}    — delete (admin only)

Mutations emit audit log entries; same shape as G3 settings.ai_change.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as log_audit_event
from app.auth.dependencies import current_user, require_admin
from app.auth.models import User
from app.db import get_db
from app.template import services as svc
from app.template.schemas import (
    MessageTemplateCreate,
    MessageTemplateOut,
    MessageTemplateUpdate,
)


router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[MessageTemplateOut])
async def list_templates_endpoint(
    channel: Annotated[
        str | None,
        Query(description="Filter by channel (email/tg/sms)"),
    ] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[MessageTemplateOut]:
    """All workspace templates, newest first. Read-open to every role
    so the manager-side preview in Automation Builder (2.5) doesn't
    need a permission shim."""
    try:
        rows = await svc.list_templates(
            db, workspace_id=user.workspace_id, channel=channel
        )
    except svc.InvalidChannel as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_channel",
                "message": f"Неизвестный канал: {exc}",
            },
        ) from exc
    return [MessageTemplateOut.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=MessageTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template_endpoint(
    payload: MessageTemplateCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> MessageTemplateOut:
    try:
        template = await svc.create_template(
            db,
            workspace_id=user.workspace_id,
            created_by=user.id,
            name=payload.name,
            channel=payload.channel,
            category=payload.category,
            text=payload.text,
        )
    except svc.InvalidChannel as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_channel",
                "message": f"Неизвестный канал: {exc}",
            },
        ) from exc
    except svc.DuplicateTemplate as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_template",
                "message": (
                    f"Шаблон «{exc.name}» для канала «{exc.channel}» "
                    "уже существует."
                ),
                "name": exc.name,
                "channel": exc.channel,
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="template.create",
        entity_type="message_template",
        entity_id=template.id,
        delta={"name": template.name, "channel": template.channel},
    )
    await db.commit()
    return MessageTemplateOut.model_validate(template)


@router.patch("/{template_id}", response_model=MessageTemplateOut)
async def update_template_endpoint(
    template_id: uuid.UUID,
    payload: MessageTemplateUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> MessageTemplateOut:
    # `category` is nullable: payload.category=None can mean «leave
    # as-is» or «clear the field». Pydantic doesn't distinguish via
    # `unset` here without `model_dump(exclude_unset=True)` gymnastics,
    # so the rule is: passing the key with `null` clears it. We detect
    # «key sent» via __fields_set__ on the parsed model.
    category_set = "category" in payload.model_fields_set

    try:
        template = await svc.update_template(
            db,
            template_id=template_id,
            workspace_id=user.workspace_id,
            name=payload.name,
            channel=payload.channel,
            category=payload.category,
            text=payload.text,
            category_set=category_set,
        )
    except svc.TemplateNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="message template not found",
        ) from exc
    except svc.InvalidChannel as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_channel",
                "message": f"Неизвестный канал: {exc}",
            },
        ) from exc
    except svc.DuplicateTemplate as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_template",
                "message": (
                    f"Шаблон «{exc.name}» для канала «{exc.channel}» "
                    "уже существует."
                ),
                "name": exc.name,
                "channel": exc.channel,
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="template.update",
        entity_type="message_template",
        entity_id=template.id,
        delta=payload.model_dump(exclude_unset=True),
    )
    await db.commit()
    return MessageTemplateOut.model_validate(template)


@router.delete(
    "/{template_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_template_endpoint(
    template_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> None:
    try:
        await svc.delete_template(
            db,
            template_id=template_id,
            workspace_id=user.workspace_id,
        )
    except svc.TemplateNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="message template not found",
        ) from exc
    except svc.TemplateInUse as exc:
        # Sprint 2.6 stability fix — structured 409 mirrors the Sprint
        # 2.3 PipelineHasLeads shape so the frontend can render a
        # «used by automation X» modal instead of a generic toast.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "template_in_use",
                "message": (
                    "Шаблон используется активной автоматизацией. "
                    "Сначала отключите или удалите автоматизацию."
                ),
                "automation_id": str(exc.automation_id),
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="template.delete",
        entity_type="message_template",
        entity_id=template_id,
    )
    await db.commit()
