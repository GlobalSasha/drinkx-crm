"""Custom Attributes REST endpoints — Sprint 2.4 G3.

Surface (definition CRUD only — value rendering on Lead is a 2.4+
polish carryover; the value-upsert endpoint isn't shipped in G3 since
no UI calls it yet, but the service layer is ready for it):

  GET    /api/custom-attributes        — list (all roles)
  POST   /api/custom-attributes        — create (admin/head)
  PATCH  /api/custom-attributes/{id}   — update (admin/head)
  DELETE /api/custom-attributes/{id}   — delete (admin/head)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as log_audit_event
from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.custom_attributes import services as svc
from app.custom_attributes.schemas import (
    CustomAttributeDefinitionCreateIn,
    CustomAttributeDefinitionOut,
    CustomAttributeDefinitionUpdateIn,
)
from app.db import get_db


router = APIRouter(prefix="/custom-attributes", tags=["custom-attributes"])


@router.get("", response_model=list[CustomAttributeDefinitionOut])
async def list_definitions_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[CustomAttributeDefinitionOut]:
    """All workspace definitions, ordered by `position`. Read-open to
    every role — managers need to see what fields exist when filling
    out a lead form (LeadCard rendering lands in a 2.4+ follow-on)."""
    rows = await svc.list_definitions(db, workspace_id=user.workspace_id)
    return [CustomAttributeDefinitionOut.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=CustomAttributeDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_definition_endpoint(
    payload: CustomAttributeDefinitionCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CustomAttributeDefinitionOut:
    try:
        definition = await svc.create_definition(
            db,
            workspace_id=user.workspace_id,
            key=payload.key,
            label=payload.label,
            kind=payload.kind,
            options_json=(
                [opt.model_dump() for opt in payload.options_json]
                if payload.options_json
                else None
            ),
            is_required=payload.is_required,
        )
    except svc.InvalidKey as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_key",
                "message": (
                    "Ключ должен быть на латинице нижнего регистра, цифрах "
                    "или подчёркиваниях, и начинаться с буквы."
                ),
                "field": str(exc),
            },
        ) from exc
    except svc.InvalidKind as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_kind", "message": f"Неизвестный тип: {exc}"},
        ) from exc
    except svc.MissingOptions as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "missing_options",
                "message": "Для типа 'select' нужно указать варианты.",
            },
        ) from exc
    except svc.DuplicateKey as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_key",
                "message": f"Поле с ключом «{exc}» уже существует.",
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="custom_attribute.create",
        entity_type="custom_attribute_definition",
        entity_id=definition.id,
        delta={"key": definition.key, "kind": definition.kind},
    )
    await db.commit()
    return CustomAttributeDefinitionOut.model_validate(definition)


@router.patch(
    "/{definition_id}", response_model=CustomAttributeDefinitionOut
)
async def update_definition_endpoint(
    definition_id: uuid.UUID,
    payload: CustomAttributeDefinitionUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CustomAttributeDefinitionOut:
    try:
        definition = await svc.update_definition(
            db,
            definition_id=definition_id,
            workspace_id=user.workspace_id,
            label=payload.label,
            options_json=(
                [opt.model_dump() for opt in payload.options_json]
                if payload.options_json is not None
                else None
            ),
            is_required=payload.is_required,
            position=payload.position,
        )
    except svc.DefinitionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="custom attribute not found",
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="custom_attribute.update",
        entity_type="custom_attribute_definition",
        entity_id=definition.id,
        delta=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    return CustomAttributeDefinitionOut.model_validate(definition)


@router.delete("/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition_endpoint(
    definition_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> None:
    try:
        await svc.delete_definition(
            db,
            definition_id=definition_id,
            workspace_id=user.workspace_id,
        )
    except svc.DefinitionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="custom attribute not found",
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="custom_attribute.delete",
        entity_type="custom_attribute_definition",
        entity_id=definition_id,
    )
    await db.commit()
