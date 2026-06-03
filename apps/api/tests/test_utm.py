"""UTM find-or-create dictionaries (Odoo utm pattern) — DB-backed."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.conftest import POSTGRES_AVAILABLE

# Trigger ORM mapper configuration (Lead string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401

# Module-level so create_all (session fixture) registers the utm tables.
from app.utm.models import UtmCampaign, UtmMedium, UtmSource  # noqa: F401
from app.utm.services import resolve_utm

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


@skip_no_pg
async def test_resolve_utm_creates_then_reuses(db, workspace):
    from app.utm.models import UtmSource
    from app.utm.services import resolve_utm

    utm = {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "spring"}
    ids1 = await resolve_utm(db, workspace.id, utm)
    assert all(v is not None for v in ids1.values())

    # Created with is_auto=True.
    src = (
        await db.execute(select(UtmSource).where(UtmSource.id == ids1["utm_source_id"]))
    ).scalar_one()
    assert src.name == "google"
    assert src.is_auto is True

    # Second call with the same names → same ids, no duplicate rows.
    ids2 = await resolve_utm(db, workspace.id, utm)
    assert ids2 == ids1
    n_sources = (
        await db.execute(
            select(func.count()).select_from(UtmSource).where(UtmSource.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert n_sources == 1


@skip_no_pg
async def test_resolve_utm_blank_and_missing(db, workspace):
    from app.utm.services import resolve_utm

    ids = await resolve_utm(db, workspace.id, {"utm_source": "   ", "utm_campaign": "promo"})
    assert ids["utm_source_id"] is None   # blank → no row
    assert ids["utm_medium_id"] is None   # missing key → no row
    assert ids["utm_campaign_id"] is not None


@skip_no_pg
async def test_resolve_utm_trims(db, workspace):
    from app.utm.models import UtmSource
    from app.utm.services import resolve_utm

    ids = await resolve_utm(db, workspace.id, {"utm_source": "  yandex  "})
    src = (
        await db.execute(select(UtmSource).where(UtmSource.id == ids["utm_source_id"]))
    ).scalar_one()
    assert src.name == "yandex"


@skip_no_pg
async def test_resolve_utm_workspace_scoped(db, workspace):
    from app.auth.models import Workspace
    from app.utm.models import UtmSource
    from app.utm.services import resolve_utm

    ws2 = Workspace(name="WS2", plan="pro", sprint_capacity_per_week=20)
    db.add(ws2)
    await db.flush()

    id_a = (await resolve_utm(db, workspace.id, {"utm_source": "vk"}))["utm_source_id"]
    id_b = (await resolve_utm(db, ws2.id, {"utm_source": "vk"}))["utm_source_id"]
    assert id_a != id_b   # same name, different workspace → different rows

    n = (
        await db.execute(
            select(func.count())
            .select_from(UtmSource)
            .where(UtmSource.name == "vk", UtmSource.workspace_id.in_([workspace.id, ws2.id]))
        )
    ).scalar_one()
    assert n == 2
