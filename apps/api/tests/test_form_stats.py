"""Sprint 3.6 G3 — per-form stats."""
from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()

# `repositories.py` imports `defer` from `sqlalchemy.orm`; the shared
# stub doesn't include it (it was added after test_webforms.py shipped).
# Patch it here so we don't need to touch test_webforms.py.
_sa_orm = sys.modules.get("sqlalchemy.orm")
if _sa_orm is not None and not hasattr(_sa_orm, "defer"):
    class _Callable:  # minimal duplicate of the stub's _Callable
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return type(self)()
        def __getattr__(self, name): return type(self)()
    _sa_orm.defer = _Callable()

WS = uuid.uuid4()


def test_form_stats_schema_shape():
    """FormStatsOut accepts the documented shape."""
    from app.forms.schemas import FormStatsOut

    stats = FormStatsOut(
        submissions_7d=24,
        submissions_30d=87,
        claimed_count=12,
        by_stage={"Новый контакт": 30, "Квалификация": 8},
    )
    assert stats.submissions_7d == 24
    assert stats.by_stage["Квалификация"] == 8


@pytest.mark.asyncio
async def test_get_form_stats_aggregates_four_buckets():
    from app.forms import services as svc

    form_id = uuid.uuid4()
    db = MagicMock()

    # Sequence of awaitable returns: 7d count, 30d count, claimed count,
    # then the by_stage GROUP BY rows.
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=lambda: 24),  # 7d
            MagicMock(scalar_one=lambda: 87),  # 30d
            MagicMock(scalar_one=lambda: 12),  # claimed
            MagicMock(all=lambda: [
                ("Новый контакт", 30),
                ("Квалификация", 8),
            ]),
        ]
    )

    out = await svc.get_form_stats(db, form_id=form_id)

    assert out.submissions_7d == 24
    assert out.submissions_30d == 87
    assert out.claimed_count == 12
    assert out.by_stage == {"Новый контакт": 30, "Квалификация": 8}


@pytest.mark.asyncio
async def test_get_form_stats_groups_unplaced_leads_under_no_stage():
    """Leads with stage_id=NULL must appear under 'Без этапа', not vanish
    from by_stage entirely."""
    from app.forms import services as svc

    form_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=lambda: 2),  # 7d
            MagicMock(scalar_one=lambda: 2),  # 30d
            MagicMock(scalar_one=lambda: 0),  # claimed (still in pool)
            MagicMock(all=lambda: [("Без этапа", 2)]),
        ]
    )

    out = await svc.get_form_stats(db, form_id=form_id)

    assert out.by_stage == {"Без этапа": 2}


@pytest.mark.asyncio
async def test_channel_analytics_shapes_rows_and_totals():
    from app.forms import services as svc

    f1, f2 = uuid.uuid4(), uuid.uuid4()
    async def fake_agg(db, *, workspace_id, date_from, date_to):
        return [
            {"form_id": f1, "channel": "Главный сайт", "submissions": 10, "leads": 8, "won": 2},
            {"form_id": f2, "channel": "Лендинг QSR", "submissions": 5, "leads": 5, "won": 0},
        ]

    with patch("app.forms.repositories.channel_analytics", new=fake_agg):
        out = await svc.get_channel_analytics(
            AsyncMock(), workspace_id=WS, date_from=None, date_to=None
        )

    assert out.total_submissions == 15
    assert out.total_leads == 13
    assert out.total_won == 2
    assert out.rows[0].conversion == 0.25
    assert out.rows[1].conversion == 0.0
