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


# ---------------------------------------------------------------------------
# QA additions (sonnet-qa, FORECAST-01 verification pass) -- an INDEPENDENT
# oracle that recomputes the contract formula in Python from raw rows,
# deliberately not sharing a single line of SQL with
# `app/leads/analytics.py::forecast_summary` (or its `_FORECAST_*_SQL` text
# blocks). If both this oracle and the production aggregate agree, the
# formula is very unlikely to be coincidentally wrong the same way twice.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


async def _independent_oracle(db, workspace_id, assigned_to=None) -> dict:
    """Recompute FORECAST_CONTRACT.md §3 from raw rows, in Python, using
    plain per-table SELECTs -- no shared SQL text with analytics.py."""
    from sqlalchemy import text as _text

    lead_rows = (
        await db.execute(
            _text(
                """
                SELECT id, stage_id, deal_amount, last_activity_at, created_at,
                       company_name
                FROM leads
                WHERE workspace_id = :wid
                  AND assignment_status = 'assigned'
                  AND deleted_at IS NULL
                  AND (CAST(:assigned_to AS uuid) IS NULL OR assigned_to = CAST(:assigned_to AS uuid))
                """
            ),
            {"wid": str(workspace_id), "assigned_to": str(assigned_to) if assigned_to else None},
        )
    ).mappings().all()

    stage_rows = (
        await db.execute(
            _text(
                """
                SELECT s.id, s.probability, s.is_won, s.is_lost, s.rot_days, s.name, s.position
                FROM stages s
                JOIN pipelines p ON p.id = s.pipeline_id
                WHERE p.workspace_id = :wid
                """
            ),
            {"wid": str(workspace_id)},
        )
    ).mappings().all()
    stages_by_id = {str(r["id"]): r for r in stage_rows}

    open_history_rows = (
        await db.execute(
            _text(
                """
                SELECT lsh.lead_id, lsh.stage_id, lsh.entered_at
                FROM lead_stage_history lsh
                JOIN leads l ON l.id = lsh.lead_id
                WHERE l.workspace_id = :wid AND lsh.exited_at IS NULL
                """
            ),
            {"wid": str(workspace_id)},
        )
    ).mappings().all()
    open_history_by_lead = {}
    for r in open_history_rows:
        open_history_by_lead[(str(r["lead_id"]), str(r["stage_id"]))] = r["entered_at"]

    now = datetime.now(timezone.utc)
    pipeline_total = 0.0
    weighted_total = 0.0
    at_risk_total = 0.0
    won_recent = 0.0
    # Every non-won/lost stage starts at zero -- stages with no matching
    # lead still appear in the output (FORECAST_CONTRACT.md §3 stageBars).
    stage_bars: dict[str, dict] = {
        str(r["id"]): {"total": 0.0, "count": 0, "position": r["position"]}
        for r in stage_rows
        if not r["is_won"] and not r["is_lost"]
    }

    for lead in lead_rows:
        stage_id = str(lead["stage_id"]) if lead["stage_id"] else None
        stage = stages_by_id.get(stage_id) if stage_id else None
        if stage is None:
            continue  # lead without a stage contributes to nothing (§3)
        amount = float(lead["deal_amount"] or 0)

        if stage["is_won"]:
            touched = lead["last_activity_at"]
            if touched is not None and touched >= now - timedelta(days=90):
                won_recent += amount
            continue
        if stage["is_lost"]:
            continue

        pipeline_total += amount
        weighted_total += amount * float(stage["probability"] or 0) / 100

        entered_at = open_history_by_lead.get((str(lead["id"]), stage_id))
        anchor = entered_at if entered_at is not None else lead["created_at"]
        stage_days = max(0.0, (now - anchor).total_seconds() / 86400)
        rot = stage["rot_days"] or 0
        if rot > 0 and stage_days > rot and amount > 0:
            at_risk_total += amount

        bar = stage_bars[stage_id]
        bar["total"] += amount
        bar["count"] += 1

    return {
        "pipeline_total": pipeline_total,
        "weighted_total": weighted_total,
        "at_risk_total": at_risk_total,
        "won_recent": won_recent,
        "stage_bars": stage_bars,
    }


