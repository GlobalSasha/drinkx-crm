"""SEC-D1 step 3 -- invite expiry/reuse, real-DB gap check.

`app/auth/services.py::upsert_user_from_token` gates new-workspace-joins
and `_apply_pending_invite` gates re-sign-in acceptance with the same
predicate:

    UserInvite.accepted_at.is_(None),
    or_(UserInvite.expires_at.is_(None), UserInvite.expires_at > now)

Existing coverage of "expiry" (tests/test_users_service.py,
tests/test_auth_bootstrap.py) is mock-only: `db.execute` is an AsyncMock
or a canned list of return values chosen by the test author, and
tests/test_invite_accept.py stubs `sqlalchemy` itself out entirely. None
of that exercises the actual `or_(...)` predicate against a real
Postgres row -- the test decides in advance whether the "query" returns
an invite or None, which is exactly the behavior under test. So the
real SQL fail-closed check had zero DB-backed coverage. These two tests
close that gap; no source change needed here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _invite(db, workspace_id, *, email, expires_at, accepted_at=None):
    from app.auth.models import UserInvite

    inv = UserInvite(
        workspace_id=workspace_id,
        email=email,
        suggested_role="manager",
        expires_at=expires_at,
        accepted_at=accepted_at,
    )
    db.add(inv)
    await db.flush()
    return inv


@skip_no_pg
@pytest.mark.asyncio
async def test_expired_invite_is_a_real_db_noop_new_user_rejected(db, workspace):
    """A real, already-expired UserInvite row in Postgres must not admit
    a new user -- the `or_` predicate has to actually filter it out at
    the SQL level, not just in a test author's mocked return value."""
    from app.auth import services as auth_svc
    from app.auth.jwt import TokenClaims

    email = f"expired-{uuid.uuid4().hex[:6]}@example.com"
    await _invite(
        db,
        workspace.id,
        email=email,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    claims = TokenClaims(sub=str(uuid.uuid4()), email=email, name="Late Hire")

    with pytest.raises(auth_svc.InviteRequired):
        await auth_svc.upsert_user_from_token(db, claims)


@skip_no_pg
@pytest.mark.asyncio
async def test_not_yet_expired_invite_is_a_real_db_admit_new_user_joins(db, workspace):
    """Control case for the same predicate: a real, still-valid invite
    row DOES admit the new user, with the workspace and role it names."""
    from app.auth import services as auth_svc
    from app.auth.jwt import TokenClaims

    email = f"ontime-{uuid.uuid4().hex[:6]}@example.com"
    await _invite(
        db,
        workspace.id,
        email=email,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    claims = TokenClaims(sub=str(uuid.uuid4()), email=email, name="On-Time Hire")

    user = await auth_svc.upsert_user_from_token(db, claims)

    assert user is not None
    assert user.workspace_id == workspace.id
    assert user.role == "manager"
