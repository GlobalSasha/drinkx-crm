"""FORECAST-01 (P2-8) -- oracle for the not-yet-built server aggregate.

`docs/brain` task: the forecast page (`apps/web/app/(app)/forecast/page.tsx`)
sums `deal_amount` over `useLeads({ page_size: 500 })`, i.e. one page of
`GET /leads`. That route caps `page_size` at 200 (`le=200`), so the literal
frontend call 422s outright, and even the best-case call under today's
route (`page_size=200`) only covers a fraction of a workspace with more
than 200 assigned leads -- see `REPRO.md` for the concrete numbers
(1200 leads, oracle SUM 1,919,400 vs first-page SUM 219,900).

This file is written AHEAD OF the fix, against a server aggregate that
does not exist yet (`GET /leads/forecast`, name taken from
`FORECAST-01_TASK_CONTRACT.md`). Every test here is expected to FAIL
today (404/405, or an assertion mismatch) -- that failure is itself the
deliverable: it is the acceptance oracle the real implementation must
turn green. See `FORECAST_CONTRACT.md` and `REPRO.md` (scratchpad,
FORECAST-01) for the literal formula this aggregate must reproduce and
the open ambiguities (role-scope default, commercial_model mixing,
archived_at, response number format) that a reviewer must resolve before
or during implementation, not silently while making these tests pass.

FC-04 (vitest -- forecast/page.tsx must stop requesting page_size=500 for
metrics, and must show an error state instead of stale/zero KPIs on a
failed aggregate fetch) is out of scope here; it belongs in
apps/web/app/(app)/forecast/page.test.tsx once the hook exists, and is
only recorded as an expectation in FORECAST_CONTRACT.md section 8.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

import app.main  # noqa: F401 -- registers SQLAlchemy mappers
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

FORECAST_PATH = "/leads/forecast"

N_LEADS_LARGE = 1200  # > any page_size the /leads route accepts (le=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _user(db, workspace_id, role: str, name: str):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


async def _lead(
    db,
    workspace_id,
    *,
    name: str,
    assigned_to=None,
    pool: bool = False,
    pipeline_id=None,
    stage_id=None,
    deal_amount=None,
):
    from app.leads.models import Lead

    lead = Lead(
        workspace_id=workspace_id,
        company_name=name,
        assignment_status="pool" if pool else "assigned",
        assigned_to=None if pool else assigned_to,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        deal_amount=deal_amount,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _call(db, actor, method: str, path: str, **kwargs):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


async def _oracle_sum(db, workspace_id, assigned_to=None) -> float:
    """Independent SQL SUM(deal_amount) over the FULL assigned, non-deleted
    set -- the literal `pipelineTotal` filter from FORECAST_CONTRACT.md §3
    (assignment_status == "assigned"), minus the stage/won-lost split which
    the tests below hold constant (single non-won/lost stage) so the oracle
    reduces to a plain SUM.
    """
    from app.leads.models import Lead

    conds = [
        Lead.workspace_id == workspace_id,
        Lead.assignment_status == "assigned",
        Lead.deleted_at.is_(None),
    ]
    if assigned_to is not None:
        conds.append(Lead.assigned_to == assigned_to)
    total = (
        await db.execute(select(func.coalesce(func.sum(Lead.deal_amount), 0)).where(*conds))
    ).scalar_one()
    return float(total)


def _amount_from(payload: dict, *keys: str) -> float:
    """Pull an amount out of the (unknown-shape) forecast response and
    coerce it the way the frontend does: Number(value) — see
    FORECAST_CONTRACT.md §5. Accepts either a JSON number or a Decimal
    string; either is a valid implementation choice per the open ambiguity.
    """
    node = payload
    for k in keys:
        assert k in node, f"expected key {k!r} in forecast response, got {sorted(node.keys())}"
        node = node[k]
    return float(node)


# ---------------------------------------------------------------------------
# FC-01 — full-set aggregate == independent SQL oracle, pagination-proof
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_fc01_full_set_aggregate_matches_oracle_beyond_500_rows(
    db, workspace, admin_user, pipeline
):
    """1200+ assigned leads for a head/admin user, deterministic deal_amount.
    The server aggregate must equal the oracle SUM over ALL of them, not a
    truncated page — a lead past row 500 (or row 200, today's page_size
    cap) must move the total. Regression guard: pointing the aggregate at
    the first 500 (or 200) rows makes this fail (see task contract
    "sensitivity" clause).
    """
    p, s = pipeline
    for i in range(N_LEADS_LARGE):
        await _lead(
            db, workspace.id,
            name=f"FC01 Co {i}",
            assigned_to=admin_user.id,
            pipeline_id=p.id,
            stage_id=s.id,
            deal_amount=1000 + i,
        )

    oracle_total = await _oracle_sum(db, workspace.id)
    assert oracle_total == sum(1000 + i for i in range(N_LEADS_LARGE))

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, (
        f"GET {FORECAST_PATH} not implemented yet (got {resp.status_code}: "
        f"{resp.text[:200]}) — this FAIL is the FORECAST-01 oracle counterexample; "
        "expected to turn green once the server aggregate ships"
    )
    body = resp.json()
    server_total = _amount_from(body, "pipeline_total")
    assert server_total == oracle_total, (
        f"server aggregate ({server_total}) must equal the full-set oracle SUM "
        f"({oracle_total}) — a partial-page aggregate would report a smaller "
        f"number here, reproducing the original bug at a new boundary"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_fc02_pagination_params_do_not_change_the_total(db, workspace, admin_user, pipeline):
    """The aggregate must not accept/depend on page or page_size at all --
    passing them (if the route even takes them) must not shrink the total
    versus calling it with no paging params."""
    p, s = pipeline
    for i in range(600):
        await _lead(
            db, workspace.id,
            name=f"FC02 Co {i}",
            assigned_to=admin_user.id,
            pipeline_id=p.id,
            stage_id=s.id,
            deal_amount=100 + i,
        )
    oracle_total = await _oracle_sum(db, workspace.id)

    resp_plain = await _call(db, admin_user, "GET", FORECAST_PATH)
    resp_paged = await _call(db, admin_user, "GET", f"{FORECAST_PATH}?page=1&page_size=50")

    assert resp_plain.status_code == 200, f"got {resp_plain.status_code}: {resp_plain.text[:200]}"
    assert resp_paged.status_code == 200, f"got {resp_paged.status_code}: {resp_paged.text[:200]}"
    total_plain = _amount_from(resp_plain.json(), "pipeline_total")
    total_paged = _amount_from(resp_paged.json(), "pipeline_total")
    assert total_plain == oracle_total
    assert total_paged == oracle_total, (
        "a page_size/page query param changed the total — pagination is "
        "leaking into the aggregate, exactly the bug FORECAST-01 exists to kill"
    )


# ---------------------------------------------------------------------------
# FC-02 (role scope) — manager sees only own; head/admin see whole workspace;
# foreign workspace invisible; empty workspace; NULL deal_amount.
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_fc02_manager_scoped_to_own_leads_only(db, workspace, pipeline):
    """A manager's forecast must total only their own assigned leads, even
    though other managers in the same workspace have larger pipelines --
    mirrors the accepted role split in FORECAST_CONTRACT.md §2/§7 item 2
    (explicitly NOT the same as GET /leads' self-default for admin/head)."""
    p, s = pipeline
    mgr_a = await _user(db, workspace.id, "manager", "MgrA")
    mgr_b = await _user(db, workspace.id, "manager", "MgrB")

    await _lead(db, workspace.id, name="A1", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=s.id, deal_amount=1000)
    await _lead(db, workspace.id, name="A2", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=s.id, deal_amount=2000)
    await _lead(db, workspace.id, name="B1", assigned_to=mgr_b.id, pipeline_id=p.id, stage_id=s.id, deal_amount=50_000)

    resp = await _call(db, mgr_a, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    total = _amount_from(resp.json(), "pipeline_total")
    assert total == 3000, (
        f"manager A's forecast ({total}) must be their own 3000, not include "
        "manager B's 50000 — a manager must never see workspace-wide totals"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_fc02_head_sees_whole_workspace(db, workspace, pipeline):
    """Head/admin forecast = sum across ALL managers in the workspace, not
    just their own book -- this is a deliberate design decision for the new
    route (unlike GET /leads, whose default for admin/head is self)."""
    p, s = pipeline
    head = await _user(db, workspace.id, "head", "Head")
    mgr_a = await _user(db, workspace.id, "manager", "MgrA")
    mgr_b = await _user(db, workspace.id, "manager", "MgrB")

    await _lead(db, workspace.id, name="A1", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=s.id, deal_amount=1000)
    await _lead(db, workspace.id, name="B1", assigned_to=mgr_b.id, pipeline_id=p.id, stage_id=s.id, deal_amount=2000)
    await _lead(db, workspace.id, name="H1", assigned_to=head.id, pipeline_id=p.id, stage_id=s.id, deal_amount=3000)

    resp = await _call(db, head, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    total = _amount_from(resp.json(), "pipeline_total")
    assert total == 6000, (
        f"head's forecast ({total}) must cover the whole workspace (6000), "
        "not just their own assigned leads"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_fc02_other_workspace_is_invisible(db, workspace, admin_user, pipeline):
    """A second workspace's leads must never leak into this one's forecast,
    however large."""
    from app.auth.models import Workspace

    p, s = pipeline
    other_ws = Workspace(name="Other WS", plan="pro", sprint_capacity_per_week=20)
    db.add(other_ws)
    await db.flush()
    other_admin = await _user(db, other_ws.id, "admin", "OtherAdmin")
    await _lead(db, other_ws.id, name="Other Co", assigned_to=other_admin.id, pipeline_id=None, stage_id=None, deal_amount=999_999)

    await _lead(db, workspace.id, name="Mine", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=500)

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    total = _amount_from(resp.json(), "pipeline_total")
    assert total == 500, (
        f"forecast ({total}) leaked another workspace's 999999 into the total"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_fc02_empty_workspace_is_zero_not_error(db, workspace, admin_user):
    """No leads at all -> zeros, per the task card's allowed control
    ('пустой workspace -> нули и понятный empty')."""
    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    total = _amount_from(resp.json(), "pipeline_total")
    assert total == 0


@skip_no_pg
@pytest.mark.asyncio
async def test_fc02_null_deal_amount_counts_as_zero(db, workspace, admin_user, pipeline):
    """A lead with deal_amount IS NULL contributes 0, matching the frontend's
    `Number(lead.deal_amount ?? 0)` (FORECAST_CONTRACT.md §3) -- it must not
    be excluded from the set or crash the aggregate."""
    p, s = pipeline
    await _lead(db, workspace.id, name="NullAmt", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=None)
    await _lead(db, workspace.id, name="WithAmt", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=777)

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    total = _amount_from(resp.json(), "pipeline_total")
    assert total == 777


# ---------------------------------------------------------------------------
# FC-03 — number format is Number()-compatible and precision-safe
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_fc03_amount_is_number_parseable_without_precision_loss(db, workspace, admin_user, pipeline):
    """Whatever wire format is chosen (JSON number vs Decimal-as-string --
    FORECAST_CONTRACT.md §5, open ambiguity), the value the client parses
    with `Number(...)`/`float(...)` must exactly equal the Decimal oracle,
    to the cent -- 12,2 precision, per `Lead.deal_amount: Numeric(12, 2)`.
    """
    p, s = pipeline
    # Cents-precision amount to catch float/Decimal drift.
    await _lead(db, workspace.id, name="Cents", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=1234.56)

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert "pipeline_total" in body
    raw = body["pipeline_total"]
    assert isinstance(raw, (int, float, str)), f"unexpected type {type(raw)} for pipeline_total"
    parsed = float(raw)
    assert parsed == pytest.approx(1234.56, abs=1e-9), (
        f"pipeline_total round-tripped to {parsed}, expected 1234.56 -- "
        "check for float drift or truncation in the aggregate"
    )