async def _stage(db, pipeline_id, *, name, position, probability=10, rot_days=7, is_won=False, is_lost=False):
    from app.pipelines.models import Stage

    s = Stage(
        pipeline_id=pipeline_id,
        name=name,
        position=position,
        color="#a1a1a6",
        rot_days=rot_days,
        probability=probability,
        is_won=is_won,
        is_lost=is_lost,
    )
    db.add(s)
    await db.flush()
    return s


async def _open_history(db, lead_id, stage_id, entered_at):
    from app.leads.models import LeadStageHistory

    h = LeadStageHistory(lead_id=lead_id, stage_id=stage_id, entered_at=entered_at, exited_at=None)
    db.add(h)
    await db.flush()
    return h


def _assert_close(actual, expected, label):
    assert actual == pytest.approx(expected, abs=1e-6), (
        f"{label}: server={actual!r} vs independent-oracle={expected!r}"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_qa_full_formula_cross_check_matches_independent_oracle_across_roles(
    db, workspace, admin_user, pipeline
):
    """>1200 leads, multiple stages (active/won/lost), stage-dwell history,
    checked under manager/head/admin scopes against a from-scratch Python
    oracle -- not the production SQL. Covers pipeline_total, weighted_total,
    won_recent and at_risk_total simultaneously, plus stage_bars sums/counts.
    """
    p, active = pipeline  # active: probability=10 (default), rot_days=14
    won = await _stage(db, p.id, name="Выиграно", position=90, probability=100, is_won=True)
    lost = await _stage(db, p.id, name="Проиграно", position=91, is_lost=True)
    active2 = await _stage(db, p.id, name="Discovery", position=2, probability=25, rot_days=5)

    head = await _user(db, workspace.id, "head", "Head")
    mgr_a = await _user(db, workspace.id, "manager", "MgrA")
    mgr_b = await _user(db, workspace.id, "manager", "MgrB")

    now = datetime.now(timezone.utc)

    # Bulk of the volume: > 1200 leads split across two managers, well past
    # any historical page_size boundary (200/500).
    N_A, N_B = 700, 601
    for i in range(N_A):
        await _lead(
            db, workspace.id, name=f"A{i}", assigned_to=mgr_a.id,
            pipeline_id=p.id, stage_id=active.id, deal_amount=100 + i,
        )
    for i in range(N_B):
        await _lead(
            db, workspace.id, name=f"B{i}", assigned_to=mgr_b.id,
            pipeline_id=p.id, stage_id=active2.id, deal_amount=50 + i,
        )
    assert N_A + N_B > 1200

    # A handful of leads on mgr_a exercising every other branch of the
    # formula at once.
    won_lead = await _lead(db, workspace.id, name="WonRecent", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=won.id, deal_amount=9000)
    won_lead.last_activity_at = now - timedelta(days=5)
    won_old_lead = await _lead(db, workspace.id, name="WonOld", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=won.id, deal_amount=5000)
    won_old_lead.last_activity_at = now - timedelta(days=120)  # outside 90d window
    lost_lead = await _lead(db, workspace.id, name="Lost", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=lost.id, deal_amount=7777)
    stageless_lead = await _lead(db, workspace.id, name="NoStage", assigned_to=mgr_a.id, pipeline_id=None, stage_id=None, deal_amount=123456)

    # Open stage-history row older than rot_days (14) -> at-risk.
    at_risk_lead = await _lead(db, workspace.id, name="AtRisk", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=active.id, deal_amount=4321)
    await _open_history(db, at_risk_lead.id, active.id, now - timedelta(days=20))

    # Open stage-history row younger than rot_days -> NOT at-risk.
    not_at_risk_lead = await _lead(db, workspace.id, name="NotAtRisk", assigned_to=mgr_a.id, pipeline_id=p.id, stage_id=active.id, deal_amount=1111)
    await _open_history(db, not_at_risk_lead.id, active.id, now - timedelta(days=2))

    # No stage-history row at all -> fallback to created_at, old enough to
    # be at-risk under active's rot_days=14.
    fallback_lead = await _lead(db, workspace.id, name="FallbackCreatedAt", assigned_to=mgr_b.id, pipeline_id=p.id, stage_id=active.id, deal_amount=6543)
    fallback_lead.created_at = now - timedelta(days=30)

    await db.flush()

    for role_label, actor, scope in (
        ("manager mgr_a", mgr_a, mgr_a.id),
        ("manager mgr_b", mgr_b, mgr_b.id),
        ("head (workspace-wide)", head, None),
        ("admin (workspace-wide)", admin_user, None),
    ):
        oracle = await _independent_oracle(db, workspace.id, assigned_to=scope)
        resp = await _call(db, actor, "GET", FORECAST_PATH)
        assert resp.status_code == 200, f"[{role_label}] got {resp.status_code}: {resp.text[:200]}"
        body = resp.json()

        _assert_close(body["pipeline_total"], oracle["pipeline_total"], f"[{role_label}] pipeline_total")
        _assert_close(body["weighted_total"], oracle["weighted_total"], f"[{role_label}] weighted_total")
        _assert_close(body["won_recent"], oracle["won_recent"], f"[{role_label}] won_recent")
        _assert_close(body["at_risk_total"], oracle["at_risk_total"], f"[{role_label}] at_risk_total")

        server_bars = {b["stage_id"]: b for b in body["stage_bars"]}
        assert set(server_bars) == set(oracle["stage_bars"]), (
            f"[{role_label}] stage_bars stage set mismatch: "
            f"server={sorted(server_bars)} oracle={sorted(oracle['stage_bars'])}"
        )
        for sid, obar in oracle["stage_bars"].items():
            sbar = server_bars[sid]
            _assert_close(sbar["total"], obar["total"], f"[{role_label}] stage_bars[{sid}].total")
            assert sbar["count"] == obar["count"], (
                f"[{role_label}] stage_bars[{sid}].count: server={sbar['count']} oracle={obar['count']}"
            )

    # Cross-check: manager totals must be strict subsets, never equal to the
    # workspace-wide head/admin total (guards against scope leaking).
    a_only = await _independent_oracle(db, workspace.id, assigned_to=mgr_a.id)
    whole = await _independent_oracle(db, workspace.id, assigned_to=None)
    assert a_only["pipeline_total"] < whole["pipeline_total"]


@skip_no_pg
@pytest.mark.asyncio
async def test_qa_lead_without_stage_excluded_from_every_metric(db, workspace, admin_user, pipeline):
    """A lead with `stage_id IS NULL` must not contribute to pipeline_total,
    weighted_total, at_risk_total, won_recent or any stage_bars entry --
    it is skipped outright (FORECAST_CONTRACT.md §3), not bucketed anywhere."""
    p, s = pipeline
    await _lead(db, workspace.id, name="Real", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=1000)
    await _lead(db, workspace.id, name="Stageless", assigned_to=admin_user.id, pipeline_id=None, stage_id=None, deal_amount=999_999)

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["pipeline_total"] == 1000, (
        f"stageless lead's 999999 leaked into pipeline_total={body['pipeline_total']}"
    )
    total_bar_count = sum(b["count"] for b in body["stage_bars"])
    assert total_bar_count == 1, (
        f"stageless lead must not appear in any stage_bars bucket (count total={total_bar_count})"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_qa_open_stage_history_older_than_rot_days_is_at_risk(db, workspace, admin_user, pipeline):
    """A lead whose open lead_stage_history row is older than the stage's
    rot_days must show up in at_risk_total AND in the top-10 at_risk_deals
    list (FC-DELTA-001 -- the whole point of computing stage_days server
    side instead of relying on the never-populated list-response field)."""
    p, s = pipeline  # rot_days=14
    lead = await _lead(db, workspace.id, name="Overdue Co", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=8000)
    entered = datetime.now(timezone.utc) - timedelta(days=20)
    await _open_history(db, lead.id, s.id, entered)

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["at_risk_total"] == 8000
    deal_ids = {d["id"] for d in body["at_risk_deals"]}
    assert str(lead.id) in deal_ids, f"overdue lead missing from at_risk_deals: {body['at_risk_deals']}"
    overdue = next(d for d in body["at_risk_deals"] if d["id"] == str(lead.id))
    # 20 days in stage - 14 rot_days = 6 days overdue (within the same day
    # the test runs; allow a 1-day slack for FLOOR/wall-clock edges).
    assert overdue["overdue_days"] in (5, 6), overdue


@skip_no_pg
@pytest.mark.asyncio
async def test_qa_lead_without_any_stage_history_falls_back_to_created_at(db, workspace, admin_user, pipeline):
    """A lead that has never appeared in lead_stage_history (no row at all,
    open or closed) must fall back to `created_at` for its stage-dwell
    clock -- not silently read as zero days (which would make it
    impossible for an old, never-transitioned lead to ever be at-risk)."""
    p, s = pipeline  # rot_days=14
    lead = await _lead(db, workspace.id, name="NeverMoved", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=3000)
    lead.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db.flush()

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["at_risk_total"] == 3000, (
        f"lead with no stage-history row and created_at 30d ago (rot_days=14) "
        f"must be at-risk via the created_at fallback; got at_risk_total={body['at_risk_total']}"
    )
    deal_ids = {d["id"] for d in body["at_risk_deals"]}
    assert str(lead.id) in deal_ids


@skip_no_pg
@pytest.mark.asyncio
async def test_qa_archived_duplicates_are_included_per_contract(db, workspace, admin_user, pipeline):
    """FORECAST_CONTRACT.md §3 explicitly records that `archived_at`
    (merged-away duplicate) leads are NOT excluded on /forecast, unlike
    /leads/utm-stats which does filter them out -- this locks in that this
    is a deliberate as-is replication, not an oversight. If a future change
    starts filtering archived_at here, this test documents the behavior
    change so it can't happen silently."""
    p, s = pipeline
    kept = await _lead(db, workspace.id, name="Kept", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=1000)
    dup = await _lead(db, workspace.id, name="ArchivedDuplicate", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=2000)
    dup.archived_at = datetime.now(timezone.utc)
    await db.flush()

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["pipeline_total"] == 3000, (
        f"expected archived_at duplicate to be INCLUDED (contract §3 'reproduce as-is'), "
        f"got pipeline_total={body['pipeline_total']} (looks like it was excluded)"
    )


@skip_no_pg
@pytest.mark.asyncio
async def test_qa_pool_lead_not_assigned_is_excluded(db, workspace, admin_user, pipeline):
    """A lead sitting in the shared pool (`assignment_status='pool'`,
    `assigned_to IS NULL`) must never contribute to the forecast -- the
    browser formula this replicates only ever saw `GET /leads`, which
    filters to `assignment_status == 'assigned'` at the SQL level
    (FORECAST_CONTRACT.md §3). Regression guard: dropping that filter from
    the new aggregate's scoped CTE makes this fail (mutation-tested)."""
    p, s = pipeline
    await _lead(db, workspace.id, name="Assigned", assigned_to=admin_user.id, pipeline_id=p.id, stage_id=s.id, deal_amount=1000)
    await _lead(db, workspace.id, name="InPool", pool=True, pipeline_id=p.id, stage_id=s.id, deal_amount=999_999)

    resp = await _call(db, admin_user, "GET", FORECAST_PATH)
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["pipeline_total"] == 1000, (
        f"pool (unassigned) lead's 999999 leaked into pipeline_total={body['pipeline_total']}"
    )
