"""Manager workload — aggregate assembly."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_workload_assembles_zero_fills_and_drops_terminal():
    from app.team import services

    s1, s2, terminal = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    u1, u2 = uuid.uuid4(), uuid.uuid4()

    # NOTE: `name` is a reserved MagicMock kwarg — set it as an attribute, not in the ctor.
    user1 = MagicMock(id=u1, email="ivan@x.io"); user1.name = "Иван"
    user2 = MagicMock(id=u2, email="petr@x.io"); user2.name = None

    stages = [(s1, "Квалификация", 1, "#0a84ff"), (s2, "КП", 4, "#ff9f0a")]
    rows = [
        (u1, s1, 2, 100.0, 1),
        (u1, terminal, 5, 999.0, 0),  # terminal → must be dropped
        (u1, s2, 1, 50.0, 0),
    ]

    with patch("app.team.services.users_repo.list_for_workspace",
               new=AsyncMock(return_value=([user1, user2], 2))):
        with patch("app.team.services.repo.non_terminal_stages",
                   new=AsyncMock(return_value=stages)):
            with patch("app.team.services.repo.workload_rows",
                       new=AsyncMock(return_value=rows)):
                out = await services.workload(MagicMock(), workspace_id=uuid.uuid4())

    assert [s["name"] for s in out["stages"]] == ["Квалификация", "КП"]
    by_id = {m["user_id"]: m for m in out["managers"]}

    m1 = by_id[u1]
    assert m1["by_stage"][str(s1)] == {"count": 2, "sum_amount": 100.0}
    assert str(terminal) not in m1["by_stage"]
    assert m1["open_count"] == 3
    assert m1["pipeline_sum"] == 150.0
    assert m1["stuck_count"] == 1

    m2 = by_id[u2]
    assert m2["name"] == "petr@x.io"   # name=None → email fallback
    assert m2["by_stage"] == {}
    assert m2["open_count"] == 0 and m2["stuck_count"] == 0
