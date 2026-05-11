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


class CannotDeleteSelf(Exception):
    """400 — admin can't delete their own user row."""


class DeleteResult:
    """Container for delete_user() so the router can audit-log + return
    a structured response. `freed_leads` is how many active leads
    were reassigned back to the pool."""

    def __init__(self, *, email: str, name: str, role: str, freed_leads: int):
        self.email = email
        self.name = name
        self.role = role
        self.freed_leads = freed_leads


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


async def delete_user(
    session: AsyncSession,
    *,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> DeleteResult:
    """Remove a user from the workspace.

    Guards:
      - cannot delete yourself  → CannotDeleteSelf
      - cannot delete last admin → LastAdminRefusal
      - target must exist in workspace → UserNotFound

    Side effect: any active (non-archived) lead currently assigned to
    the target is returned to the pool. Historical activities and
    audit_log rows authored by them stay in place (FK SET NULL on
    delete) — the audit trail must survive the personnel change.
    Caller commits.
    """
    if target_user_id == actor_user_id:
        raise CannotDeleteSelf()

    user = await repo.get_by_id(
        session, user_id=target_user_id, workspace_id=workspace_id
    )
    if user is None:
        raise UserNotFound(str(target_user_id))

    if user.role == "admin":
        admin_count = await repo.count_admins(
            session, workspace_id=workspace_id
        )
        if admin_count <= 1:
            raise LastAdminRefusal()

    snapshot = DeleteResult(
        email=user.email,
        name=user.name,
        role=user.role,
        freed_leads=await repo.return_leads_to_pool(
            session,
            user_id=target_user_id,
            workspace_id=workspace_id,
        ),
    )
    await repo.delete_user_row(session, user=user)
    return snapshot
