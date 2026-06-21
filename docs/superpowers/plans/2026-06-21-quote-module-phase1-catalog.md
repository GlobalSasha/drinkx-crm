# Quote Module — Phase 1: Product Catalog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A workspace-scoped DrinkX product catalog (`products` table + CRUD API + seed + a minimal Settings UI) that Phase 2's quote builder will pick line items from.

**Architecture:** New ORM model `Product` in the promoted `app/quote/` package (products only exist to serve quotes, so they share the domain — YAGNI). Standard package-per-domain CRUD (models/schemas/repositories/services/routers), workspace-scoped, list open to all roles, mutations gated `require_admin_or_head` (mirrors `forms`/`settings`). One Alembic migration `0049`. A small Settings catalog list on the frontend.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + Alembic (backend); Next.js 15 App Router + TanStack Query (frontend).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-21-quote-module-design.md`.
- All rows workspace-scoped (`workspace_id` FK→workspaces, CASCADE). Money is `Numeric(12, 2)`.
- Categories: one of `station | service | install | option | other`.
- No new Python/JS dependency.
- Backend test cmd (this machine): `cd apps/api && .venv/bin/python -c "import sqlalchemy, pytest, sys; sys.exit(pytest.main(['<args>']))"`. CI: `uv run pytest -q`. Postgres-gated tests use `POSTGRES_AVAILABLE` / `@skip_no_pg`.
- Frontend gate: `cd apps/web && npm run typecheck && npm run lint && pnpm build`.
- Next migration id: `0049_quote_catalog`, `down_revision = "0048_lead_lookup_indexes"`, file `apps/api/alembic/versions/20260621_0049_quote_catalog.py`.

## File structure

- Create `apps/api/app/quote/models.py` — `Product` ORM (promote the placeholder package).
- Create `apps/api/app/quote/schemas.py` — `ProductOut`, `ProductCreate`, `ProductUpdate`.
- Create `apps/api/app/quote/repositories.py` — async data access.
- Create `apps/api/app/quote/services.py` — validation + CRUD orchestration + seed.
- Create `apps/api/app/quote/routers.py` — `/api/products` CRUD.
- Modify `apps/api/app/main.py` — register the products router.
- Create `apps/api/alembic/versions/20260621_0049_quote_catalog.py` — `products` table.
- Create `apps/api/tests/test_quote_catalog.py` — CRUD + scoping + seed tests.
- Create `apps/web/lib/hooks/use-products.ts` + types in `apps/web/lib/types.ts`.
- Create `apps/web/components/settings/CatalogSection.tsx` + mount it on the settings page.

---

## Task 1: `Product` model + Alembic migration

**Files:**
- Create: `apps/api/app/quote/models.py`
- Create: `apps/api/alembic/versions/20260621_0049_quote_catalog.py`

**Interfaces:**
- Produces: `Product` ORM with columns `id, workspace_id, name, category, unit_price, is_active, created_at, updated_at`; table `products`.

- [ ] **Step 1: Write `Product`**, mirroring `app/custom_attributes/models.py` conventions (Base + UUIDPrimaryKeyMixin, `workspace_id` FK CASCADE, `DateTime(timezone=True), server_default=func.now()`):

```python
"""Quote/КП product catalog — Sprint Quote v1, Phase 1."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin

# Keep in sync with web/lib/types.ts PRODUCT_CATEGORIES.
PRODUCT_CATEGORIES = ("station", "service", "install", "option", "other")


class Product(Base, UUIDPrimaryKeyMixin):
    """A catalog item a quote line can reference. Workspace-scoped."""
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_workspace_active", "workspace_id", "is_active"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="other", server_default="other"
    )
    unit_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Write the migration** (mirror `20260611_0048_lead_lookup_indexes.py` for the revision/down_revision shape):

```python
"""Quote catalog — products table.

Revision ID: 0049_quote_catalog
Revises: 0048_lead_lookup_indexes
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0049_quote_catalog"
down_revision = "0048_lead_lookup_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="other"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_products_workspace_active", "products", ["workspace_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_products_workspace_active", table_name="products")
    op.drop_table("products")
