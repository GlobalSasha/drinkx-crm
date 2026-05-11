"""Users REST endpoints — Sprint 2.4 G1.

Surface:
  GET    /api/users                — list workspace users (all roles)
  GET    /api/users/invites        — list workspace invites (all roles)
  POST   /api/users/invite         — send invite (admin only)
  PATCH  /api/users/{id}/role      — change role (admin only)

The per-action role check happens via FastAPI dependencies. Read
access is open to all roles so a manager can see who else is on
the team in the «Команда» section of /settings.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as log_audit_event
from app.auth.dependencies import current_user, require_admin
from app.auth.models import User
from app.db import get_db
from app.users import services as svc
from app.users.schemas import (
    UserInviteIn,
    UserInviteOut,
    UserListItemOut,
    UserListOut,
    UserRoleUpdateIn,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListOut)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> UserListOut:
    items, total = await svc.list_users(db, workspace_id=user.workspace_id)
    return UserListOut(
        items=[UserListItemOut.model_validate(u) for u in items],
        total=total,
    )


@router.get("/invites", response_model=list[UserInviteOut])
async def list_invites(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[UserInviteOut]:
    invites = await svc.list_invites(db, workspace_id=user.workspace_id)
    return [UserInviteOut.model_validate(i) for i in invites]


@router.post(
    "/invite",
    response_model=UserInviteOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_user_endpoint(
    payload: UserInviteIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> UserInviteOut:
    try:
        invite = await svc.invite_user(
            db,
            workspace_id=user.workspace_id,
            invited_by_user_id=user.id,
            email=payload.email,
            role=payload.role,
        )
    except svc.InvalidRole as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid role: {exc}",
        ) from exc
    except svc.InviteSendFailed as exc:
        # Supabase upstream failure — surface 502 so the UI can
        # render a «retry later» state instead of a generic error.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "invite_send_failed",
                "message": "Не удалось отправить приглашение. Попробуйте позже.",
                "upstream": str(exc)[:200],
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="user.invite",
        entity_type="user_invite",
        entity_id=invite.id,
        delta={"email": invite.email, "suggested_role": invite.suggested_role},
    )
    await db.commit()
    return UserInviteOut.model_validate(invite)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> None:
    try:
        snap = await svc.delete_user(
            db,
            target_user_id=user_id,
            actor_user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except svc.CannotDeleteSelf as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "cannot_delete_self",
                "message": "Нельзя удалить себя.",
            },
        ) from exc
    except svc.UserNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="пользователь не найден",
        ) from exc
    except svc.LastAdminRefusal as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "last_admin",
                "message": (
                    "Это последний администратор в рабочем пространстве — "
                    "сначала повысьте кого-то ещё до admin."
                ),
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="user.delete",
        entity_type="user",
        entity_id=user_id,
        delta={
            "email": snap.email,
            "name": snap.name,
            "role": snap.role,
            "freed_leads": snap.freed_leads,
        },
    )
    await db.commit()


@router.patch("/{user_id}/role", response_model=UserListItemOut)
async def change_role_endpoint(
    user_id: uuid.UUID,
    payload: UserRoleUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> UserListItemOut:
    try:
        target = await svc.change_role(
            db,
            target_user_id=user_id,
            new_role=payload.role,
            workspace_id=user.workspace_id,
        )
    except svc.UserNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="пользователь не найден",
        ) from exc
    except svc.InvalidRole as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid role: {exc}",
        ) from exc
    except svc.LastAdminRefusal as exc:
        # Carry the structured 409 detail for the UI's friendly
        # «promote someone else first» modal — same pattern as
        # Sprint 2.3 PipelineHasLeads / PipelineIsDefault.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "last_admin",
                "message": (
                    "Это последний администратор в рабочем пространстве — "
                    "сначала повысьте кого-то ещё до admin."
                ),
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="user.role_change",
        entity_type="user",
        entity_id=target.id,
        delta={"email": target.email, "new_role": target.role},
    )
    await db.commit()
    return UserListItemOut.model_validate(target)
