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

Isolation note (audit-integration, full-suite run on drinkx_ci4):
`upsert_user_from_token`'s new-user path picks a workspace with
`SELECT ... ORDER BY created_at ASC LIMIT 1` -- "the" shared workspace.
Several other tests in this suite (including the oauth-state tests in
this same SEC-D1 batch, see `SEC-D1/REPRO.md`) reach a code path that
does a REAL `db.commit()`, so their `Workspace` fixture rows can survive
into the shared `drinkx_ci4` database after their own test finishes.
Whichever workspace happens to be globally oldest when this test runs is
whatever that query returns -- if it isn't the `workspace` fixture this
test built its invite in, `upsert_user_from_token` resolves a workspace
with no matching invite and raises `InviteRequired` for a reason that
has nothing to do with expiry. `_pin_as_oldest_workspace` makes the
`workspace` fixture provably win that ordering, by reading the actual
current minimum `created_at` across the table (whatever other tests
have already left behind) and setting ours strictly before it -- rather
than asserting anything about what "should" be in the table. This is a
test-only, same-transaction `UPDATE` + `flush` (no extra commit), so it
cannot itself leak a stray row the way the oauth tests' real commits do.
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


async def _pin_as_oldest_workspace(db, workspace_id) -> None:
    """Force `workspace_id` to be the row
    `app/auth/services.py::upsert_user_from_token`'s
    `SELECT Workspace ORDER BY created_at ASC LIMIT 1` will pick, no
    matter what other tests in this process/database have already
    committed. Reads the table's actual current minimum `created_at`
    and backdates this workspace to strictly before it -- a real
    reflection of "oldest", not a guessed constant that some other
    test's own backdating trick could still beat.
    """
    from sqlalchemy import func, select, update

    from app.auth.models import Workspace

    current_min = (
        await db.execute(select(func.min(Workspace.created_at)))
    ).scalar_one()
    baseline = current_min or datetime.now(timezone.utc)
    sentinel = baseline - timedelta(days=1)
    await db.execute(
        update(Workspace).where(Workspace.id == workspace_id).values(created_at=sentinel)
    )
    await db.flush()


@skip_no_pg
@pytest.mark.asyncio
async def test_expired_invite_is_a_real_db_noop_new_user_rejected(db, workspace):
    """A real, already-expired UserInvite row in Postgres must not admit
    a new user -- the `or_` predicate has to actually filter it out at
    the SQL level, not just in a test author's mocked return value.

    Pinned as the oldest workspace so the rejection is provably about
    the expired invite, not an accident of which workspace the
    new-user-join query happened to resolve to.
    """
    from app.auth import services as auth_svc
    from app.auth.jwt import TokenClaims

    await _pin_as_oldest_workspace(db, workspace.id)

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
    row DOES admit the new user, with the workspace and role it names.

    Must be pinned as the oldest workspace: otherwise, whenever some
    other test in the suite has already left a real (committed) newer
    -or-older Workspace row behind, `upsert_user_from_token` may resolve
    a DIFFERENT workspace than the one this test put its invite in, find
    no matching invite there, and raise `InviteRequired` for a reason
    that has nothing to do with what this test checks.
    """
    from app.auth import services as auth_svc
    from app.auth.jwt import TokenClaims

    await _pin_as_oldest_workspace(db, workspace.id)

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
