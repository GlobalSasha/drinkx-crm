"""Auth domain services — workspace bootstrap and user upsert."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import TokenClaims
from app.auth.models import User, Workspace
from app.pipelines.models import DEFAULT_STAGES, Pipeline, Stage


def _email_to_workspace_name(email: str) -> str:
    """Stub: use the email's domain as workspace name. Manager can rename later."""
    domain = email.split("@", 1)[-1] if "@" in email else email
    base = re.sub(r"\.(ru|com|tech|io|net|org)$", "", domain, flags=re.I)
    return base.replace(".", " ").title() or "Workspace"


async def upsert_user_from_token(session: AsyncSession, claims: TokenClaims) -> User:
    """Look up or create the User identified by the JWT claims.

    On first sign-in: creates a Workspace + default Pipeline with 7 stages,
    then creates the User as the workspace's first admin.
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

    # 3. Brand new user — bootstrap a Workspace + default pipeline
    workspace = Workspace(
        name=_email_to_workspace_name(claims.email),
        plan="free",
    )
    session.add(workspace)
    await session.flush()

    pipeline = Pipeline(
        workspace_id=workspace.id,
        name="Новые клиенты",
        type="sales",
        is_default=True,
        position=0,
    )
    session.add(pipeline)
    await session.flush()

    for s in DEFAULT_STAGES:
        session.add(Stage(pipeline_id=pipeline.id, **s))

    # Sprint 2.3 G1: also set the canonical FK pointer on the
    # workspace. The legacy `pipelines.is_default=True` above is kept
    # for back-compat with diff_engine + the migration backfill, but
    # the new default-resolver reads through `default_pipeline_id`.
    workspace.default_pipeline_id = pipeline.id
    await session.flush()

    user = User(
        workspace_id=workspace.id,
        email=claims.email,
        name=claims.name or claims.email.split("@", 1)[0].title(),
        role="admin",  # first user becomes admin
        supabase_user_id=claims.sub,
        last_login_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    return user
