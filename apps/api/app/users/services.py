"""Users domain services — Sprint 2.4 G1.

Three operations live here:
  - list workspace users (read by any role)
  - invite a new team member by email (admin-only at the router)
  - change a user's role (admin-only at the router) — defensive
    against demoting the last admin to keep the workspace
    bootstrappable.
"""
from __future__ import annotations

import uuid
from typing import Iterable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserInvite
from app.users import repositories as repo
from app.users.supabase_admin import (
    SupabaseInviteError,
    send_invite_email,
)

log = structlog.get_logger()

VALID_ROLES = ("admin", "head", "manager")


# ---------------------------------------------------------------------------
# Custom exceptions — router maps to HTTP
# ---------------------------------------------------------------------------

class UserNotFound(Exception):
    """404."""


class InvalidRole(Exception):
    """400 — the role string isn't one of admin/head/manager."""


class LastAdminRefusal(Exception):
    """409 — refuse to demote the workspace's last admin. Without
    this guard, the workspace could end up with zero admins, leaving
    no one able to invite / promote / settings."""


class InviteSendFailed(Exception):
    """502 — the row was created but Supabase didn't deliver. The
    invite stays in `user_invites` table; admin can retry."""


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_users(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> tuple[list[User], int]:
    return await repo.list_for_workspace(session, workspace_id=workspace_id)


async def list_invites(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Iterable[UserInvite]:
    return await repo.list_invites_for_workspace(
        session, workspace_id=workspace_id
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

async def invite_user(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    invited_by_user_id: uuid.UUID,
    email: str,
    role: str,
) -> UserInvite:
    """Send the magic-link via Supabase + persist a UserInvite row.

    Idempotent: if an invite for this (workspace, email) pair
    already exists, return the existing row (re-send the magic-link
    too — admin's intent is «invite this person», whether or not
    we've tried before).

    Caller commits.
    """
    if role not in VALID_ROLES:
        raise InvalidRole(role)

    existing = await repo.get_invite_by_email(
        session, workspace_id=workspace_id, email=email
    )

    # Re-send the magic-link first; if Supabase chokes we don't
    # want to have created a row that's a lie.
    try:
        await send_invite_email(email=email)
    except SupabaseInviteError as exc:
        raise InviteSendFailed(str(exc)) from exc

    if existing is not None:
        return existing

    return await repo.create_invite(
        session,
        workspace_id=workspace_id,
        invited_by_user_id=invited_by_user_id,
        email=email,
        suggested_role=role,
    )


async def change_role(
    session: AsyncSession,
    *,
    target_user_id: uuid.UUID,
    new_role: str,
    workspace_id: uuid.UUID,
) -> User:
    """Promote / demote the target user. Defensive:
      - role must be admin / head / manager
      - if the target is currently admin AND would become non-admin
        AND they're the LAST admin in the workspace, refuse with
        LastAdminRefusal (router → 409). Forces the inviter to
        promote someone else first.
    Caller commits."""
    if new_role not in VALID_ROLES:
        raise InvalidRole(new_role)

    user = await repo.get_by_id(
        session, user_id=target_user_id, workspace_id=workspace_id
    )
    if user is None:
        raise UserNotFound(str(target_user_id))

    if user.role == "admin" and new_role != "admin":
        admin_count = await repo.count_admins(
            session, workspace_id=workspace_id
        )
        if admin_count <= 1:
            raise LastAdminRefusal()

    return await repo.update_role(session, user=user, role=new_role)
