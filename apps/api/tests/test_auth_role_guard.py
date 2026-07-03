"""SEC-01 regression: PATCH /auth/me must not let a user change their own role."""
from __future__ import annotations

import pytest

from app.auth.routers import update_me
from app.auth.schemas import UserUpdateIn
from tests.conftest import POSTGRES_AVAILABLE

pytestmark = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


@pytest.mark.asyncio
async def test_self_role_escalation_is_ignored(db, user):
    # `user` fixture is role="manager"
    assert user.role == "manager"

    # Even if a client forges a role field, it must not stick.
    payload = UserUpdateIn.model_validate({"role": "admin", "name": "Hacker"})
    result = await update_me(payload=payload, user=user, session=db)

    assert result.role == "manager", "manager must not be able to self-promote to admin"
    assert result.name == "Hacker", "legitimate profile fields still update"
