"""Quote lifecycle — PG round-trip integration tests (КП Phase 2 backend).

Covers the gap the unit tests (test_quote_totals.py, pure) can't: persistence
of create → totals → number sequence → update (line replace) → status stamps →
apply-to-deal → delete rules → workspace isolation. PG-gated; skipped when no
Postgres is reachable.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo

    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db, workspace_id, payload, assigned_to=None, assignment_status="assigned"
    )


async def _make_workspace(db):
    from app.auth.models import Workspace

    ws = Workspace(name=f"WS {uuid.uuid4().hex[:6]}", plan="pro", sprint_capacity_per_week=20)
    db.add(ws)
    await db.flush()
    return ws


def _line(name, qty, price, disc=0, product_id_ref=None):
    return {
        "product_id_ref": product_id_ref,
        "product_name": name,
        "description": None,
        "quantity": qty,
        "unit_price": price,
        "line_discount_pct": disc,
    }


async def _count_lines(db, quote_id) -> int:
    from app.quote.models import QuoteLine

    stmt = select(func.count()).select_from(QuoteLine).where(QuoteLine.quote_id == quote_id)
    return int((await db.execute(stmt)).scalar_one())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_create_persists_number_and_totals(db, workspace, user):
    """Create stamps КП-0001, denormalizes line names, stores computed totals."""
    from app.quote import services

    # A real catalog product to exercise the product_id_ref FK + denormalization.
    product = await services.create_product(
        db, workspace.id, {"name": "Станция S100", "category": "station", "unit_price": 100}
    )
    lead = await _make_lead(db, workspace.id)

    quote = await services.create_quote(
        db,
        workspace.id,
        lead.id,
        user.id,
        {
            "vat_rate": 20,
            "discount": 70,
            "lines": [
                _line("Станция S100", 2, 100, 0, product_id_ref=product.id),
                _line("Монтаж", 1, 300, 10),  # 300*(1-10%) = 270
            ],
        },
    )

    assert quote.number == "КП-0001"
    assert quote.status == "draft"
    # subtotal 470; -70 = 400; +20% VAT = 480
    assert quote.subtotal == Decimal("470.00")
    assert quote.total == Decimal("480.00")

    lines = sorted(quote.lines, key=lambda l: l.position)
    assert [l.position for l in lines] == [0, 1]
    assert lines[0].product_id_ref == product.id
    assert lines[0].product_name == "Станция S100"
    assert lines[0].total == Decimal("200.00")
    assert lines[1].product_id_ref is None  # free-text row
    assert lines[1].total == Decimal("270.00")

    # Round-trip: a fresh fetch resolves the same quote with its lines loaded.
    fetched = await services.get_quote_or_raise(db, workspace.id, quote.id)
    assert fetched.total == Decimal("480.00")
    assert len(fetched.lines) == 2


@skip_no_pg
async def test_number_sequence_is_per_workspace(db, workspace, user):
    """Numbers increment per workspace and restart in a different workspace."""
    from app.quote import services

    lead = await _make_lead(db, workspace.id)
    numbers = [
        (await services.create_quote(db, workspace.id, lead.id, user.id, {})).number
        for _ in range(3)
    ]
    assert numbers == ["КП-0001", "КП-0002", "КП-0003"]

    other_ws = await _make_workspace(db)
    other_lead = await _make_lead(db, other_ws.id)
    first_in_other = await services.create_quote(db, other_ws.id, other_lead.id, None, {})
    assert first_in_other.number == "КП-0001"


@skip_no_pg
async def test_update_replaces_lines_and_recomputes(db, workspace, user):
    """A PATCH with a new line-set replaces the old rows (orphan-delete) and
    recomputes totals from the new lines + header."""
    from app.quote import services

    lead = await _make_lead(db, workspace.id)
    quote = await services.create_quote(
        db,
        workspace.id,
        lead.id,
        user.id,
        {"vat_rate": 0, "discount": 0, "lines": [_line("A", 1, 600), _line("B", 1, 400)]},
    )
    assert quote.subtotal == Decimal("1000.00")
    assert await _count_lines(db, quote.id) == 2

    updated = await services.update_quote(
        db,
        workspace.id,
        quote.id,
        {"vat_rate": 20, "discount": 0, "lines": [_line("C", 2, 50)]},
    )
    # New single line 100; +20% VAT = 120.
    assert updated.subtotal == Decimal("100.00")
    assert updated.total == Decimal("120.00")
    # Old two rows are gone — only the replacement persists.
    assert await _count_lines(db, quote.id) == 1


@skip_no_pg
async def test_status_transitions_stamp_timestamps(db, workspace, user):
    """draft→sent stamps sent_at; →accepted stamps accepted_at; bad status raises."""
    from app.quote import services

    lead = await _make_lead(db, workspace.id)
    quote = await services.create_quote(db, workspace.id, lead.id, user.id, {})
    assert quote.sent_at is None and quote.accepted_at is None

    sent = await services.set_quote_status(db, workspace.id, quote.id, "sent")
    assert sent.status == "sent"
    assert sent.sent_at is not None
    assert sent.accepted_at is None

    accepted = await services.set_quote_status(db, workspace.id, quote.id, "accepted")
    assert accepted.status == "accepted"
    assert accepted.accepted_at is not None

    with pytest.raises(ValueError):
        await services.set_quote_status(db, workspace.id, quote.id, "bogus")


@skip_no_pg
async def test_apply_to_deal_sets_lead_deal_amount(db, workspace, user):
    """apply-to-deal copies the quote total onto lead.deal_amount."""
    from app.leads import repositories as leads_repo
    from app.quote import services

    lead = await _make_lead(db, workspace.id)
    assert lead.deal_amount is None

    quote = await services.create_quote(
        db,
        workspace.id,
        lead.id,
        user.id,
        {"vat_rate": 0, "discount": 0, "lines": [_line("Станция", 1, 1000)]},
    )
    await services.apply_to_deal(db, workspace.id, quote.id)

    fresh = await leads_repo.get_by_id(db, lead.id, workspace.id)
    assert fresh.deal_amount == Decimal("1000.00")


@skip_no_pg
async def test_delete_only_drafts(db, workspace, user):
    """Drafts delete; a sent quote refuses deletion."""
    from app.quote import services

    lead = await _make_lead(db, workspace.id)

    draft = await services.create_quote(db, workspace.id, lead.id, user.id, {})
    await services.delete_quote(db, workspace.id, draft.id)
    with pytest.raises(services.QuoteNotFound):
        await services.get_quote_or_raise(db, workspace.id, draft.id)

    sent = await services.create_quote(db, workspace.id, lead.id, user.id, {})
    await services.set_quote_status(db, workspace.id, sent.id, "sent")
    with pytest.raises(ValueError):
        await services.delete_quote(db, workspace.id, sent.id)


@skip_no_pg
async def test_workspace_isolation(db, workspace, user):
    """A quote in workspace A is invisible from workspace B."""
    from app.quote import services

    lead = await _make_lead(db, workspace.id)
    quote = await services.create_quote(db, workspace.id, lead.id, user.id, {})

    other_ws = await _make_workspace(db)
    with pytest.raises(services.QuoteNotFound):
        await services.get_quote_or_raise(db, other_ws.id, quote.id)
    assert await services.list_quotes(db, other_ws.id, lead.id) == []
