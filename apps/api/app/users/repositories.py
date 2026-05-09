"""Users domain data access — Sprint 2.4 G1."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserInvite


async def list_for_workspace(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> tuple[list[User], int]:
    """Return all users in the workspace + total count. Sorted by
    role priority (admin → head → manager) then created_at — admins
    surface at the top of the «Команда» table."""
    base = select(User).where(User.workspace_id == workspace_id)

    count_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = int(count_result.scalar_one())

    rows_result = await db.execute(
        base.order_by(User.role.asc(), User.created_at.asc())
    )
    return list(rows_result.scalars().all()), total


async def get_by_id(
    db: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> User | None:
    """Workspace-scoped fetch — admin can't accidentally edit a
    foreign workspace's user. Wrong-workspace lookups return None,
    router maps to 404."""
    result = await db.execute(
        select(User).where(
            User.id == user_id, User.workspace_id == workspace_id
        )
    )
    return result.scalar_one_or_none()


async def count_admins(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> int:
    """Number of admins in the workspace. Used by the demote-guard
    in services — refuse to drop the count below 1."""
    result = await db.execute(
        select(func.count(User.id)).where(
            User.workspace_id == workspace_id, User.role == "admin"
        )
    )
    return int(result.scalar_one())


async def update_role(
    db: AsyncSession, *, user: User, role: str
) -> User:
    """Set + flush. Caller commits."""
    user.role = role
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------

async def create_invite(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    invited_by_user_id: uuid.UUID,
    email: str,
    suggested_role: str,
) -> UserInvite:
    """Create a UserInvite row. Caller handles the unique-constraint
    collision (re-invite to the same email in the same workspace)."""
    invite = UserInvite(
        workspace_id=workspace_id,
        invited_by_user_id=invited_by_user_id,
        email=email.lower().strip(),
        suggested_role=suggested_role,
    )
    db.add(invite)
    await db.flush()
    return invite


async def get_invite_by_email(
    db: AsyncSession, *, workspace_id: uuid.UUID, email: str
) -> UserInvite | None:
    result = await db.execute(
        select(UserInvite).where(
            UserInvite.workspace_id == workspace_id,
            UserInvite.email == email.lower().strip(),
        )
    )
    return result.scalar_one_or_none()


async def list_invites_for_workspace(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[UserInvite]:
    """All invite rows for the workspace, both pending + accepted.
    Pending sort to the top by accepted_at NULLS FIRST."""
    from sqlalchemy import nullsfirst

    result = await db.execute(
        select(UserInvite)
        .where(UserInvite.workspace_id == workspace_id)
        .order_by(nullsfirst(UserInvite.accepted_at), UserInvite.created_at.desc())
    )
    return list(result.scalars().all())
