"""Quote catalog data-access — async SQLAlchemy 2.0. Phase 1."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.quote.models import Product, Quote


async def list_for_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, *, active_only: bool = True
) -> list[Product]:
    stmt = select(Product).where(Product.workspace_id == workspace_id)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.category.asc(), Product.name.asc())
    return list((await db.execute(stmt)).scalars().all())


async def get(
    db: AsyncSession, product_id: uuid.UUID, workspace_id: uuid.UUID
) -> Product | None:
    stmt = select(Product).where(
        Product.id == product_id, Product.workspace_id == workspace_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create(
    db: AsyncSession, workspace_id: uuid.UUID, data: dict[str, Any]
) -> Product:
    product = Product(workspace_id=workspace_id, **data)
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def update(
    db: AsyncSession, product: Product, patch: dict[str, Any]
) -> Product:
    for field, value in patch.items():
        setattr(product, field, value)
    await db.flush()
    await db.refresh(product)
    return product


async def count_for_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Product)
        .where(Product.workspace_id == workspace_id)
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def bulk_create(
    db: AsyncSession, workspace_id: uuid.UUID, items: list[dict[str, Any]]
) -> None:
    for item in items:
        db.add(Product(workspace_id=workspace_id, **item))
    await db.flush()


# --- Quotes (Phase 2) ---


async def list_quotes_for_lead(
    db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID
) -> list[Quote]:
    stmt = (
        select(Quote)
        .where(Quote.lead_id == lead_id, Quote.workspace_id == workspace_id)
        .order_by(Quote.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_quote(
    db: AsyncSession, quote_id: uuid.UUID, workspace_id: uuid.UUID
) -> Quote | None:
    stmt = select(Quote).where(
        Quote.id == quote_id, Quote.workspace_id == workspace_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_quotes_for_workspace(
    db: AsyncSession, workspace_id: uuid.UUID
) -> int:
    stmt = (
        select(func.count())
        .select_from(Quote)
        .where(Quote.workspace_id == workspace_id)
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def delete_quote(db: AsyncSession, quote: Quote) -> None:
    await db.delete(quote)
    await db.flush()
