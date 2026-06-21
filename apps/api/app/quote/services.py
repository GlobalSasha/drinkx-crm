"""Quote catalog service layer — validation + CRUD + seed. Phase 1."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.quote import repositories as repo
from app.quote.models import PRODUCT_CATEGORIES, Product


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
