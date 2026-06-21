"""Quote catalog service layer — validation + CRUD + seed. Phase 1."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.quote import repositories as repo
from app.quote.models import (
    PRODUCT_CATEGORIES,
    QUOTE_STATUSES,
    Product,
    Quote,
    QuoteLine,
)


class QuoteNotFound(Exception):
    pass


class ProductNotFound(Exception):
    pass


# Starter DrinkX catalog seeded on demand. Prices are 0 placeholders the
# workspace owner edits later — the point is the categories/structure.
STARTER_CATALOG: list[dict] = [
    {"name": "Кофейная станция S100", "category": "station", "unit_price": 0},
    {"name": "Кофейная станция S300", "category": "station", "unit_price": 0},
    {"name": "Сервисный пакет (год)", "category": "service", "unit_price": 0},
    {"name": "Монтаж и пусконаладка", "category": "install", "unit_price": 0},
    {"name": "Брендирование", "category": "option", "unit_price": 0},
]


def _validate_category(category: str | None) -> None:
    if category is not None and category not in PRODUCT_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Allowed: {PRODUCT_CATEGORIES}"
        )


async def list_products(
    db: AsyncSession, workspace_id: uuid.UUID, *, active_only: bool = True
) -> list[Product]:
    return await repo.list_for_workspace(db, workspace_id, active_only=active_only)


async def create_product(
    db: AsyncSession, workspace_id: uuid.UUID, payload: dict
) -> Product:
    _validate_category(payload.get("category"))
    return await repo.create(db, workspace_id, payload)


async def update_product(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID, patch: dict
) -> Product:
    product = await repo.get(db, product_id, workspace_id)
    if product is None:
        raise ProductNotFound(product_id)
    _validate_category(patch.get("category"))
    return await repo.update(db, product, patch)


async def deactivate_product(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    product = await repo.get(db, product_id, workspace_id)
    if product is None:
        raise ProductNotFound(product_id)
    return await repo.update(db, product, {"is_active": False})


async def seed_starter_catalog(
    db: AsyncSession, workspace_id: uuid.UUID
) -> list[Product]:
    """Idempotent: no-op (returns the current list) if the workspace already
    has any products, so re-clicking «Засеять» can't create duplicates."""
    if await repo.count_for_workspace(db, workspace_id) > 0:
        return await repo.list_for_workspace(db, workspace_id, active_only=False)
    await repo.bulk_create(db, workspace_id, STARTER_CATALOG)
    return await repo.list_for_workspace(db, workspace_id, active_only=False)


# ---------------------------------------------------------------------------
# Quote totals — server-authoritative (КП Phase 2)
# ---------------------------------------------------------------------------