```

- [ ] **Step 3: Verify** — `cd apps/api && .venv/bin/python -m py_compile app/quote/models.py alembic/versions/20260621_0049_quote_catalog.py` → exit 0. Confirm `Product` imports: `.venv/bin/python -c "import sqlalchemy; from app.quote.models import Product; print(Product.__tablename__)"` → `products`.

- [ ] **Step 4: Commit** — `git add apps/api/app/quote/models.py apps/api/alembic/versions/20260621_0049_quote_catalog.py && git commit -m "feat(quote): product catalog model + migration (phase 1)"`

---

## Task 2: Schemas + repositories + services (CRUD + seed)

**Files:**
- Create: `apps/api/app/quote/schemas.py`, `apps/api/app/quote/repositories.py`, `apps/api/app/quote/services.py`
- Test: `apps/api/tests/test_quote_catalog.py`

**Interfaces:**
- Produces: `services.list_products(db, workspace_id, *, active_only=True)`, `create_product(db, workspace_id, payload)`, `update_product(db, workspace_id, product_id, patch)`, `deactivate_product(db, workspace_id, product_id)`, `seed_starter_catalog(db, workspace_id)`; raises `ProductNotFound`, `ValueError` (bad category).

- [ ] **Step 1: Schemas** (Pydantic, `model_config = ConfigDict(from_attributes=True)` like `forms/schemas.py`):

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    category: str
    unit_price: float
    is_active: bool

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = "other"
    unit_price: float = 0

class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    category: str | None = None
    unit_price: float | None = None
    is_active: bool | None = None
```

- [ ] **Step 2: Repositories** (async, workspace-scoped; mirror `forms/repositories.py`): `list_for_workspace(db, workspace_id, active_only)`, `get(db, product_id, workspace_id)`, `create(db, workspace_id, data)`, `update(db, product, patch)`, `count_for_workspace(db, workspace_id)`.

- [ ] **Step 3: Services** with category validation against `PRODUCT_CATEGORIES`, soft-delete (`deactivate` sets `is_active=False`), and `seed_starter_catalog` that is **idempotent** (no-op if `count_for_workspace > 0`) inserting: `("Кофейная станция S100","station",0)`, `("Кофейная станция S300","station",0)`, `("Сервисный пакет (год)","service",0)`, `("Монтаж и пусконаладка","install",0)`, `("Брендирование","option",0)`. Prices 0 = owner edits later.

- [ ] **Step 4: Write tests** in `tests/test_quote_catalog.py` — pure where possible: category validation rejects an unknown category (`ValueError`); `seed_starter_catalog` is idempotent (second call adds nothing). Use the mock-only sqlalchemy-stub style from `tests/test_public_submit.py` for service-level logic, or `@skip_no_pg` integration tests for the repository round-trip. At minimum a non-PG test asserting `services._validate_category("bogus")` raises and the seed list has 5 deterministic items.

- [ ] **Step 5: Run** — `cd apps/api && .venv/bin/python -c "import sqlalchemy, pytest, sys; sys.exit(pytest.main(['tests/test_quote_catalog.py','-q']))"` → pass.

- [ ] **Step 6: Commit** — `git add apps/api/app/quote/{schemas,repositories,services}.py apps/api/tests/test_quote_catalog.py && git commit -m "feat(quote): catalog schemas/repos/services + seed + tests (phase 1)"`

---

## Task 3: Router + main.py registration

**Files:**
- Create: `apps/api/app/quote/routers.py`
- Modify: `apps/api/app/main.py` (add `include_router`)

**Interfaces:**
- Consumes: services from Task 2.
- Produces: `GET /api/products` (list, all roles), `POST /api/products` + `PATCH /api/products/{id}` + `DELETE /api/products/{id}` (gated `require_admin_or_head`).

- [ ] **Step 1: Router** — `APIRouter(prefix="/api/products", tags=["products"])`. List uses `Depends(current_user)`; create/update/delete use `Depends(require_admin_or_head)` (from `app.auth.dependencies`). Map `ProductNotFound`→404, `ValueError`→400. Mirror `forms/routers.py` shape.

- [ ] **Step 2: Register** — in `app/main.py`, alongside the other `include_router` calls (~line 130), add:

```python
    from app.quote.routers import router as products_router
    app.include_router(products_router)
```

- [ ] **Step 3: Verify** — `cd apps/api && .venv/bin/python -c "import sqlalchemy; import app.main; print('ok')"` → `ok`. Confirm route registered: a `@skip_no_pg` route-smoke test (mirror `tests/base_update/test_api.py::test_routes_registered_in_app`, using `{r.path for r in app.routes if hasattr(r, 'path')}`) asserts `/api/products` is present.

