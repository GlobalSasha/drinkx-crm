"""Quote totals computation — pure (no DB). КП Phase 2."""
from __future__ import annotations

from decimal import Decimal


def _line(qty, price, disc=0):
    return {"quantity": qty, "unit_price": price, "line_discount_pct": disc}


def test_single_line_no_vat_no_discount():
    from app.quote.services import compute_totals

    r = compute_totals([_line(2, 100)], discount=0, vat_rate=0)
    assert r["line_totals"] == [Decimal("200.00")]
    assert r["subtotal"] == Decimal("200.00")
    assert r["total"] == Decimal("200.00")


def test_line_discount_percent():
    from app.quote.services import compute_totals

    # 2 * 100 * (1 - 10%) = 180
    r = compute_totals([_line(2, 100, 10)], discount=0, vat_rate=0)
    assert r["line_totals"] == [Decimal("180.00")]
    assert r["subtotal"] == Decimal("180.00")


def test_quote_discount_then_vat():
    from app.quote.services import compute_totals

    # 600 + 400 = 1000 subtotal; -100 discount = 900; +20% VAT = 1080
    r = compute_totals([_line(1, 600), _line(1, 400)], discount=100, vat_rate=20)
    assert r["subtotal"] == Decimal("1000.00")
    assert r["total"] == Decimal("1080.00")


def test_discount_larger_than_subtotal_clamps_to_zero():
    from app.quote.services import compute_totals

    r = compute_totals([_line(1, 100)], discount=500, vat_rate=20)
    assert r["subtotal"] == Decimal("100.00")
    assert r["total"] == Decimal("0.00")


def test_rounding_half_up():
    from app.quote.services import compute_totals

    r = compute_totals([_line(1, 10.005)], discount=0, vat_rate=0)
    assert r["line_totals"] == [Decimal("10.01")]


def test_empty_lines():
    from app.quote.services import compute_totals

    r = compute_totals([], discount=0, vat_rate=20)
    assert r["subtotal"] == Decimal("0.00")
    assert r["total"] == Decimal("0.00")