def _money(value) -> Decimal:
    """Quantize to 2 decimal places, half-up — matches Numeric(12, 2)."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_line_total(quantity, unit_price, line_discount_pct) -> Decimal:
    q = Decimal(str(quantity or 0))
    up = Decimal(str(unit_price or 0))
    disc = Decimal(str(line_discount_pct or 0))
    return _money(q * up * (Decimal(1) - disc / Decimal(100)))


def compute_totals(lines, *, discount, vat_rate) -> dict:
    """Server-authoritative quote totals.

    `lines`: iterable of dicts with quantity / unit_price / line_discount_pct.
    Formula (spec): line = qty*price*(1-disc%); subtotal = Σ lines;
    after_discount = max(subtotal - quote_discount, 0); total = after_discount*(1+vat%).
    Returns {line_totals: list[Decimal], subtotal: Decimal, total: Decimal}.
    """
    line_totals = [
        compute_line_total(
            line.get("quantity"), line.get("unit_price"), line.get("line_discount_pct")
        )
        for line in lines
    ]
    subtotal = _money(sum(line_totals, Decimal("0")))
    after_discount = subtotal - _money(discount)
    if after_discount < 0:
        after_discount = Decimal("0.00")
    vat_amount = _money(after_discount * Decimal(str(vat_rate or 0)) / Decimal(100))
    total = _money(after_discount + vat_amount)
    return {"line_totals": line_totals, "subtotal": subtotal, "total": total}


# ---------------------------------------------------------------------------
# Quote CRUD (КП Phase 2)
# ---------------------------------------------------------------------------

async def _generate_number(db: AsyncSession, workspace_id: uuid.UUID) -> str:
    n = await repo.count_quotes_for_workspace(db, workspace_id) + 1
    return f"КП-{n:04d}"


def _build_lines(lines_in: list[dict]) -> list[QuoteLine]:
    out: list[QuoteLine] = []
    for i, line in enumerate(lines_in):
        out.append(
            QuoteLine(
                position=i,
                product_id_ref=line.get("product_id_ref"),
                product_name=line["product_name"],
                description=line.get("description"),
                quantity=line.get("quantity", 1),
                unit_price=line.get("unit_price", 0),
                line_discount_pct=line.get("line_discount_pct", 0),
                total=compute_line_total(
                    line.get("quantity"),
                    line.get("unit_price"),
                    line.get("line_discount_pct"),
                ),
            )
        )
    return out


def _apply_totals(quote: Quote) -> None:
    res = compute_totals(
        [
            {
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "line_discount_pct": l.line_discount_pct,
            }
            for l in quote.lines
        ],
        discount=quote.discount,
        vat_rate=quote.vat_rate,
    )
    quote.subtotal = res["subtotal"]
    quote.total = res["total"]


async def create_quote(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    created_by: uuid.UUID | None,
    payload: dict,
) -> Quote:
    quote = Quote(
        workspace_id=workspace_id,
        lead_id=lead_id,
        created_by=created_by,
        number=await _generate_number(db, workspace_id),
        status="draft",
        recipient_contact_id=payload.get("recipient_contact_id"),
        valid_until=payload.get("valid_until"),
        vat_rate=payload.get("vat_rate", 20),
        discount=payload.get("discount", 0),
    )
    quote.lines = _build_lines(payload.get("lines") or [])
    _apply_totals(quote)
    db.add(quote)
    await db.flush()
    return quote


async def update_quote(
    db: AsyncSession, workspace_id: uuid.UUID, quote_id: uuid.UUID, patch: dict
) -> Quote:
    quote = await repo.get_quote(db, quote_id, workspace_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    if "recipient_contact_id" in patch:
        quote.recipient_contact_id = patch["recipient_contact_id"]
    if "valid_until" in patch:
        quote.valid_until = patch["valid_until"]
    if patch.get("vat_rate") is not None:
        quote.vat_rate = patch["vat_rate"]
    if patch.get("discount") is not None:
        quote.discount = patch["discount"]
    if patch.get("lines") is not None:
        quote.lines = _build_lines(patch["lines"])
    _apply_totals(quote)
    await db.flush()
    return quote


async def set_quote_status(
    db: AsyncSession, workspace_id: uuid.UUID, quote_id: uuid.UUID, status: str
) -> Quote:
    if status not in QUOTE_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Allowed: {QUOTE_STATUSES}")
    quote = await repo.get_quote(db, quote_id, workspace_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    quote.status = status
    now = datetime.now(timezone.utc)
    if status == "sent" and quote.sent_at is None:
        quote.sent_at = now
    if status == "accepted" and quote.accepted_at is None:
        quote.accepted_at = now
    await db.flush()
    return quote


async def apply_to_deal(
    db: AsyncSession, workspace_id: uuid.UUID, quote_id: uuid.UUID
) -> Quote:
    quote = await repo.get_quote(db, quote_id, workspace_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    from app.leads import repositories as leads_repo

    lead = await leads_repo.get_by_id(db, quote.lead_id, workspace_id)
    if lead is not None:
        lead.deal_amount = quote.total
    await db.flush()
    return quote


async def delete_quote(
    db: AsyncSession, workspace_id: uuid.UUID, quote_id: uuid.UUID
) -> None:
    quote = await repo.get_quote(db, quote_id, workspace_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    if quote.status != "draft":
        raise ValueError("Only draft quotes can be deleted")
    await repo.delete_quote(db, quote)


async def list_quotes(
    db: AsyncSession, workspace_id: uuid.UUID, lead_id: uuid.UUID
) -> list[Quote]:
    return await repo.list_quotes_for_lead(db, lead_id, workspace_id)


async def get_quote_or_raise(
    db: AsyncSession, workspace_id: uuid.UUID, quote_id: uuid.UUID
) -> Quote:
    quote = await repo.get_quote(db, quote_id, workspace_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    return quote