- [ ] **Step 4: Commit** — `git add apps/api/app/quote/routers.py apps/api/app/main.py apps/api/tests/test_quote_catalog.py && git commit -m "feat(quote): catalog router + registration (phase 1)"`

---

## Task 4: Seed on demand + wire to workspace

**Files:**
- Modify: `apps/api/app/quote/routers.py` (add `POST /api/products/seed-starter`, admin/head)

- [ ] **Step 1:** Add `POST /api/products/seed-starter` (gated admin/head) calling `services.seed_starter_catalog(db, workspace_id)` and returning the resulting list. Idempotent (Task 2 guarantees no-op when products exist). This lets the owner populate the starter catalog with one click rather than a data migration.

- [ ] **Step 2: Verify** — `py_compile` + the existing tests still pass.

- [ ] **Step 3: Commit** — `git commit -am "feat(quote): one-click starter catalog seed endpoint (phase 1)"`

---

## Task 5: Frontend — products hook + Settings catalog list

**Files:**
- Modify: `apps/web/lib/types.ts` (add `ProductOut`, `PRODUCT_CATEGORIES`)
- Create: `apps/web/lib/hooks/use-products.ts`
- Create: `apps/web/components/settings/CatalogSection.tsx`
- Modify: the settings page (`apps/web/app/(app)/settings/page.tsx`) to mount `CatalogSection` (admin/head only, matching how other admin sections are gated there).

**Interfaces:**
- Consumes: `/api/products` from Task 3.

- [ ] **Step 1: Types** — add to `lib/types.ts`:

```typescript
export const PRODUCT_CATEGORIES = ["station", "service", "install", "option", "other"] as const;
export interface ProductOut {
  id: string;
  name: string;
  category: string;
  unit_price: number;
  is_active: boolean;
}
```

- [ ] **Step 2: Hook** `use-products.ts` (TanStack Query, mirror `use-forms.ts`): `useProducts()` (GET list), `useCreateProduct()`, `useUpdateProduct()`, `useDeactivateProduct()`, `useSeedStarterCatalog()`.

- [ ] **Step 3: `CatalogSection.tsx`** — a list of catalog rows (name · category · price · active toggle) with inline add/edit (name, category select, price) and a «Засеять стартовый каталог» button shown when the list is empty. Use the existing settings-section styling (mirror `components/settings/ChannelsSection.tsx`). Gate to admin/head like the other admin sections.

- [ ] **Step 4: Mount** on the settings page next to the other admin sections.

- [ ] **Step 5: Verify** — `cd apps/web && npm run typecheck && npm run lint && pnpm build` → all exit 0; `/settings` builds.

- [ ] **Step 6: Commit** — `git add apps/web/lib/types.ts apps/web/lib/hooks/use-products.ts apps/web/components/settings/CatalogSection.tsx "apps/web/app/(app)/settings/page.tsx" && git commit -m "feat(quote): catalog management in Settings (phase 1)"`

---

## Self-Review

**Spec coverage (Phase 1 slice):** `products` table + columns ✓ (Task 1); catalog CRUD + soft-delete ✓ (Tasks 2-3); seed starter set ✓ (Tasks 2,4); admin/head gating on mutations ✓ (Task 3); Settings UI ✓ (Task 5). Quotes/quote_lines, totals, builder, print, deal-sync are **Phase 2-4** (separate plans) — out of scope here, by design.

**Placeholder scan:** every code step carries real code; seed list is explicit; commands are exact. ✓

**Type consistency:** `Product` columns (Task 1) == migration columns (Task 1) == `ProductOut`/`ProductCreate` fields (Task 2) == TS `ProductOut` (Task 5); `PRODUCT_CATEGORIES` identical in `models.py` and `types.ts`. Service names in Task 2 == those called in Task 3. ✓

## Maintenance notes

- Phase 2 (`quotes`/`quote_lines`) will add a `product_id_ref` FK→`products` (SET NULL) and denormalize `product_name` onto the line so catalog edits/deletes don't corrupt historical quotes — keep `Product` soft-deletable (never hard-delete) for that reason.
- Reviewer: confirm the migration runs at deploy (no local Postgres here); the route-smoke + seed-idempotency tests run in CI with Postgres.
