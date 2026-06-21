"""Quote catalog API — Phase 1.

List is open to any authed user in the workspace (managers build quotes);
create/update/delete/seed are gated to admin/head, mirroring forms/settings.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.db import get_db
from app.quote import services
from app.quote.schemas import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[ProductOut]:
    rows = await services.list_products(db, user.workspace_id, active_only=True)
    return rows  # type: ignore[return-value]


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> ProductOut:
    try:
        product = await services.create_product(
            db, user.workspace_id, payload.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.commit()
    return product  # type: ignore[return-value]


@router.post("/seed-starter", response_model=list[ProductOut])
async def seed_starter(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> list[ProductOut]:
    rows = await services.seed_starter_catalog(db, user.workspace_id)
    await db.commit()
    return rows  # type: ignore[return-value]


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> ProductOut:
    try:
        product = await services.update_product(
            db, user.workspace_id, product_id, payload.model_dump(exclude_unset=True)
        )
    except services.ProductNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.commit()
    return product  # type: ignore[return-value]


@router.delete("/{product_id}", response_model=ProductOut)
async def deactivate_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> ProductOut:
    try:
        product = await services.deactivate_product(
            db, user.workspace_id, product_id
        )
    except services.ProductNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    await db.commit()
    return product  # type: ignore[return-value]
