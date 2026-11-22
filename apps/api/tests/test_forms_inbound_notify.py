"""Form submission bell (mobile phase 1, 22.11.2026): kind `lead_inbound`,
an admin who owns the lead gets one notification, not two."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.forms.public_routers as forms_mod
import app.notifications.services as notif_mod


def _result(*, all_=None, scalar=None):
    r = MagicMock()
    r.all = MagicMock(return_value=all_ or [])
    r.scalar_one_or_none = MagicMock(return_value=scalar)
    return r


async def _run(*, admins: list, owner):
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        _result(all_=[(a,) for a in admins]),
        _result(scalar=owner),
    ])
    notify_mock = AsyncMock(return_value=None)
    with patch.object(notif_mod, "safe_notify", new=notify_mock):
        await forms_mod._notify_workspace_admins(
            session,
            workspace_id=uuid.uuid4(),
            form_name="Сайт drinkx.ru",
            company_name="Кофе Хаус",
            lead_id=uuid.uuid4(),
        )
    return notify_mock


@pytest.mark.asyncio
async def test_form_lead_notifies_admins_and_owner_with_lead_inbound():
    admin, owner = uuid.uuid4(), uuid.uuid4()
    notify_mock = await _run(admins=[admin], owner=owner)
    users = [c.kwargs["user_id"] for c in notify_mock.await_args_list]
    assert users == [admin, owner]
    assert {c.kwargs["kind"] for c in notify_mock.await_args_list} == {"lead_inbound"}
    assert notify_mock.await_args_list[0].kwargs["body"] == '"Сайт drinkx.ru" — Кофе Хаус'


@pytest.mark.asyncio
async def test_admin_who_owns_the_lead_gets_one_notification():
    admin = uuid.uuid4()
    notify_mock = await _run(admins=[admin], owner=admin)
    assert notify_mock.await_count == 1


@pytest.mark.asyncio
async def test_form_notify_failure_does_not_raise():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    await forms_mod._notify_workspace_admins(
        session,
        workspace_id=uuid.uuid4(),
        form_name="f",
        company_name="c",
        lead_id=uuid.uuid4(),
    )
