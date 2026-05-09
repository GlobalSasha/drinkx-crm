"""Auth domain services — workspace bootstrap and user upsert.

Hotfix 2026-05-08: single-workspace model. DrinkX needs ONE shared
workspace for the entire team — every user signs in into the same
data plane (same lead pool, same pipelines, same notifications).
The first user creates the workspace; every subsequent user joins
it automatically with role='manager'. No invites in v1; assignment
isolation is already handled at the lead level
(`assignment_status='assigned'` + `assigned_to=user_id`).

The previous behavior (a workspace per user) was creating
disconnected silos as soon as a second team member signed in —
they'd land in an empty workspace with no leads.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import TokenClaims
from app.auth.models import User, Workspace
from app.config import get_settings
from app.pipelines.models import DEFAULT_STAGES, Pipeline, Stage


async def upsert_user_from_token(session: AsyncSession, claims: TokenClaims) -> User:
    """Look up or create the User identified by the JWT claims.

    First user to sign in:
      - Creates the shared Workspace (name from settings.workspace_name)
      - Creates the bootstrap Pipeline + 12 stages
      - User joins as role='admin'

    Every subsequent user:
      - Joins the EXISTING shared workspace (oldest by created_at)
      - User joins as role='manager'
      - No invite, no manual assignment — the team uses one data plane
    """
    # 1. Try to find by Supabase user id
    result = await session.execute(
        select(User).where(User.supabase_user_id == claims.sub)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # 2. Or by email (e.g. they signed in via different OAuth at the same address)
        result = await session.execute(select(User).where(User.email == claims.email))
        user = result.scalar_one_or_none()

    if user is not None:
        # Update mutable fields and last_login
        if user.supabase_user_id is None:
            user.supabase_user_id = claims.sub
        if claims.name and not user.name:
            user.name = claims.name
        user.last_login_at = datetime.now(timezone.utc)
        await session.flush()
        return user

    # 3. New user — find the shared workspace if it exists.
    settings = get_settings()
    result = await session.execute(
        select(Workspace).order_by(Workspace.created_at.asc()).limit(1)
    )
    workspace = result.scalar_one_or_none()

    if workspace is None:
        # First-ever user — create the shared workspace + bootstrap pipeline.
        workspace = Workspace(
            name=settings.workspace_name or "DrinkX",
            plan="free",
        )
        session.add(workspace)
        await session.flush()

        pipeline = Pipeline(
            workspace_id=workspace.id,
            name="Новые клиенты",
            type="sales",
            # Sprint 2.4 G1: legacy `is_default` column dropped by
            # migration 0017. The canonical default-pointer is
            # `workspace.default_pipeline_id`, set right below.
            position=0,
        )
        session.add(pipeline)
        await session.flush()

        for s in DEFAULT_STAGES:
            session.add(Stage(pipeline_id=pipeline.id, **s))

        # Sprint 2.3 G1: canonical FK pointer.
        workspace.default_pipeline_id = pipeline.id
        await session.flush()

        role = "admin"
    else:
        # Subsequent user — joins the existing shared workspace.
        # Note: workspace might still be in the legacy «one workspace
        # per user» state if the data migration hasn't run yet, but
        # selecting the OLDEST workspace is the right pick — that's
        # the canonical one in production today.
        role = "manager"

    user = User(
        workspace_id=workspace.id,
        email=claims.email,
        name=claims.name or claims.email.split("@", 1)[0].title(),
        role=role,
        supabase_user_id=claims.sub,
        last_login_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    return user
