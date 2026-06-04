"""UTM channel analytics — «какой канал приносит сделки» (DB-backed)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.leads.models import Lead
from app.leads.analytics import utm_source_stats
from app.utm.models import UtmSource

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


def _lead(workspace_id, **kw):
    base = dict(
        workspace_id=workspace_id,
        company_name="Acme",
        assignment_status="pool",
        tags_json=[],
    )
    base.update(kw)
    return Lead(**base)


@skip_no_pg
async def test_utm_source_stats_groups_and_sums(db, workspace):
    google = UtmSource(workspace_id=workspace.id, name="google", is_auto=True)
    yandex = UtmSource(workspace_id=workspace.id, name="yandex", is_auto=True)
    db.add_all([google, yandex])
    await db.flush()

    now = datetime.now(timezone.utc)
    db.add_all([
        # google: 2 leads, 1 won for 100
        _lead(workspace.id, utm_source_id=google.id, won_at=now, deal_amount=Decimal("100")),
        _lead(workspace.id, utm_source_id=google.id),
        # yandex: 1 lead, won for 50
        _lead(workspace.id, utm_source_id=yandex.id, won_at=now, deal_amount=Decimal("50")),
        # no source: 1 lead, not won
        _lead(workspace.id),
    ])
    await db.flush()

    rows = await utm_source_stats(db, workspace.id)
    by_source = {r["source"]: r for r in rows}

    assert by_source["google"]["leads"] == 2
    assert by_source["google"]["won"] == 1
    assert by_source["google"]["won_sum"] == Decimal("100")

    assert by_source["yandex"]["leads"] == 1
    assert by_source["yandex"]["won"] == 1
    assert by_source["yandex"]["won_sum"] == Decimal("50")

    # Unattributed leads land in the None bucket; won_sum coalesces to 0.
    assert by_source[None]["leads"] == 1
    assert by_source[None]["won"] == 0
    assert by_source[None]["won_sum"] == 0

    # Ordered by lead count desc → google (2) first.
    assert rows[0]["source"] == "google"


@skip_no_pg
async def test_utm_source_stats_excludes_archived(db, workspace):
    google = UtmSource(workspace_id=workspace.id, name="google", is_auto=True)
    db.add(google)
    await db.flush()

    now = datetime.now(timezone.utc)
    db.add_all([
        _lead(workspace.id, utm_source_id=google.id),
        # archived (e.g. merged-away dup) → must not count
        _lead(workspace.id, utm_source_id=google.id, archived_at=now),
    ])
    await db.flush()

    rows = await utm_source_stats(db, workspace.id)
    by_source = {r["source"]: r for r in rows}
    assert by_source["google"]["leads"] == 1
